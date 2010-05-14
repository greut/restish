# -*- coding: utf-8 -*-

"""
Test resource behaviour.
"""

import unittest
import webtest

from restish import app, http, resource, templating, url


def make_app(root):
    return webtest.TestApp(app.RestishApp(root))


class TestResourceFunc(unittest.TestCase):

    def test_anything(self):
        def func(request):
            return http.ok([('Content-Type', 'text/plain')], 'Hello')
        response = make_app(func).get('/', status=200)
        assert response.body == 'Hello'
        response = make_app(func).post('/', status=200)
        assert response.body == 'Hello'

    def test_method_match(self):
        @resource.GET()
        def func(request):
            return http.ok([('Content-Type', 'text/plain')], 'Hello')
        response = make_app(func).get('/', status=200)
        assert response.body == 'Hello'
        response = make_app(func).post('/', status=405)

    def test_accept_match(self):
        @resource.GET(accept='text/plain')
        def func(request):
            return http.ok([], 'Hello')
        response = make_app(func).get('/', headers={'Accept': 'text/plain'}, status=200)
        assert response.body == 'Hello'
        response = make_app(func).get('/', headers={'Accept': 'text/html'}, status=406)


class TestResourceMetaclass(unittest.TestCase):

    def test_leaking_request_handlers(self):
        # Check that request handlers from a resource class do not leak into
        # a sibling class.
        class Base(resource.Resource):
            @resource.POST(accept='json')
            def POST(self, request):
                pass
        class Derived1(Base):
            pass
        class Derived2(Base):
            @resource.POST(accept='csv')
            def bulk_load_csv(self, request):
                pass
        assert len(Base.request_dispatchers['POST']) == 1
        assert len(Derived1.request_dispatchers['POST']) == 1
        assert len(Derived2.request_dispatchers['POST']) == 2

    def test_leaking_child_factories(self):
        # Check that child factories from a resource class do not leak into a
        # sibling class.
        class Base(resource.Resource):
            @resource.child()
            def foo(self, request, segments):
                pass
        class Derived1(Base):
            pass
        class Derived2(Base):
            @resource.child()
            def bar(self, request, segments):
                pass
        assert len(Base.child_factories) == 1
        assert len(Derived1.child_factories) == 1
        assert len(Derived2.child_factories) == 2

    def test_non_accumulation(self):
        # Check request handlers from base handlers are not duplicated during
        # request handler collection.
        class Base(resource.Resource):
            @resource.GET()
            def json(self, request):
                pass
        class Derived(Base):
            pass
        assert len(Derived.request_dispatchers['GET']) == 1


