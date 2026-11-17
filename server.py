"""Local-only simulated application site; submissions stay on this machine."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import uuid

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'submissions'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/', '/jobs'):
            self.send_error(404)
            return
        filename = 'index.html' if self.path == '/' else 'jobs.html'
        body = (ROOT / 'site' / filename).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/submit':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 100_000:
                self.send_error(413)
                return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected an object')
            if 'job_id' in data and data['job_id'] not in ('job-a', 'job-b'):
                raise ValueError('Unknown job')
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        submission_id = uuid.uuid4().hex
        OUTPUT.mkdir(exist_ok=True)
        record = {'id': submission_id, 'timestamp': datetime.now(timezone.utc).isoformat(), 'application': data}
        if 'job_id' in data:
            record['job_id'] = data['job_id']
        (OUTPUT / f'{submission_id}.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        body = json.dumps({'id': submission_id}).encode()
        self.send_response(201)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    print('Simulated application: http://127.0.0.1:8000', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8000), Handler).serve_forever()
