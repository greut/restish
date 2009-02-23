def wsgi_out(app, environ):
    out = {}
    def start_response(status, headers, exc_info=None):
        out['status'] = status
        out['headers'] = headers
    out['body'] = ''.join(iter(app(environ, start_response)))
    return out

