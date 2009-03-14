"""
Base Resource class and associates methods for children and content negotiation
"""
import inspect
import mimetypes
import re

from restish import http, _mimeparse as mimeparse


_RESTISH_CHILD = "restish_child"
_RESTISH_METHOD = "restish_method"
_RESTISH_MATCH = "restish_match"


SHORT_CONTENT_TYPE_EXTRA = {
        'json': 'application/json',
        }


class _metaResource(type):
    """
    Resource meta class that gathers all annotations for easy access.
    """
    def __new__(cls, name, bases, clsattrs):
        cls = type.__new__(cls, name, bases, clsattrs)
        _gather_request_dispatchers(cls, clsattrs)
        _gather_child_factories(cls, clsattrs)
        return cls


def _gather_request_dispatchers(cls, clsattrs):
    """
    Gather any request handler -annotated methods and add them to the class's
    request_dispatchers attribute.
    """
    # Copy the super class's 'request_dispatchers' dict (if any) to this class.
    cls.request_dispatchers = dict(getattr(cls, 'request_dispatchers', {}))
    for callable in _find_annotated_funcs(clsattrs, _RESTISH_METHOD):
        method = getattr(callable, _RESTISH_METHOD, None)
        match = getattr(callable, _RESTISH_MATCH)
        cls.request_dispatchers.setdefault(method, []).append((callable, match))


def _gather_child_factories(cls, clsattrs):
    """
    Gather any 'child' annotated methods and add them to the class's
    child_factories attribute.
    """
    # Copy the super class's 'child_factories' list (if any) to this class.
    cls.child_factories = list(getattr(cls, 'child_factories', []))
    # Extend child_factories to include the ones found on this class.
    child_factories = _find_annotated_funcs(clsattrs, _RESTISH_CHILD)
    cls.child_factories.extend((getattr(f, _RESTISH_CHILD), f) \
                               for f in child_factories)
    # Sort the child factories by score.
    cls.child_factories = sorted(cls.child_factories, \
                                 key=lambda i: i[0].score, reverse=True)


def _find_annotated_funcs(clsattrs, annotation):
    """
    Return a (generated) list of methods that include the given annotation.
    """
    funcs = (item for item in clsattrs.itervalues() \
             if inspect.isroutine(item))
    funcs = (func for func in funcs \
             if getattr(func, annotation, None) is not None)
    return funcs


class Resource(object):
    """
    Base class for additional resource types.

    Provides the basic API required of a resource (resource_child(request,
    segments) and __call__(request)), possibly dispatching to annotated methods
    of the class (using metaclass magic).
    """

    __metaclass__ = _metaResource

    def resource_child(self, request, segments):
        for matcher, func in self.child_factories:
            match = matcher(request, segments)
            if match is not None:
                break
        else:
            return None
        match_args, match_kwargs, segments = match
        # A key cannot be in unicode. 
        for key in match_kwargs.keys():
            if isinstance(key, unicode):
                value = match_kwargs[key]
                del match_kwargs[key]
                match_kwargs[key.encode("utf-8")] = value
        result = func(self, request, segments, *match_args, **match_kwargs)
        
        if result is None:
            return None
        elif isinstance(result, tuple):
            return result
        else:
            return result, segments

    def __call__(self, request):
        # Get the dispatchers for the request method.
        dispatchers = self.request_dispatchers.get(request.method)
        # No normal dispatchers for method found,
        if dispatchers is None:
            # Looking for a magic dispatcher
            dispatchers = self.request_dispatchers.get(ALL.method)
            # No magic dispatchers found either,
            # send 405 with list of allowed methods.
            if dispatchers is None:
                return http.method_not_allowed(', '.join(self.request_dispatchers))
        # Look up the best dispatcher
        dispatcher = _best_dispatcher(dispatchers, request)
        if dispatcher is not None:
            (callable, match) = dispatcher
            response = callable(self, request)
            # Try to autocomplete the content-type header if not set
            # explicitly.
            # If there's no accept from the client and there's only one
            # possible type from the match then use that as the best match.
            # Otherwise use mimeparse to work out what the best match was. If
            # the best match if not a wildcard then we know what content-type
            # should be.
            if isinstance(response, http.Response) and \
                    not response.headers.get('content-type'):
                accept = str(request.accept)
                if not accept and len(match['accept']) == 1:
                    best_match = match['accept'][0]
                else:
                    best_match = mimeparse.best_match(match['accept'], accept)
                if '*' not in best_match:
                    response.headers['content-type'] = best_match
            return response
        # No match, send 406
        return http.not_acceptable([('Content-Type', 'text/plain')], \
                                   '406 Not Acceptable')


def _best_dispatcher(dispatchers, request):
    """
    Find the best dispatcher for the request.
    """
    # Use content negotation to filter the dispatchers to an ordered list of
    # only those that match.
    if request.headers.get('content-type'):
        dispatchers = _filter_dispatchers_on_content_type(dispatchers, request)
    if request.headers.get('accept'):
        dispatchers = _filter_dispatchers_on_accept(dispatchers, request)
    # Return the best match or None
    if dispatchers:
        return dispatchers[0]
    else:
        return None

