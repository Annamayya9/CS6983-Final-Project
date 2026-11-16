"""Separate localhost resume workflow. The original server and form stay intact."""
import argparse
import base64
import binascii
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import uuid

from resume_relevance import MAX_UPLOAD, build_comparison, extract_text, sha256, write_artifacts

ROOT = Path(__file__).resolve().parent
DOWNLOADS = {'original_resume.txt', 'tailored_resume.txt', 'job_description.txt',
             'comparison.html', 'comparison.json', 'changes.diff'}


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.send_bytes((ROOT / 'site/resume.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/job':
            return self.send_json(json.loads((ROOT / 'experiments/resume_relevance/input/job.json').read_text(encoding='utf-8')))
        match = re.fullmatch(r'/artifacts/([a-f0-9]{32})/([a-z_.]+)', path)
        if match and match[2] in DOWNLOADS:
            file = self.server.output / 'artifacts' / match[1] / match[2]
            if file.is_file():
                content_type = 'text/html' if file.suffix == '.html' else 'application/json' if file.suffix == '.json' else 'text/plain'
                return self.send_bytes(file.read_bytes(), content_type + '; charset=utf-8')
        self.send_error(404)

    def read_json(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            raise ValueError('Request origin does not match this local server.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError as exc:
            raise ValueError('Invalid request length.') from exc
        if not 0 < length <= 8 * 1024 * 1024:
            raise ValueError('Request must be nonempty and at most 8 MiB.')
        try:
            data = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError('Expected valid JSON.') from exc
        if not isinstance(data, dict):
            raise ValueError('Expected a JSON object.')
        return data

    def do_POST(self):
        try:
            data = self.read_json()
            if self.path == '/api/tailor':
                filename, encoded = data.get('filename'), data.get('content_base64')
                job_id, jd = data.get('job_id'), data.get('job_description')
                if not all(isinstance(v, str) for v in (filename, encoded, job_id, jd)) or not 1 <= len(job_id.strip()) <= 100:
                    raise ValueError('Provide a filename, resume bytes, job ID, and job description.')
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError('Invalid base64 resume data.') from exc
                text = extract_text(filename, raw)
                report = build_comparison(text, jd, job_id, Path(filename).name)
                report['upload_sha256'] = sha256(raw)
                artifact_id = uuid.uuid4().hex
                write_artifacts(report, self.server.output / 'artifacts' / artifact_id)
                return self.send_json({'tailoring_id': artifact_id, 'report': report,
                                       'comparison_url': f'/artifacts/{artifact_id}/comparison.html',
                                       'resume_url': f'/artifacts/{artifact_id}/tailored_resume.txt'}, 201)
            if self.path == '/submit':
                return self.submit(data)
            self.send_error(404)
        except (ValueError, TypeError) as exc:
            self.send_json({'error': str(exc)}, 400)

    def submit(self, data):
        artifact_id = data.get('tailoring_id', '')
        if not isinstance(artifact_id, str) or not re.fullmatch(r'[a-f0-9]{32}', artifact_id):
            raise ValueError('Analyze and accept the tailored resume before submitting.')
        path = self.server.output / 'artifacts' / artifact_id / 'comparison.json'
        if not path.is_file():
            raise ValueError('Tailoring result not found. Analyze the current resume and JD again.')
        report = json.loads(path.read_text(encoding='utf-8'))
        if data.get('job_id') != report['job_id'] or not isinstance(data.get('job_description'), str) or sha256(data['job_description'].encode()) != report['jd_sha256']:
            raise ValueError('Job description changed. Analyze and review the resume again.')
        if data.get('tailored_accepted') is not True:
            raise ValueError('Review and accept the tailored resume first.')
        try:
            uploaded = base64.b64decode(data.get('resume_content_base64', ''), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Invalid submitted resume bytes.') from exc
        if len(uploaded) > MAX_UPLOAD or sha256(uploaded) != report['tailored_sha256']:
            raise ValueError('Submitted resume does not match the reviewed tailored artifact.')
        required = ('full_name', 'email', 'education', 'experience', 'experience_duration', 'run_id')
        if any(not isinstance(data.get(k), str) or not data[k].strip() for k in required):
            raise ValueError('Complete all required application fields.')
        if data.get('sponsorship') not in ('yes', 'no') or data.get('consent') is not True:
            raise ValueError('Provide sponsorship and explicit simulated consent.')
        if data.get('resume') != 'tailored_resume.txt':
            raise ValueError('Select the generated tailored_resume.txt file.')
        submission_id = uuid.uuid4().hex
        application = {k: data[k] for k in required + ('sponsorship', 'consent', 'resume', 'job_id')}
        application.update(tailoring_id=artifact_id, resume_sha256=report['tailored_sha256'],
                           jd_sha256=report['jd_sha256'])
        record = {'id': submission_id, 'timestamp': datetime.now(timezone.utc).isoformat(),
                  'run_id': data['run_id'], 'application': application,
                  'resume_verified': True, 'before_score': report['before']['score'],
                  'after_score': report['after']['score']}
        directory = self.server.output / 'submissions'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (submission_id + '.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
        self.send_json({'id': submission_id, 'resume_verified': True}, 201)


def make_server(port=8001, output=None):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.output = Path(output or ROOT / 'runs/resume_workflow').resolve()
    server.output.mkdir(parents=True, exist_ok=True)
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8001)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    with make_server(args.port, args.output_dir) as server:
        print(f'Resume workflow: http://127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
