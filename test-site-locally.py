#!/usr/bin/env python3

from http.server import HTTPServer, CGIHTTPRequestHandler
import os
# This assumes that the script will be called from the root of the package.
# If called from within `scripts/`, then this should be `../static-site` - but I think that will
# be rare enough that we don't need an option flag for that.
os.chdir('static-site')
import argparse
import re
import requests


class LambdaDelegatingHandler(CGIHTTPRequestHandler):
    def do_POST(self):
        if self.path.split('/')[1] == 'api':
            self._delegate('post')
        else:
            super().do_POST()

    def do_GET(self):
        split_path = self.path.split('/')
        if split_path[1] == 'api':
            self._delegate('get')
        else:
            # TODO - replace /foo/bar/baz with /foo/bar/baz.html
            # (The below was a guess that doesn't work. Perhaps the target is cached
            # and referenced elsewhere than in `self.path`)
            # if '.' not in split_path[-1] and len(split_path[-1]) > 0 and len(split_path) > 2:
            #     split_path[-1] += '.html'
            #     self.path = '/'.join(split_path)
            super().do_GET()

    def _delegate(self, method):
        request = self._make_request(method, f'{self.__class__.get_target_domain()}{self.requestline.split()[1]}')
        self.send_response(request.status_code)
        for header_key in request.headers:
            self.send_header(header_key, request.headers[header_key])
        self.end_headers()
        self.wfile.write(request.content)

    @classmethod
    def set_target_domain(cls, target_domain):
        cls.target_domain = target_domain

    @classmethod
    def get_target_domain(cls):
        return cls.target_domain

    def _make_request(self, method, url):
        session = requests.Session()
        data = self.rfile.read(int(self.headers.get('content-length', 0)))
        if data:
            return getattr(session, method)(url, data=data.decode('utf-8'))
        else:
            return getattr(session, method)(url)


def run(args, server_class=HTTPServer, handler_class=LambdaDelegatingHandler):
    server_address = ('', args.port)
    httpd = server_class(server_address, handler_class)
    httpd.RequestHandlerClass.set_target_domain(f'{args.domain}')
    print(f'Go to localhost:{args.port} to test')
    httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='Run a website for local testing')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--domain', required=True)
    args = parser.parse_args()
    run(args)


if __name__ == '__main__':
    main()
