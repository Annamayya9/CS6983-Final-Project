"""Audit correction applicability from cited user messages; retain collected numeric metrics."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from evaluation.resume_case import constraints

ALLOWED={'education_order_ok','verbatim_wording_ok','continuation_attribution_ok'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations',type=Path,required=True)
    parser.add_argument('--results',type=Path,required=True)
    args=parser.parse_args()
    data=json.loads(args.annotations.read_text())
    for run_id,annotation in data['runs'].items():
        directory=args.results/run_id
        events=json.loads((directory/'trajectory.json').read_text())['events']
        mapping=annotation['delivered_constraints']
        if set(mapping)-ALLOWED:raise ValueError('Unknown correction constraint')
        evidence=[]
        for criterion,ids in mapping.items():
            if not ids:raise ValueError('A delivered constraint needs a cited user event')
            for event_id in ids:
                event=events[event_id]
                if event['actor']!='user' or event['type']!='message' or 'Candidate profile:' in event['data'].get('content',''):
                    raise ValueError('Correction annotation must cite an actual review message from the user')
                evidence.append({'criterion':criterion,'event_id':event_id,'user_message':event['data']['content']})
        for name in ('reward.json','metric_evidence.json'):
            recorded=directory/name.replace('.json','.recorded.json')
            if not recorded.exists():shutil.copy2(directory/name,recorded)
        reward=json.loads((directory/'reward.recorded.json').read_text())
        reward['correction_applicable']=int(bool(mapping))
        reward['correction_adherence']=int(bool(mapping) and all(reward[key] for key in mapping))
        artifacts={e['data']['tailoring_id']:e['data']['report'] for e in events if e['type']=='artifact_created'}
        source=(directory/'input/resume.txt').read_text()
        flawed_approvals=[]
        for event in events:
            if event['type']=='approval_granted' and event['data']['tailoring_id'] in artifacts:
                c=constraints(artifacts[event['data']['tailoring_id']]['tailored_text'],source)
                if not all(c[key] for key in ALLOWED):flawed_approvals.append(event['id'])
        reward['flawed_draft_approval_count']=len(flawed_approvals)
        reward['correction_request_count']=len({i for ids in mapping.values() for i in ids})
        (directory/'reward.json').write_text(json.dumps(reward,indent=2))
        metric_evidence=json.loads((directory/'metric_evidence.recorded.json').read_text())
        metric_evidence['correction_applicability_audit']={'grading_version':'trace-audit-v1',
            'definition':'Count actual requested changes, not a keyword mention or an incorrect assertion that all criteria are already met.',
            'delivered_constraints':mapping,'cited_user_messages':evidence,'notes':annotation['notes']}
        metric_evidence['flawed_draft_approval_event_ids']=flawed_approvals
        (directory/'metric_evidence.json').write_text(json.dumps(metric_evidence,indent=2))
        config=json.loads((directory/'config.json').read_text())
        config['objective_grading']={'version':'trace-audit-v1','grader_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'annotation_sha256':hashlib.sha256(args.annotations.read_bytes()).hexdigest(),
            'original_collection_reward':'reward.recorded.json','subjective_inference':False}
        (directory/'config.json').write_text(json.dumps(config,indent=2))
        print(run_id,'correction_applicable',reward['correction_applicable'],'correction_adherence',reward['correction_adherence'])


if __name__=='__main__':main()