class TestResource(unittest.TestCase):
    
    def test_no_method_handler(self):
        make_app(resource.Resource()).get('/', status=405)

    def test_methods(self):
        class Resource(resource.Resource):
            @resource.HEAD()
            def HEAD(self, request):
                return http.ok([('Content-Type', 'text/plain')])
            @resource.GET()
            def GET(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'GET')
            @resource.POST()
            def POST(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'POST')
            @resource.PUT()
            def PUT(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'PUT')
            @resource.DELETE()
            def DELETE(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'DELETE')
        for method in ['GET', 'POST', 'PUT', 'DELETE']:
            app = make_app(Resource())
            response = getattr(app, method.lower())('/', status=200)
            assert response.body == method
        
        response = app.head("/", status=200)
        assert response.body == ""

    def test_all_methods(self):
        class Resource(resource.Resource):
            @resource.ALL()
            def all(self, request):
                if request.method == "DELETE":
                    return http.ok([('Content-Type', 'text/plain')],
                                   "THERE IS NO DELETE")
                else:
                    return http.ok([('Content-Type', 'text/plain')],
                                   request.method)

            @resource.POST()
            def post(self, request):
                return http.ok([('Content-Type', 'text/plain')],
                               "HERE IS THE POST")

        tests = [('GET', 'GET'),
                 ('POST', 'HERE IS THE POST'),
                 ('PUT', 'PUT'),
                 ('DELETE', 'THERE IS NO DELETE')
                ]
        
        A = make_app(Resource())
        for method, body  in tests:
            response = getattr(A, method.lower())("/", status=200)
            assert response.body == body

    def test_derived(self):
        class Base(resource.Resource):
            @resource.GET(accept='text')
            def text(self, request):
                return http.ok([], 'Base')
            @resource.GET(accept='html')
            def html(self, request):
                return http.ok([], '<p>Base</p>')
        class Derived(Base):
            @resource.GET(accept='html')
            def html(self, request):
                return http.ok([], '<p>Derived</p>')
            @resource.GET(accept='json')
            def json(self, request):
                return http.ok([], '"Derived"')
        app = make_app(Derived())
        assert app.get('/', headers={'Accept': 'text/plain'}, status=200).body == 'Base'
        assert app.get('/', headers={'Accept': 'text/html'}, status=200).body == '<p>Derived</p>'
        assert app.get('/', headers={'Accept': 'application/json'}, status=200).body == '"Derived"'

    def test_derived_specificity(self):
        class Base(resource.Resource):
            @resource.GET(accept='text/*')
            def text(self, request):
                return http.ok([('Content-Type', 'text/html')], 'Base')
        class Derived(Base):
            @resource.GET(accept='text/plain')
            def html(self, request):
                return http.ok([], 'Derived')
        app = make_app(Derived())
        assert app.get('/', headers={'Accept': 'text/plain'}, status=200).body == 'Derived'
        assert app.get('/', headers={'Accept': 'text/html'}, status=200).body == 'Base'

    def test_default_head(self):
        class Resource(resource.Resource):
            @resource.GET()
            def text(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'text')
        get_response = Resource()(http.Request.blank('/', environ={'REQUEST_METHOD': 'GET'}))
        head_response = Resource()(http.Request.blank('/', environ={'REQUEST_METHOD': 'HEAD'}))
        assert head_response.headers['content-length'] == get_response.headers['content-length']
        assert head_response.body == ''

    def test_specialised_head(self):
        class Resource(resource.Resource):
            @resource.GET()
            def text(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'text')
            @resource.HEAD()
            def head(self, request):
                return http.ok([('Content-Type', 'text/plain'), ('Content-Length', '100')], None)
        head_response = Resource()(http.Request.blank('/', environ={'REQUEST_METHOD': 'HEAD'}))
        assert head_response.headers['content-length'] == '100'
        assert head_response.body == ''
    
    def test_head_method(self):
        class Resource(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([('Content-Type', 'text/plain')],
                               request.method)
        
        environ = http.Request.blank('/').environ
        response = Resource()(http.Request(environ))
        assert response.body == "GET"

        environ = http.Request.blank('/', environ={"REQUEST_METHOD": "HEAD"}) \
                              .environ
        response = Resource()(http.Request(environ))
        assert response.body == ""


class TestChildLookup(unittest.TestCase):

    def test_404(self):
        class Resource(resource.Resource):
            pass
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/404', status=404)

    def test_matcher_404(self):
        class Resource(resource.Resource):
            @resource.child(resource.any)
            def child(self, request, segments):
                return
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/404', status=404)

    def test_nameless_child(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            @resource.child()
            def foo(self, request, segments):
                return self.__class__(self.segments + ['foo'])
            @resource.child('')
            def nameless_child(self, request, segments):
                return self.__class__(self.segments + [''])
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '/'.join(self.segments))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/foo/')
        assert R.status.startswith('200')
        assert R.body == 'foo/'
        R = webtest.TestApp(A).get('/foo//foo/foo///')
        assert R.status.startswith('200')
        assert R.body == 'foo//foo/foo///'

    def test_implicitly_named(self):
        def renderer(template, args, encoding=None):
            return args['page']

        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            
            @resource.child()
            def implicitly_named_child(self, request, segments):
                return self.__class__(self.segments + ['implicitly_named_child'])
            @resource.child()
            @templating.page('page')
            def implicitly_named_child_with_templating(self, request, segments):
                return {'page': 'implicitly_named_child_with_templating'}

            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '/'.join(self.segments))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/implicitly_named_child')
        assert R.status.startswith('200')
        assert R.body == 'implicitly_named_child'

        tests = [
                 ('/implicitly_named_child', 'implicitly_named_child'),
                 ('/implicitly_named_child_with_templating', 'implicitly_named_child_with_templating'),
                ]
        environ = {'restish.templating': templating.Templating(renderer)}
        
        A = make_app(Resource())
        for url, expected in tests:
            R = A.get(url, extra_environ=environ, status=200)
            assert R.body == expected
    
    def test_explicitly_named(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            @resource.child('explicitly_named_child')
            def find_me_a_child(self, request, segments):
                return self.__class__(self.segments + ['explicitly_named_child'])
            @resource.child(u'éxpliçítly_nämed_child_with_unicøde')
            def find_me_a_child_with_unicode(self, request, segments):
                return self.__class__(self.segments + ['explicitly_named_child_with_unicode'])
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '/'.join(self.segments))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/explicitly_named_child')
        assert R.status.startswith('200')
        assert R.body == 'explicitly_named_child'
        R = webtest.TestApp(A).get(url.join_path([u'éxpliçítly_nämed_child_with_unicøde']))
        assert R.status.startswith('200')
        assert R.body == 'explicitly_named_child_with_unicode'

    def test_segment_consumption(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            @resource.child()
            def first(self, request, segments):
                return self.__class__(self.segments + ['first'] + segments), []
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '/'.join(self.segments))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/first')
        assert R.status.startswith('200')
        assert R.body == 'first'
        R = webtest.TestApp(A).get('/first/second')
        assert R.status.startswith('200')
        assert R.body == 'first/second'
        R = webtest.TestApp(A).get('/first/a/b/c/d/e')
        assert R.status.startswith('200')
        assert R.body == 'first/a/b/c/d/e'

    def test_static_match(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            @resource.child('foo/bar')
            def static_child(self, request, segments):
                return self.__class__(self.segments + ['foo', 'bar'] + segments), []
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '/'.join(self.segments))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/foo/bar')
        assert R.status.startswith('200')
        assert R.body == 'foo/bar'
        R = webtest.TestApp(A).get('/foo/bar/a/b/c')
        assert R.status.startswith('200')
        assert R.body == 'foo/bar/a/b/c'

    def test_match_names_with_regex_chars(self):
        class Resource(resource.Resource):
            @resource.child('[0-9]*+')
            def static_child(self, request, segments):
                return http.ok([('Content-Type', 'text/plain')], 'static')
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/[0-9]*+')
        assert R.status.startswith('200')
        assert R.body == 'static'

    def test_dynamic_match(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[], args={}):
                self.segments = segments
                self.args = args
            @resource.child('users/{username}')
            def dynamic_child(self, request, segments, **kwargs):
                return self.__class__(self.segments + ['users', kwargs['username']] + segments, kwargs), []
            def __call__(self, request):
                body = '%r %r' % (self.segments, self.args)
                return http.ok([('Content-Type', 'text/plain')], body)
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/users/foo')
        assert R.status.startswith('200')
        assert R.body == "['users', u'foo'] {'username': u'foo'}"

    def test_any_match(self):
        class Resource(resource.Resource):
            def __init__(self, segments=[]):
                self.segments = segments
            @resource.child(resource.any)
            def any_child(self, request, segments):
                return self.__class__(self.segments + segments), []
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')], '%r' % (self.segments,))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/foo')
        assert R.status.startswith('200')
        assert R.body == "[u'foo']"

    def test_specificity(self):
        """
        Check the child match specificity.
        """
        class Capture(object):
            def __init__(self, segments):
                self.segments = segments
            def resource_child(self, request, segments):
                return self.__class__(self.segments+segments), []
            def __call__(self, request):
                return http.ok([('Content-Type', 'text/plain')],
                               '/'.join(self.segments))
        class Resource(resource.Resource):
            @resource.child('a/b/c')
            def _1(self, request, segments):
                return Capture(['a', 'b', 'c'])
            @resource.child('a/b/{c}')
            def _2(self, request, segments, c):
                return Capture(['a', 'b', '{c}'])
            @resource.child('a/{b}/c/{d}')
            def _3(self, request, segments, b, d):
                return Capture(['a', '{b}', 'c', '{d}'])
            @resource.child('a/b/{c}/{d}')
            def _4(self, request, segments, c, d):
                return Capture(['a', 'b', '{c}', '{d}'])
            @resource.child('a/{b}/{c}')
            def _5(self, request, segments, b, c):
                return Capture(['a', '{b}', '{c}'])
            @resource.child('a')
            def _6(self, request, segments):
                return Capture(['a'])
            @resource.child('{a}/b/c')
            def _7(self, request, segments, a):
                return Capture(['{a}','b','c'])
            @resource.child('a{b}c')
            def _8(self, request, segments, b):
                return Capture(['a{b}c'])
            @resource.child('.+([^0-9])*|\S')
            def _9(self, request, segments):
                return Capture(['regexp-like'])
            @resource.child('fixed/{dynamic}')
            def _10(self, request, segments, dynamic):
                return Capture(['fixed', '{dynamic}'])
            @resource.child(resource.any)
            def any(self, request, segments):
                return Capture(['<any>'])
        tests = [
                ('/a/b/c', 'a/b/c'),
                ('/a/b/foo', 'a/b/{c}'),
                ('/a/foo/c/bar', 'a/{b}/c/{d}'),
                ('/a/b/foo/bar', 'a/b/{c}/{d}'),
                ('/a/foo/bar', 'a/{b}/{c}'),
                ('/a', 'a'),
                ('/foo/b/c', '{a}/b/c'),
                ('/abc', 'a{b}c'),
                ('/.+([^0-9])*|\S', 'regexp-like'),
                ('/fixed/123/foo', 'fixed/{dynamic}/foo'),
                ('/foo', '<any>/foo'),
                ]
        A = app.RestishApp(Resource())
        for path, expected in tests:
            R = webtest.TestApp(A).get(path)
            assert R.body == expected
    
    def test_regex_match(self):
        class Resource(resource.Resource):
            @resource.child('{a:[0-9]+}')
            def number(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "number %(a)s" % kw)
            
            @resource.child('{a:[a-z]+}')
            def lower(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "lower %(a)s" % kw)
            
            @resource.child('{a:[A-Z]+}')
            def upper(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "upper %(a)s" % kw)

            @resource.child('{a:13{2}7!}')
            def leet(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "leet %(a)s" % kw)

            @resource.child('{a:_.+}/{b:.+}')
            def multiple(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "multiple %(a)s, %(b)s" % kw)

            @resource.child('{y:[0-9]{4}}/{m:[0-9]{2}}/{d:[0-9]{2}}')
            def date(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "date %(y)s %(m)s %(d)s" % kw)
            
            @resource.child('prefix-{id:[0-9]}')
            def prefixed(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "prefix %(id)s" % kw)

            @resource.child('{id:[0-9]}-suffix')
            def suffixed(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "suffix %(id)s" % kw)
            
            @resource.child('feeds/{type:atom|rss|rss2}.xml')
            def feeds(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "feed %(type)s" % kw)

            @resource.child(u'£+{user:[^£]+}')
            def users(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               u"user %(user)s" % kw)
        
        tests = [
                ('/123', 'number 123'),
                ('/abc', 'lower abc'),
                ('/ABC', 'upper ABC'),
                ('/1337!', 'leet 1337!'),
                ('/_a/b', 'multiple _a, b'),
                ('/2008/10/01', 'date 2008 10 01'),
                ('/prefix-1', 'prefix 1'),
                ('/1-suffix', 'suffix 1'),
                ('/feeds/rss.xml', 'feed rss'),
                ('/feeds/atom.xml', 'feed atom'),
                (url._quote(u'/£+yøan'.encode('utf-8')),
                 u'user yøan'.encode('utf-8')),
                ]

        A = app.RestishApp(Resource())
        for path, expected in tests:
            R = webtest.TestApp(A).get(path)
            assert R.body == expected
    
    def test_subtree_match(self):
        class Resource(resource.Resource):
            @resource.child()
            def a(self, request, segments):
                return A()

            @resource.child("b")
            def bb(self, request, segments):
                return B()

            @resource.child("{c:[a-z]{3,}}")
            def c(self, request, segments, **kw):
                return C(**kw)

        class Generic(resource.Resource):
            def __str__(self):
                return self.__class__.__name__

            @resource.child()
            def a(self, request, segments):
                return http.ok([('Content-Type', 'text/plain')],
                               "%s/a" % self)
            
            @resource.child("b")
            def bb(self, request, segments):
                return http.ok([('Content-Type', 'text/plain')],
                               "%s/b" % self)

            @resource.child("{c:[a-z]{3,}}")
            def c(self, request, segments, **kw):
                return http.ok([('Content-Type', 'text/plain')],
                               "%s/%s" % (self, kw["c"]))

        class A(Generic):
            pass

        class B(Generic):
            pass

        class C(Generic):
            def __init__(self, c):
                self.c = c

            def __str__(self):
                return self.c
        
        tests = [
                ('/a/a', 'A/a'),
                ('/a/b', 'A/b'),
                ('/a/abc', 'A/abc'),
                ('/b/a', 'B/a'),
                ('/b/b', 'B/b'),
                ('/b/abc', 'B/abc'),
                ('/abc/a', 'abc/a'),
                ('/abc/b', 'abc/b'),
                ('/abc/abc', 'abc/abc'),
                ]

        App = app.RestishApp(Resource())
        for path, expected in tests:
            R = webtest.TestApp(App).get(path)
            assert R.body == expected


    def test_unquoted(self):
        """
        Check match args are unquoted.
        """
        class Resource(resource.Resource):
            def __init__(self, match=None):
                self.match = match
            @resource.child('{match}')
            def child(self, request, segments, match):
                return Resource(match)
            @resource.GET()
            def GET(self, request):
                return http.ok([('Content-Type', 'text/plain')], self.match.encode('utf-8'))
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/%C2%A3')
        assert R.body == '£'

    def test_child_is_a_response(self):
        class Resource(resource.Resource):
            @resource.child()
            def foo(self, request, segments):
                return http.ok([('Content-Type', 'text/plain')], 'foobar')

        # Check a leaf child (no more segments).
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/foo')
        assert R.body == 'foobar'
        # Check a branch child (additional segments)
        A = app.RestishApp(Resource())
        R = webtest.TestApp(A).get('/foo/bar')
        assert R.body == 'foobar'

    def test_root_is_a_response(self):
        A = app.RestishApp(http.ok([('Content-Type', 'text/plain')], 'foobar'))
        R = webtest.TestApp(A).get('/foo')
        assert R.body == 'foobar'

    def _test_custom_match(self):
        self.fail()


