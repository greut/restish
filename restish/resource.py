"""
Base Resource class and associates methods for children and content negotiation
"""

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


def child(matcher=None, klass=None, canonical=False, with_parent=False):
    if klass is None and not isinstance(matcher, _metaResource):
        """ Child decorator used for finding child resources """
        def decorator(func, matcher=matcher):
            # No matcher? Use the function name.
            if matcher is None:
                matcher = func.__name__
            # If the matcher is a string then create a
            # TemplateChildMatcher in its place.
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
            if with_parent:
                kwargs["_parent"] = self
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

    def __repr__(self):
        return '<TemplateChildMatcher "%s">' % self.pattern

    def _calc_score(self):
        """Return the score for this element"""
        def score(segment):
            if len(segment) >= 2 and (segment.find(self.MARKERS[0]) +
                                      segment.find(self.MARKERS[1]) != -2):
                return 0
            return 1
        segments = self.pattern.split(self.SPLITTER)
        self.score = tuple(score(segment) for segment in segments)

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
                    prefix = re.escape(prefix)
                    suffix = re.escape(suffix)
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
                    yield re.escape(segment)

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
        wrapper = ResourceMethodWrapper(func)
        setattr(wrapper, _RESTISH_METHOD, self.method)
        setattr(wrapper, _RESTISH_MATCH, self.match)
        return wrapper


class ResourceMethodWrapper(object):
    """
    Wraps a @resource.GET etc -decorated function to ensure the function is
    only called with a matching request. If the request does not match then an
    HTTP error response is returned.

    Implementation note: The wrapper class is always added to decorated
    functions. However, the wrapper is discarded for Resource methods at the
    time the annotated methods are collected by the metaclass. This is because
    the Resource._call__ is already doing basically the same work, only it has
    a whole suite of dispatchers to worry about.
    """

    def __init__(self, func):
        self.func = func

    def __call__(self, request):
        # Extract annotations.
        method = getattr(self, _RESTISH_METHOD)
        match = getattr(self, _RESTISH_MATCH)
        # Check for correct method.
        if request.method != method:
            return http.method_not_allowed([method])
        # Look for a dispatcher.
        dispatcher = _best_dispatcher([(self.func, match)], request)
        if dispatcher is not None:
            return _dispatch(request, match, self.func)
        # No dispatcher.
        return http.not_acceptable([('Content-Type', 'text/plain')], \
                                   '406 Not Acceptable')


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
    real = mimetypes.guess_type('filename.%s' % mimetype)[0]
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
    # Collect the request handlers that *this* class adds first.
    request_dispatchers = {}
    for wrapper in _find_annotated_funcs(clsattrs, _RESTISH_METHOD):
        method = getattr(wrapper, _RESTISH_METHOD, None)
        match = getattr(wrapper, _RESTISH_MATCH)
        request_dispatchers.setdefault(method, []).append(
            (wrapper.func, match))
    # Append any handlers that were added by base classes.
    for method, dispatchers in getattr(cls, 'request_dispatchers', {}).iteritems():
        request_dispatchers.setdefault(method, []).extend(dispatchers)
    # Set the handlers on the class.
    cls.request_dispatchers = request_dispatchers


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
    
    funcs = (func for func in clsattrs.itervalues() \
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
            return _dispatch(request, match, lambda r: callable(self, r))
        # No match, send 406
        return http.not_acceptable([('Content-Type', 'text/plain')], \
                                   '406 Not Acceptable')

    @HEAD()
    def head(self, request):
        """
        Handle a HEAD request by calling the resource again as if a GET was
        sent and then discarding the content.

        This default HEAD behaviour works very well for dynamically generated
        content. However, it is not suitable for static content where the size
        is already known, e.g. large blobs stored in a database.

        In that scenario add a HEAD-decorated method to the application
        resource's class that includes a Content-Length header but no body.
        """
        request.method = 'GET'
        # Loop until we get an actual response to support resource forwarding.
        response = self(request)
        while not isinstance(response, http.Response):
            response = response(request)
        content_length = response.headers.get('content-length')
        response.body = ''
        if content_length is not None:
            response.headers['content-length'] = content_length
        return response

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


def _dispatch(request, match, func):
    response = func(request)
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


def _best_dispatcher(dispatchers, request):
    """
    Find the best dispatcher for the request.
    """
    # Use content negotation to filter the dispatchers to an ordered list of
    # only those that match.
    content_type = request.headers.get('content-type')
    if content_type:
        dispatchers = _filter_dispatchers_on_content_type(dispatchers,
                                                          str(content_type))
    accept = request.headers.get('accept')
    if accept:
        accept = accept.strip(', ') # Some clients send bad accept headers
        dispatchers = _filter_dispatchers_on_accept(dispatchers, accept)
    # Return the best match or None
    if dispatchers:
        return dispatchers[0]
    else:
        return None


def _filter_dispatchers_on_content_type(dispatchers, content_type):
    # Build an ordered list of the supported types.
    supported = []
    for d in dispatchers:
        supported.extend(d[1]['content_type'])
    # Find the best type.
    best_match = mimeparse.best_match(supported, content_type)
    # Return the matching dispatchers
    return [d for d in dispatchers if best_match in d[1]['content_type']]


def _filter_dispatchers_on_accept(dispatchers, accept):
    # Build an ordered list of the supported types.
    supported = []
    for d in dispatchers:
        supported.extend(d[1]['accept'])
    # Find the best accept type
    best_match = mimeparse.best_match(supported, accept)
    # Return the matching dispatchers
    return [d for d in dispatchers if best_match in d[1]['accept']]