def _filter_dispatchers_on_content_type(dispatchers, request):
    # Build an ordered list of the supported types.
    supported = []
    for d in dispatchers:
        supported.extend(d[1]['content_type'])
    # Find the best type.
    best_match = mimeparse.best_match(supported, \
                                      str(request.headers['content-type']))
    # Return the matching dispatchers
    return [d for d in dispatchers if best_match in d[1]['content_type']]


def _filter_dispatchers_on_accept(dispatchers, request):
    # Build an ordered list of the supported types.
    supported = []
    for d in dispatchers:
        supported.extend(d[1]['accept'])
    # Find the best accept type
    best_match = mimeparse.best_match(supported, str(request.accept))
    # Return the matching dispatchers
    return [d for d in dispatchers if best_match in d[1]['accept']]


def child(matcher=None):
    """ Child decorator used for finding child resources """
    def decorator(func, matcher=matcher):
        # No matcher? Use the function name.
        if matcher is None:
            matcher = func.__name__
        # If the matcher is a string then create a TemplateChildMatcher in its
        # place.
        if isinstance(matcher, basestring):
            matcher = TemplateChildMatcher(matcher)
        # Annotate the function.
        setattr(func, _RESTISH_CHILD, matcher)
        # Return the function (unwrapped).
        return func
    return decorator


class TemplateChildMatcher(object):
    """
    A @child matcher that parses a template in the form /fixed/{dynamic}/fixed,
    extracting segments inside {} markers.
    """

    def __init__(self, pattern):
        self.pattern = pattern
        self._calc_score()
        self._compile()

    def _calc_score(self):
        """Return the score for this element"""
        def score(segment):
            if len(segment) >= 2 and segment.find('{') + segment.find('}') != \
                -2:
                return 0
            return 1
        segments = self.pattern.split('/')
        self.score = tuple(score(segment) for segment in segments)
    
    @staticmethod
    def _re_safe(s):
        """Make a safe expression to be used into a regexp"""
        for c in r'\+*()[].^|':
            s = s.replace(c, r'\%s' % c)
        return s

    def _build_regex(self):
        """Build the regex from the pattern"""
        def re_segments(segments):
            for segment in segments:
                if len(segment) >= 2 and segment.find("{") + \
                    segment.find("}") != -2:
                    prefix, rest = segment.split("{", 1)
                    var, suffix = rest.rsplit("}", 1)
                    pos = var.find(":")
                    # make them regexp safe
                    prefix = self._re_safe(prefix)
                    suffix = self._re_safe(suffix)
                    if ~pos:
                        regex = '%s(?P<%s>%s)%s' % (prefix,
                                                    var[:pos],
                                                    var[pos+1:],
                                                    suffix)
                    else:
                        regex = r'%s(?P<%s>[^/]+)%s' % (prefix,
                                                        var,
                                                        suffix)
                    yield regex
                else:
                    yield self._re_safe(segment)

        segments = self.pattern.split('/')
        self._count = len(segments)
        print '/'.join(re_segments(segments))
        return '/'.join(re_segments(segments))

    def _compile(self):
        """Compile the regexp to match segments"""
        self._regex = re.compile('^' + self._build_regex() + '$')

    def __call__(self, request, segments):
        match_segments, remaining_segments = \
                segments[:self._count], segments[self._count:]
        # Note: no need to use the url module to join the path segments here
        # because we want the unquoted and decoded segments.
        match_path = '/'.join(match_segments)
        match = self._regex.match(match_path)
        if not match:
            return None
        return [], match.groupdict(), remaining_segments


class AnyChildMatcher(object):
    """
    A @child matcher that will always match, returning to match args and the
    list of segments unchanged.
    """

    score = ()

    def __call__(self, request, segments):
        return [], {}, segments


any = AnyChildMatcher()


class MethodDecorator(object):
    """
    content negotition decorator base class. See DELETE, GET, PUT, POST
    """

    method = None

    def __init__(self, accept='*/*', content_type='*/*'):
        if not isinstance(accept, list):
            accept = [accept]
        if not isinstance(content_type, list):
            content_type = [content_type]
        accept = [_normalise_mimetype(a) for a in accept]
        content_type = [_normalise_mimetype(a) for a in content_type]
        self.match = {'accept': accept, 'content_type': content_type}

    def __call__(self, func):
        setattr(func, _RESTISH_METHOD, self.method)
        setattr(func, _RESTISH_MATCH, self.match)
        return func


class ALL(MethodDecorator):
    """ every kind of http methods """
    method = '*'

class DELETE(MethodDecorator):
    """ http DELETE method """
    method = 'DELETE'


class GET(MethodDecorator):
    """ http GET method """
    method = 'GET'


class POST(MethodDecorator):
    """ http POST method """
    method = 'POST'


class PUT(MethodDecorator):
    """ http PUT method """
    method = 'PUT'


def _normalise_mimetype(mimetype):
    """
    Expand any shortcut mimetype names into a full mimetype
    """
    if '/' in mimetype:
        return mimetype
    # Try mimetypes module, by extension.
    real = mimetypes.guess_type('filename.%s'%mimetype)[0]
    if real is not None:
        return real
    # Try extra extension mapping.
    real = SHORT_CONTENT_TYPE_EXTRA.get(mimetype)
    if real is not None:
        return real
    # Oh well.
    return mimetype