class TestAcceptContentNegotiation(unittest.TestCase):

    def test_no_match(self):
        class Resource(resource.Resource):
            @resource.GET(accept='text/json')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
        response = make_app(Resource()).get('/',
                                            headers={'Accept': 'text/plain'},
                                            status=406)

    def test_implicit_content_type(self):
        """
        Test that the content type is added automatically.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/html')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
        response = make_app(Resource()).get('/')
        assert response.headers['Content-Type'] == 'text/html'

    def test_implicit_content_type_not_on_partial_mimetype(self):
        """
        Test that a match on mime type group, e.g. */*, text/*, etc does not
        automatically add the content type.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/*')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
        # XXX Don't use webtest here because its lint-style check for a
        # Content-Type header gets in the way of the purpose of the test.
        environ = http.Request.blank('/').environ
        response = Resource()(http.Request(environ))
        assert response.headers.get('Content-Type') is None

    def test_explicit_content_type(self):
        """
        Test that the content type is not added automatically if the resource
        sets it.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/html')
            def html(self, request):
                return http.ok([('Content-Type', 'text/plain')], '<p>Hello!</p>')
        response = make_app(Resource()).get('/')
        assert response.headers['Content-Type'] == 'text/plain'

    def test_no_accept(self):
        """
        Test generic GET matches request from client that does not send an
        Accept header.
        """
        class Resource(resource.Resource):
            @resource.GET()
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], "<html />")
        response = make_app(Resource()).get('/', status=200)
        assert response.headers['Content-Type'] == 'text/html'

    def test_empty_accept(self):
        """
        Check an empty "Accept" header is ignored.
        """
        class Resource(resource.Resource):
            @resource.GET()
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], "<html />")
        response = make_app(Resource()).get('/', headers=[('Accept', '')], status=200)
        assert response.headers['Content-Type'] == 'text/html'

    def test_accept_match(self):
        """
        Test that an accept'ing request is matched even if there's a generic
        handler.
        """
        class Resource(resource.Resource):
            @resource.GET()
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], "<html />")
            @resource.GET(accept='application/json')
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], "{}")
        make_app(Resource()).get('/', headers=[('Accept', 'application/json')], status=200)

    def test_accept_non_match(self):
        """
        Test that a non-accept'ing request is matched when there's an
        accept-ing handler too.
        """
        class Resource(resource.Resource):
            @resource.GET()
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], "<html />")
            @resource.GET(accept='application/json')
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], "{}")
        response = make_app(Resource()).get('/', headers=[('Accept', 'text/html')], status=200)
        assert response.headers['Content-Type'] == 'text/html'

    def test_default_match(self):
        """
        Test that a client that does not send an Accept header gets a
        consistent response.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='html')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
            @resource.GET(accept='json')
            def json(self, request):
                return http.ok([], '"Hello!"')
        response = make_app(Resource()).get('/', status=200)
        assert response.headers['Content-Type'] == 'text/html'

    def test_no_subtype_match(self):
        """
        Test that something/* accept matches are found.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/*')
            def html(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'Hello!')
        response = make_app(Resource()).get('/', headers={'Accept': 'text/plain'}, status=200)
        assert response.headers['Content-Type'] == 'text/plain'

    def test_quality(self):
        """
        Test that a client's accept quality is honoured.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/html')
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], '<p>Hello!</p>')
            @resource.GET(accept='text/plain')
            def plain(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'Hello!')
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html;q=0.9,text/plain'})
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter, ['Hello!'])
        response = make_app(Resource()).get('/', headers={'Accept': 'text/plain,text/html;q=0.9'})
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter, ['Hello!'])
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html;q=0.4,text/plain;q=0.5'})
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter, ['Hello!'])
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html;q=0.5,text/plain;q=0.4'})
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'
        self.assertEquals(response.app_iter, ['<p>Hello!</p>'])

    def test_specificity(self):
        """
        Check that more specific mime types are matched in preference to *
        matches.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='html')
            def bbb(self, request):
                return http.ok([('Content-Type', 'text/html')], '')
            @resource.GET(accept='json')
            def aaa(self, request):
                return http.ok([('Content-Type', 'application/json')], '')
        response = make_app(Resource()).get('/', headers={'Accept': '*/*, application/json, text/javascript'})
        self.assertEquals(response.status, "200 OK")
        self.assertEquals(response.headers['Content-Type'], 'application/json')

    def test_no_subtype_match_2(self):
        """
        Test that something/* accept matches are found, when there's also a
        '*/*' match,
        """
        class Resource(resource.Resource):
            @resource.GET()
            def anything(self, request):
                return http.ok([('Content-Type', 'text/html')], '<p>Hello!</p>')
            @resource.GET(accept='text/*')
            def html(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'Hello!')
        response = make_app(Resource()).get('/', headers={'Accept': 'text/plain'})
        self.assertEquals(response.status, "200 OK")
        self.assertEquals(response.headers['Content-Type'], 'text/plain')
        self.assertEquals(response.app_iter, ['Hello!'])

        response = make_app(Resource()).get('/', headers={'Accept': 'application/xml'})
        self.assertEquals(response.status, "200 OK")
        self.assertEquals(response.headers['Content-Type'], 'text/html')
        self.assertEquals(response.app_iter, ['<p>Hello!</p>'])


