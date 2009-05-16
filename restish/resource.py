"""
Base Resource class and associates methods for children and content negotiation
"""
import inspect
import mimetypes
import re
import mimeparse

from restish import http, url


_RESTISH_CHILD = "restish_child"
_RESTISH_METHOD = "restish_method"
_RESTISH_MATCH = "restish_match"
_RESTISH_CHILD_CLASS = "restish_child_class"


SHORT_CONTENT_TYPE_EXTRA = {
        'json': 'application/json',
        }

PYTHON_STRING_VARS = re.compile(r"%\(([^\)]+)\)s")

def child(matcher=None, klass=None, canonical=False):
    if klass is None and not isinstance(matcher, _metaResource):
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
    else:
        if klass is None:
            canonical = klass
            klass = matcher
            matcher = None
        
        def func(self, request, segments, *args, **kwargs):
            return klass(*args, **kwargs), segments
        
        if isinstance(matcher, basestring):
            matcher = TemplateChildMatcher(matcher, canonical)
        
        setattr(func, _RESTISH_CHILD, matcher)
        setattr(func, _RESTISH_CHILD_CLASS, klass)
        return func


def url_for(cls, *args, **kwargs):
    """
    Contruct an URL going up from the given resource class to the root.

    url_for(Klass, arg1="val1", arg2="val2")
    url_for(Klass, {"arg1":"val1", "arg2": "val2"})
    url_for(Klass, obj)
    """
    if isinstance(cls, basestring):
        classname = cls.lower()
        cls = Resource._resources.get(classname, None)
    
    # Some resource aren't in, like the root of the tree.
    # they will get "/"
    if cls is not None:
        return cls._url_for(*args, **kwargs)
    else:
        return Resource._url_for()


def redirect(fro, to=None):
    if not isinstance(fro, _metaResource) and not isinstance(to, _metaResource):
        def decorator(func):
            # you cannot alter a variable that sits outside the scope
            # so they are renamed
            if to is None:
                dest = fro
                orig = func.__name__
            else:
                dest = to
                orig = fro

            if type(dest) not in (list, tuple):
                dest = dest,
            
            # ignore original func
            new_func = lambda self, request, segments: http.found(request.application_url.child(*dest))
            setattr(new_func, _RESTISH_CHILD, TemplateChildMatcher(orig))
            return new_func
        return decorator
    else:
        if to is None:
            to = fro
            fro = None
        else:
            fro = TemplateChildMatcher(fro)
        
        def func(self, request, segments, **kwargs):
            return http.found(request.application_url + to._url_for(kwargs))

        setattr(func, _RESTISH_CHILD, fro)
        return func


class TemplateChildMatcher(object):
    """
    A @child matcher that parses a template in the form /fixed/{dynamic}/fixed,
    extracting segments inside {} markers.
    """
    SPLITTER = '/'
    MARKERS = '{', '}'
    
    def __init__(self, pattern, canonical=False):
        self.pattern = pattern
        self.canonical = canonical
        self._calc_score()
        self._compile()

    def _calc_score(self):
        """Return the score for this element"""
        def score(segment):
            if len(segment) >= 2 and (segment.find(self.MARKERS[0]) +
                                      segment.find(self.MARKERS[1]) != -2):
                return 0
            return 1
        segments = self.pattern.split(self.SPLITTER)
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
        return '/'.join(re_segments(segments))

    def _build_url(self):
        """Generate an URL from the matcher"""
        segments = self.pattern.split(self.SPLITTER)
        def re_segments(segments):
            for segment in segments:
                if len(segment) >= 2 and (segment.find(self.MARKERS[0]) +
                                          segment.find(self.MARKERS[1]) != -2):
                    prefix, rest = segment.split(self.MARKERS[0], 1)
                    var, suffix = rest.rsplit(self.MARKERS[1], 1)
                    pos = var.find(":")
                    if ~pos:
                        yield '%s%%(%s)s%s' % (prefix, var[:pos], suffix)
                    else:
                        yield '%s%%(%s)s%s' % (prefix, var, suffix)
                else:
                    yield segment
        
        return re_segments(segments)

    def _compile(self):
        """Compile the regexp to match segments"""
        self._regex = re.compile('^' + self._build_regex() + '$')
    
    def _url_for(self, obj=None, **kwargs):
        """Compile the URL with the given arguments.
        
        _url_for({arg: val, ...})
        _url_for(obj)
        _url_for(arg=val, ...)
        """
        template_url = self._build_url()
        if type(obj) is dict:
            kwargs = dict(kwargs, **obj)
            obj = None
        
        if obj is not None:
            segments = []
            for segment in template_url:
                keys = PYTHON_STRING_VARS.findall(segment)
                if keys:
                    for key in keys:
                        if hasattr(obj, key):
                            segments.append(segment % {key: getattr(obj, key)})
                        else:
                            raise KeyError(key, "url_for: key is missing")
                else:
                    segments.append(segment)
            return segments
        else:
            return [segment % kwargs for segment in template_url]

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
    """Every kind of http methods"""
    method = '*'


