"""
General-purpose utilities.
"""


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
    def start_response(status, headers, exc_info=None):
        out['status'] = status
        out['headers'] = headers
    out['body'] = ''.join(iter(app(environ, start_response)))
    return out