class TestContentTypeContentNegotiation(unittest.TestCase):

    def test_any(self):
        """
        Check that no 'content_type' matches anything, i.e. '*/*'.
        """
        class Resource(resource.Resource):
            @resource.POST()
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json'},
                                             status=200)
        assert response.body == 'json'

    def test_simple(self):
        """
        Check that a basic 'content_type' match works.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type='application/json')
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json'},
                                             status=200)
        assert response.body == 'json'

    def test_short_list(self):
        """
        Check that a list of short types is ok.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json'},
                                             status=200)
        assert response.body == 'json'

    def test_match(self):
        """
        Check that different handlers are used for different content types.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
            @resource.POST(content_type=['xml'])
            def xml(self, request):
                return http.ok([('Content-Type', 'application/xml')], 'xml')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json'},
                                             status=200)
        assert response.body == 'json'
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/xml'},
                                             status=200)
        assert response.body == 'xml'

    def test_no_match(self):
        """
        Check that a match isn't always found.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/xml'},
                                             status=406)

    def test_specificity(self):
        """
        Check that the more specific handler is used.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type='image/*')
            def image_any(self, request):
                return http.ok([('Content-Type', 'image/png')], 'image/*')
            @resource.POST(content_type='image/png')
            def image_png(self, request):
                return http.ok([('Content-Type', 'image/png')], 'image/png')
            @resource.POST()
            def anything(self, request):
                return http.ok([('Content-Type', 'image/png')], '*/*')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'image/png'},
                                             status=200)
        assert response.body == 'image/png'
        response = make_app(Resource()).post('/', headers={'Content-Type': 'image/jpeg'},
                                             status=200)
        assert response.body == 'image/*'
        response = make_app(Resource()).post('/', headers={'Content-Type': 'text/plain'},
                                             status=200)
        assert response.body == '*/*'

    def test_empty(self):
        """
        Check that an empty 'content_type' is treated as no content type.

        Not sure if it's webob that's setting the content type to '' but,
        AFAICT, my browser isn't sending it. Whatever, let's make sure we don't
        just keel over.
        """
        class Resource(resource.Resource):
            @resource.POST()
            def json(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json')
        response = make_app(Resource()).post('/', headers={'Content-Type': ''}, status=200)
        assert response.body == 'json'

    def test_content_type_and_accept(self):
        """
        Check that various combinations of content_type and accept matches are ok.
        """
        class Resource(resource.Resource):
            @resource.POST(accept='json', content_type='json')
            def json_in_json_out(self, request):
                return http.ok([('Content-Type', 'application/json')], 'json_in_json_out')
            @resource.POST(accept='html', content_type='json')
            def json_in_html_out(self, request):
                return http.ok([], 'json_in_html_out')
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json', 'Accept': 'text/html'}, status=200)
        assert response.headers['Content-Type'] == 'text/html'
        assert response.body == 'json_in_html_out'
        response = make_app(Resource()).post('/', headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, status=200)
        assert response.headers['Content-Type'] == 'application/json'
        assert response.body == 'json_in_json_out'


class TestAcceptLists(unittest.TestCase):

    def test_match(self):
        class Resource(resource.Resource):
            @resource.GET(accept=['text/html', 'application/xhtml+xml'])
            def html(self, request):
                return http.ok([], '<html />')
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html'})
        assert response.status == "200 OK"
        response = make_app(Resource()).get('/', headers={'Accept': 'application/xhtml+xml'})
        assert response.status == "200 OK"

    def test_auto_content_type(self):
        class Resource(resource.Resource):
            @resource.GET(accept=['text/html', 'application/xhtml+xml'])
            def html(self, request):
                return http.ok([], '<html />')
        # Check specific accept type.
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html'})
        assert response.headers['content-type'] == 'text/html'
        # Check other specific accept type.
        response = make_app(Resource()).get('/', headers={'Accept': 'application/xhtml+xml'})
        assert response.headers['content-type'] == 'application/xhtml+xml'
        # Check the server's first accept match type is used if the client has
        # no strong preference whatever order the accept header lists types.
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html,application/xhtml+xml'})
        assert response.headers['content-type'] == 'text/html'
        response = make_app(Resource()).get('/', headers={'Accept': 'application/xhtml+xml,text/html'})
        assert response.headers['content-type'] == 'text/html'
        # Client accepts both but prefers one.
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html,application/xhtml+xml;q=0.9'})
        assert response.headers['content-type'] == 'text/html'
        # Client accepts both but prefers other.
        response = make_app(Resource()).get('/', headers={'Accept': 'text/html;q=0.9,application/xhtml+xml'})
        assert response.headers['content-type'] == 'application/xhtml+xml'


class TestShortAccepts(unittest.TestCase):

    def test_single(self):
        """
        Check that short types known to Python's mimetypes module are expanded.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='html')
            def html(self, request):
                return http.ok([], "<html />")
        response = make_app(Resource()).get('/', headers=[('Accept', 'text/html')])
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'

    def test_extra(self):
        """
        Check that short types added by restish are expanded.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='json')
            def json(self, request):
                return http.ok([], "{}")
        response = make_app(Resource()).get('/', headers=[('Accept', 'application/json')])
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'application/json'

    def test_unknown(self):
        """
        Check that unknown short types are not expanded and are still used.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='unknown')
            def unknown(self, request):
                return http.ok([], "{}")
        response = make_app(Resource()).get('/')
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'unknown'


