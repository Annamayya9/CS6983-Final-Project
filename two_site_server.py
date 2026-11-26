"""Two simulated employer origins for the multi-site baseline."""
import argparse
import base64
import binascii
import hashlib
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import uuid

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'submissions'


def make_handler(site_id, job_id, html_file):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/':
                self.send_error(404)
                return
            body = (ROOT / 'site' / html_file).read_bytes()
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
                if length > 8_000_000:
                    self.send_error(413)
                    return
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Expected an object')
                content = data.pop('resume_content_base64', None)
                resume_sha256 = hashlib.sha256(base64.b64decode(content, validate=True)).hexdigest() if content is not None else None
            except (ValueError, UnicodeDecodeError, binascii.Error, TypeError):
                self.send_error(400)
                return
            submission_id = uuid.uuid4().hex
            record = {'id': submission_id, 'site_id': site_id, 'job_id': job_id,
                      'timestamp': datetime.now(timezone.utc).isoformat(), 'application': data,
                      'resume_sha256': resume_sha256}
            OUTPUT.mkdir(exist_ok=True)
            (OUTPUT / f'{submission_id}.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
            body = json.dumps({'id': submission_id, 'site_id': site_id, 'job_id': job_id}).encode()
            self.send_response(201)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser = argparse.ArgumentParser(description='Run two localhost-only simulated employer sites.')
    parser.add_argument('--port-a', type=int, default=8002)
    parser.add_argument('--port-b', type=int, default=8003)
    args = parser.parse_args()
    if args.port_a == args.port_b:
        parser.error('The two sites need different ports.')
    first = ThreadingHTTPServer(('127.0.0.1', args.port_a), make_handler('site-a', 'job-a', 'site_a.html'))
    try:
        second = ThreadingHTTPServer(('127.0.0.1', args.port_b), make_handler('site-b', 'job-b', 'site_b.html'))
    except Exception:
        first.server_close()
        raise
    thread = threading.Thread(target=first.serve_forever, daemon=True)
    thread.start()
    print(f'Site A: http://127.0.0.1:{args.port_a}/', flush=True)
    print(f'Site B: http://127.0.0.1:{args.port_b}/', flush=True)
    try:
        second.serve_forever()
    finally:
        first.shutdown(); first.server_close(); thread.join(); second.server_close()


if __name__ == '__main__': main()
