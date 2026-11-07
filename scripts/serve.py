#!/usr/bin/env python3
"""Bounded loopback preview of a generated synthetic review page.

The original CMS proof server exposed its whole checkout indefinitely. This
public adaptation retains stdlib serving but requires an explicit generated
review root, admits only six known review assets, and always closes its socket.
It does not start on import; running it is an explicit operator action.
"""
from __future__ import annotations

import argparse
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import time
from urllib.parse import urlsplit

from studio_paths import STUDIO_ROOT

ROOT = STUDIO_ROOT
CONFIG_PATH = STUDIO_ROOT / 'config/local_webui.json'
ALLOWED_PATHS = frozenset({'/index.html','/bundle.json','/review.js','/review.css','/feedback.js'})


def load_settings(config_path=CONFIG_PATH):
    settings = json.loads(Path(config_path).read_text(encoding='utf-8'))
    if settings.get('host') != '127.0.0.1':
        raise ValueError('loopback_required')
    port = settings.get('port')
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError('invalid_preview_port')
    return settings


def admit_preview(root):
    from human_voice_review import validate_bundle
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or not (root/'index.html').is_file():
        raise ValueError('generated_review_page_required')
    bundle_path = (root/'bundle.json').resolve(strict=True)
    if not bundle_path.is_relative_to(root):
        raise ValueError('preview_path_escape')
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    validate_bundle(bundle)
    if bundle.get('media') or not bundle.get('candidates') or not all(
            candidate.get('synthetic_only') is True for candidate in bundle['candidates'].values()):
        raise ValueError('synthetic_only_required')
    return root


def handler_for(root, port):
    root = admit_preview(root)
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,directory=str(root),**kwargs)
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def admitted_path(self):
            if self.headers.get('Host') != f'127.0.0.1:{port}':
                return None
            name = urlsplit(self.path).path
            name = '/index.html' if name == '/' else name
            if name not in ALLOWED_PATHS:
                return None
            path = (root/name.lstrip('/')).resolve()
            return path if path.is_relative_to(root) and path.is_file() else None
        def translate_path(self,path):
            admitted = self.admitted_path()
            if admitted is None:
                raise ValueError('preview_path_not_allowed')
            return str(admitted)
        def do_GET(self):
            if self.admitted_path() is None:
                return self.send_error(404)
            super().do_GET()
        def do_HEAD(self):
            if self.admitted_path() is None:
                return self.send_error(404)
            super().do_HEAD()
        def end_headers(self):
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            super().end_headers()
        def log_message(self,*args):
            pass
    return Handler


def run_preview(root,seconds,config_path=CONFIG_PATH):
    if type(seconds) not in (int,float) or not 1 <= seconds <= 1800:
        raise ValueError('invalid_preview_timeout')
    settings = load_settings(config_path)
    root = admit_preview(root)
    # Resolve the handler first; invalid input cannot bind a socket.
    handler = handler_for(root,settings['port'])
    server = HTTPServer((settings['host'],settings['port']),handler)
    if settings['port'] == 0:
        server.RequestHandlerClass = handler_for(root,server.server_address[1])
    server.timeout = .15
    start = time.monotonic()
    try:
        print(f'http://127.0.0.1:{server.server_address[1]}/index.html',flush=True)
        while time.monotonic()-start < seconds:
            server.handle_request()
    finally:
        server.server_close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True,help='Generated synthetic review site, not a repository root.')
    parser.add_argument('--seconds',type=float,default=300,help='Finite lifetime:1–1800 seconds.')
    parser.add_argument('--config',type=Path,default=CONFIG_PATH)
    args = parser.parse_args(argv)
    run_preview(args.root,args.seconds,args.config)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