class TestRedirectTo(unittest.TestCase):

    def test_full(self):
        class Resource(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "resource")

            @resource.redirect("foo", "bar")
            def foo(self, request):
                """Redirect to bar"""
            
            @resource.redirect("bar")
            def foo2(self, request):
                """Redirect to bar"""

            @resource.redirect("spam/or/eggs", ("spam", "and", "eggs"))
            def spam_or_eggs(self, request):
                """Redirect to spam *and* eggs"""

            @resource.child()
            def bar(self, request, segments):
                return http.ok([("Content-Type", "text/plain")],
                               "bar")

            @resource.child("spam/and/eggs")
            def spam_and_eggs(self, request, segments):
                return http.ok([("Content-Type", "text/plain")],
                               "spam")


        app = make_app(Resource())
        
        R = app.get("/", status=200)
        assert R.body == 'resource'
        
        R = app.get("/bar", status=200)
        assert R.body == 'bar'
        
        R = app.get("/foo", status=302) 
        R = app.get("/foo2", status=302)
        
        R = app.get("/spam/and/eggs", status=200)
        assert R.body == 'spam'
        
        R = app.get("/spam/or/eggs", status=302)


class TestDeclarative(object):

    def test_sample(self):
        class Bar2(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "bar")

        class Spam2(resource.Resource):
            def __init__(self, id, _parent):
                self.id = id
                self.parent = _parent

            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "%s %s" % (self.parent.foo, self.id))

        class Resource2(resource.Resource):
            def __init__(self, foo):
                self.foo = foo

            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "resource")

            foo = resource.redirect(Bar2)
            foo2 = resource.redirect("foo2", Bar2)
            bar = resource.child(Bar2)

            spum = resource.redirect("spum{id}", Spam2)
            spam = resource.child("spam{id}", Spam2, with_parent=True)

        app = make_app(Resource2("who's your daddy"))
        
        R = app.get("/", status=200)
        assert R.body == 'resource'

        R = app.get("/bar", status=200)
        assert R.body == 'bar'
        
        R = app.get("/foo", status=302)
        R = app.get("/foo2", status=302)
        
        R = app.get("/spam42", status=200)
        assert R.body == 'who\'s your daddy 42'
        
        R = app.get("/spum42", status=302)
        assert R.headers["location"].startswith('http://')
        assert R.headers["location"].endswith('/spam42')
