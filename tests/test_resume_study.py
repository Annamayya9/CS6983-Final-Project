import base64
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
import urllib.error
import urllib.request

from evaluation.resume_case import BASELINE, CASE, bullet_blocks, canonical, constraints, evaluate, make_environment
from resume_proposed import build_comparison, study_html
from run_resume_study import UserChannel

SOURCE = (CASE / 'input/resume.txt').read_text(encoding='utf-8')
JOB = json.loads((CASE / 'input/job.json').read_text())
PROFILE = json.loads((CASE / 'input/profile.json').read_text())


class TailoringStudyTests(unittest.TestCase):
    def test_baseline_reproduces_wrong_claim_attribution_despite_line_retention(self):
        r = BASELINE.build_comparison(SOURCE, JOB['description'])
        c = constraints(r['tailored_text'], SOURCE)
        self.assertEqual(c['source_line_retention'], 1)
        self.assertEqual(c['unsupported_claim_count'], 1)
        self.assertEqual(c['continuation_attribution_ok'], 0)
        self.assertGreater(r['after']['score'], r['before']['score'])

    def test_proposed_moves_whole_claim_blocks(self):
        r = build_comparison(SOURCE, JOB['description'])
        self.assertEqual(constraints(r['tailored_text'], SOURCE)['unsupported_claim_count'], 0)
        self.assertEqual(Counter(map(canonical, bullet_blocks(SOURCE))), Counter(map(canonical, bullet_blocks(r['tailored_text']))))
        self.assertEqual(r['before']['coverage_percent'], r['after']['coverage_percent'])

    def test_user_preferences_outrank_presentation_score(self):
        r = build_comparison(SOURCE, JOB['description'], preferences={'education_first': True, 'preserve_wording': True})
        c = constraints(r['tailored_text'], SOURCE)
        self.assertTrue(all(c[k] for k in ('education_order_ok', 'verbatim_wording_ok', 'continuation_attribution_ok')))
        self.assertEqual(c['unsupported_claim_count'], 0)
        self.assertEqual(Counter(line for line in SOURCE.splitlines() if line.strip()), Counter(line for line in r['tailored_text'].splitlines() if line.strip()))
        self.assertNotIn('Kubernetes', r['tailored_text'])
        self.assertNotIn('AWS', r['tailored_text'])

    def test_two_employers_keep_their_own_bullets_and_wrapped_claims(self):
        source = 'Name\nWORK HISTORY\nEmployer A\n- Filing\n- Python tools,\n  in a synthetic benchmark.\nEmployer B\n- Notes\n- SQL reports,\n  reviewed by a classmate.\n'
        r = build_comparison(source, 'Python SQL')
        self.assertLess(r['tailored_text'].index('Python tools'), r['tailored_text'].index('Employer B'))
        self.assertGreater(r['tailored_text'].index('SQL reports'), r['tailored_text'].index('Employer B'))
        self.assertEqual(Counter(map(canonical, bullet_blocks(source))), Counter(map(canonical, bullet_blocks(r['tailored_text']))))

    def test_preferences_are_explicit_booleans(self):
        for pref in ({'education_first': 'yes'}, {'invent_aws': True}):
            with self.assertRaises(ValueError):
                build_comparison(SOURCE, JOB['description'], preferences=pref)

    def test_proposed_ui_exposes_controls_and_separate_metric_explanation(self):
        text = study_html((CASE / 'baseline_v1/site.html').read_text())
        for expected in ('preserve_wording', 'education_first', '/api/review-status', 'unchanged qualifications'):
            self.assertIn(expected, text)

    def test_rewards_are_numeric_and_require_correct_authoritative_fields(self):
        report = build_comparison(SOURCE, JOB['description'], preferences={'education_first': True, 'preserve_wording': True})
        application = {**PROFILE, 'resume_sha256':report['tailored_sha256'], 'jd_sha256':report['jd_sha256']}
        events = [{'id':0,'actor':'user','type':'message','data':{'is_review_feedback':True}},
                  {'id':1,'actor':'environment','type':'submission_record','data':{
                      'approved_at_submission':True,'record':{'resume_verified':True,'application':application}}}]
        reward, evidence = evaluate(events, SOURCE, report, .1, PROFILE)
        self.assertEqual(reward['task_success'], 1)
        self.assertTrue(all(isinstance(value, (int,float)) and math.isfinite(value) for value in reward.values()))
        for name in ('engagement','cognitive_load','perceived_controllability'):
            self.assertNotIn(name, reward)
        application['email'] = 'wrong@example.test'
        self.assertEqual(evaluate(events, SOURCE, report, .1, PROFILE)[0]['task_success'], 0)

    def test_feedback_recorder_rejects_a_simulated_run(self):
        with tempfile.TemporaryDirectory() as temp:
            Path(temp,'config.json').write_text(json.dumps({'mode':'simulated'}))
            result = subprocess.run([sys.executable, str(CASE.parents[2] / 'record_human_feedback.py'), '--run',temp], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(Path(temp,'survey.json').exists())

    def test_human_and_llm_users_use_identical_agent_facing_text_channel(self):
        class Trace:
            def __init__(self):self.events=[]
            def emit(self,actor,kind,data):
                event={'id':len(self.events),'actor':actor,'type':kind,'data':data}
                self.events.append(event)
                return event
        persona=json.loads((CASE/'input/user_persona.json').read_text())
        reply=persona['required_review_feedback']
        observation={'text':'Original resume and tailored resume visible here.'}
        traces=[]
        for mode in ('human','simulated'):
            trace=Trace()
            channel=UserChannel(mode,SimpleNamespace(current_artifact='draft',approved_artifact=None),trace,'fixture-model',{},persona,PROFILE)
            with patch('builtins.input',return_value=reply), patch('run_resume_study.model_call',return_value={'content':json.dumps({'message':reply})}), patch('sys.stdout',new=io.StringIO()):
                self.assertEqual(channel.receive('Review this version.',observation,checkpoint=True),reply)
            traces.append(trace.events)
        human=[e['data'] for e in traces[0] if e['actor']=='user']
        simulated=[e['data'] for e in traces[1] if e['actor']=='user']
        self.assertEqual(human,simulated)
        self.assertEqual([e['data'] for e in traces[0] if e['type']=='user_observation'],
                         [e['data'] for e in traces[1] if e['type']=='user_observation'])


class ProposedApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.events=[]
        self.server=make_environment('proposed', CASE/'input', Path(self.temp.name)/'service',
                                     lambda actor,kind,data:self.events.append((actor,kind,data)))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5);self.temp.cleanup()

    def post(self,path,data):
        req=urllib.request.Request(self.url+path,json.dumps(data).encode(),{'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as response:return response.code,json.load(response)

    def tailor(self):
        status,result=self.post('/api/tailor',{'filename':'resume.txt','content_base64':base64.b64encode(SOURCE.encode()).decode(),
            'job_id':JOB['id'],'job_description':JOB['description'],'preferences':{'education_first':True,'preserve_wording':True}})
        self.assertEqual(status,201)
        return result

    def test_current_version_approval_is_required_and_regeneration_revokes_it(self):
        result=self.tailor()
        data={**PROFILE,'run_id':'approval-test','consent':True,'resume':'tailored_resume.txt','tailored_accepted':True,
              'tailoring_id':result['tailoring_id'],'job_id':JOB['id'],'job_description':JOB['description'],
              'resume_content_base64':base64.b64encode(result['report']['tailored_text'].encode()).decode()}
        self.assertEqual(self.post('/submit',data)[0],400)
        self.server.approved_artifact=result['tailoring_id']
        self.assertEqual(self.post('/submit',data)[0],201)
        self.tailor()
        self.assertIsNone(self.server.approved_artifact)
        self.assertEqual(self.post('/submit',data)[0],400)


if __name__ == '__main__':
    unittest.main()
