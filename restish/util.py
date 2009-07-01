"""
General-purpose utilities.
"""

from restish import http, url


def wsgi(request, app, path_info_segments):
    """
    Call out to another wsgi application.

    WARNING: This is only a partial implementation for now. It does not handle
    the start_response exc_info arg, nor does it handle calls to the write
    function that must be returned from start_response.
    """
    # Copy and update the environ to set new SCRIPT_NAME and PATH_INFO.
    script_segments = request.path.path_segments
    if path_info_segments:
        script_segments = script_segments[:-len(path_info_segments)]
    environ = dict(request.environ)
    environ['SCRIPT_NAME'] = url.join_path(script_segments)
    environ['PATH_INFO'] = url.join_path(path_info_segments)
    # Call the wsgi application.
    stuff = {}
    def write(body_data):
        raise NotImplementedError()
    def start_response(status, headers, exc_info=None):
        if exc_info is not None:
            raise NotImplementedError()
        stuff['status'] = status
        stuff['headers'] = headers
        return write
    result = app(environ, start_response)
    return http.Response(stuff['status'], stuff['headers'], result)


class RequestBoundCallable(object):
    """
    Bind a request to something callable.

    The callable will be called with request as the 1st positional argument.
    Any additional args (positional or keyword) will be passed as-is.
    """

    def __init__(self, callable, request):
        self.callable = callable
        self.request = request

    def __call__(self, *a, **k):
        return self.callable(self.request, *a, **k)

    def __getattr__(self, name):
        return getattr(self.callable, name)
    
    def __getitem__(self, name):
        return self.callable[name]

def wsgi_out(app, environ):
    """Simple tool for testing purposes"""
    out = {}
    def start_response(status, headers):
        out['status'] = status
        out['headers'] = headers
    result = app(environ, start_response)
    out['body'] = ''.join(iter(result))
    if hasattr(result, 'close'):
        result.close()
    return out