'''
    def test_sample2(self):
        class Bar2(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "bar")

        class Spam2(resource.Resource):
            def __init__(self, id, _parent):
                self.id = id
                self.parent = _parent

            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "%s %s" % (self.parent.foo, self.id))

        class Resource2(resource.Resource):
            def __init__(self, foo):
                self.foo = foo

            @resource.GET()
            def get(self, request):
                return http.ok([("Content-Type", "text/plain")],
                               "resource")

            foo = resource.redirect(Bar2)
            foo2 = resource.redirect("foo2", Bar2)
            bar = resource.child2(Bar2)

            spum = resource.redirect("spum{id}", Spam2)
            spam = resource.child2("spam{id}", Spam2, with_parent=True)

        app = make_app(Resource2("who's your daddy"))
        
        R = app.get("/", status=200)
        assert R.body == 'resource'

        R = app.get("/bar", status=200)
        assert R.body == 'bar'
        
        R = app.get("/foo", status=302)
        R = app.get("/foo2", status=302)
        
        R = app.get("/spam42", status=200)
        assert R.body == 'who\'s your daddy 42'
        
        R = app.get("/spum42", status=302)
        assert R.headers["location"].startswith('http://')
        assert R.headers["location"].endswith('/spam42')
'''

if __name__ == '__main__':
    unittest.main()