class DELETE(MethodDecorator):
    """http DELETE method"""
    method = 'DELETE'


class GET(MethodDecorator):
    """http GET method"""
    method = 'GET'


class POST(MethodDecorator):
    """http POST method"""
    method = 'POST'


class PUT(MethodDecorator):
    """http PUT method"""
    method = 'PUT'


class HEAD(MethodDecorator):
    """http HEAD method"""
    method = 'HEAD'

class OPTIONS(MethodDecorator):
    """http OPTIONS method"""
    method = 'OPTIONS'


class TRACE(MethodDecorator):
    """http TRACE method"""
    method = 'TRACE'

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
    annotation = _RESTISH_CHILD
    # Copy the super class's 'child_factories' list (if any) to this class.
    cls.child_factories = list(getattr(cls, 'child_factories', []))
    # A way to find the name of its childs quickly
    cls.child_matchers = {}
    # Complete the childs built using the declarative way
    for name, func in clsattrs.iteritems():
        # childs with no names
        if hasattr(func, annotation) and getattr(func, annotation, None) is None:
            setattr(func, annotation, TemplateChildMatcher(name))
        # childs with no daddies
        if hasattr(func, _RESTISH_CHILD_CLASS):
            child_cls = getattr(func, _RESTISH_CHILD_CLASS)
            # who's your daddy
            child_cls._parent = cls
            matcher = getattr(func, annotation, None)
            if child_cls not in cls.child_matchers or matcher.canonical:
                cls.child_matchers[child_cls] = matcher
                cls._resources[child_cls.__name__.lower()] = child_cls
    
    # Extend child_factories to include the ones found on this class.
    child_factories = _find_annotated_funcs(clsattrs, annotation)
    cls.child_factories.extend((getattr(f, annotation), f)
                               for f in child_factories)
    # Sort the child factories by score.
    cls.child_factories = sorted(cls.child_factories,
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

    _resources = {}

    def __init__(self, *args, **kwargs):
        pass
    
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
            if request.method == HEAD.method:
                # HEAD is (almost) GET
                dispatchers = self.request_dispatchers.get(GET.method)
                
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
                    not response.content_type:
                accept = str(request.accept)
                if not accept and len(match['accept']) == 1:
                    best_match = match['accept'][0]
                else:
                    best_match = mimeparse.best_match(match['accept'], accept)
                if '*' not in best_match:
                    response.content_type = best_match
            if request.method is HEAD.method:
                # Emptying a GET that has been called as a HEAD
                response.body = ''
            return response
        # No match, send 406
        return http.not_acceptable([('Content-Type', 'text/plain')], \
                                   '406 Not Acceptable')
    
    @classmethod
    def _url_for(cls, *args, **kwargs):
        """
        URL of this resource built using the given arguments
        """
        parents = []
                
        while hasattr(cls, '_parent'):
            segments = cls._parent.child_matchers.get(cls, None)._url_for(*args, **kwargs)
            segments.reverse()
            parents += segments
            cls = cls._parent
        if len(parents):
            parents.reverse()
        else:
            parents = ['']
        
        return url.URL('/').child(*parents)


def _best_dispatcher(dispatchers, request):
    """
    Find the best dispatcher for the request.
    """
    # Use content negotation to filter the dispatchers to an ordered list of
    # only those that match.
    if request.content_type is not "":
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
    best_match = mimeparse.best_match(supported, request.content_type)
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

