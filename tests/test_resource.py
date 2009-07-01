# -*- coding: utf-8 -*-

"""
Test resource behaviour.
"""

import unittest

from restish import app, http, resource, templating, url
from restish.util import wsgi_out


class TestResourceFunc(unittest.TestCase):

    def test_anything(self):
        def func(request):
            return http.ok([('Content-Type', 'text/plain')], 'Hello')
        request = http.Request.blank('/', environ={'REQUEST_METHOD': 'GET'})
        response = func(http.Request(request.environ))
        assert response.status == '200 OK'
        assert response.body == 'Hello'
        request = http.Request.blank('/', environ={'REQUEST_METHOD': 'POST'})
        response = func(http.Request(request.environ))
        assert response.status == '200 OK'
        assert response.body == 'Hello'

    def test_method_match(self):
        @resource.GET()
        def func(request):
            return http.ok([('Content-Type', 'text/plain')], 'Hello')
        request = http.Request.blank('/', environ={'REQUEST_METHOD': 'GET'})
        response = func(http.Request(request.environ))
        assert response.status == '200 OK'
        assert response.body == 'Hello'
        request = http.Request.blank('/', environ={'REQUEST_METHOD': 'POST'})
        response = func(http.Request(request.environ))
        assert response.status == '405 Method Not Allowed'

    def test_accept_match(self):
        @resource.GET(accept='text/plain')
        def func(request):
            return http.ok([], 'Hello')
        request = http.Request.blank('/', headers={'Accept': 'text/plain'})
        response = func(http.Request(request.environ))
        assert response.status == '200 OK'
        assert response.body == 'Hello'
        request = http.Request.blank('/', headers={'Accept': 'text/html'})
        response = func(http.Request(request.environ))
        assert response.status == '406 Not Acceptable'


class TestResource(unittest.TestCase):
    
    def test_no_method_handler(self):
        res = resource.Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
        assert response.status.startswith("405")

    def test_methods(self):
        class Resource(resource.Resource):
            @resource.HEAD()
            def HEAD(self, request):
                return http.ok([])
            @resource.GET()
            def GET(self, request):
                return http.ok([], 'GET')
            @resource.POST()
            def POST(self, request):
                return http.ok([], 'POST')
            @resource.PUT()
            def PUT(self, request):
                return http.ok([], 'PUT')
            @resource.DELETE()
            def DELETE(self, request):
                return http.ok([], 'DELETE')
        for method in ['GET', 'POST', 'PUT', 'DELETE', 'HEAD']:
            environ = http.Request.blank('/',
                    environ={'REQUEST_METHOD': method},
                    headers={'Accept': 'text/html'}).environ
            response = Resource()(http.Request(environ))
            assert response.status == "200 OK"
            if method is not 'HEAD':
                assert response.body == method
            else:
                assert response.body == ''

    def test_all_methods(self):
        class Resource(resource.Resource):
            @resource.ALL()
            def all(self, request):
                if request.method == "DELETE":
                    return http.ok([], "THERE IS NO DELETE")
                else:
                    return http.ok([], request.method)

            @resource.POST()
            def post(self, request):
                return http.ok([], "HERE IS THE POST")

        tests = [('GET', 'GET'),
                 ('POST', 'HERE IS THE POST'),
                 ('PUT', 'PUT'),
                 ('DELETE', 'THERE IS NO DELETE')
                ]
        
        for method, body  in tests:
            environ = http.Request.blank('/',
                    environ={"REQUEST_METHOD": method}).environ
            response = Resource()(http.Request(environ))
            assert response.status == "200 OK"
            assert response.body == body
    
    def test_head_method(self):
        class Resource(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], request.method)
        
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
        R = wsgi_out(A, http.Request.blank('/404').environ)
        assert R['status'].startswith('404')

    def test_matcher_404(self):
        class Resource(resource.Resource):
            @resource.child(resource.any)
            def child(self, request, segments):
                return
        A = app.RestishApp(Resource())
        R = wsgi_out(A, http.Request.blank('/404').environ)
        assert R['status'].startswith('404')

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
        R = wsgi_out(A, http.Request.blank('/foo/').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'foo/'
        R = wsgi_out(A, http.Request.blank('/foo//foo/foo///').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'foo//foo/foo///'
    
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

        tests = [
                 ('/implicitly_named_child', 'implicitly_named_child'),
                 ('/implicitly_named_child_with_templating', 'implicitly_named_child_with_templating'),
                ]
        environ = {'restish.templating': templating.Templating(renderer)}
        
        A = app.RestishApp(Resource())
        for url, expected in tests:
            _environ = http.Request.blank(url, environ).environ
            R = wsgi_out(A, _environ)
            #print R, "\n", R["body"], "\n", expected
            assert R['status'].startswith('200')
            assert R['body'] == expected, expected
    
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
        R = wsgi_out(A, http.Request.blank('/explicitly_named_child').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'explicitly_named_child'
        R = wsgi_out(A, http.Request.blank(url.join_path([u'éxpliçítly_nämed_child_with_unicøde'])).environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'explicitly_named_child_with_unicode'
    
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
        R = wsgi_out(A, http.Request.blank('/first').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'first'
        R = wsgi_out(A, http.Request.blank('/first/second').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'first/second'
        R = wsgi_out(A, http.Request.blank('/first/a/b/c/d/e').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'first/a/b/c/d/e'

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
        R = wsgi_out(A, http.Request.blank('/foo/bar').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'foo/bar'
        R = wsgi_out(A, http.Request.blank('/foo/bar/a/b/c').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'foo/bar/a/b/c'

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
        R = wsgi_out(A, http.Request.blank('/users/foo').environ)
        assert R['status'].startswith('200')
        assert R['body'] == "['users', u'foo'] {'username': u'foo'}"

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
        R = wsgi_out(A, http.Request.blank('/foo').environ)
        assert R['status'].startswith('200')
        assert R['body'] == "[u'foo']"
        
    def test_specificity(self):
        """
        Check the child match specificity.
        """
        def make_resource(body):
            def resource(request):
                return http.ok([], body)
            return resource
        class Resource(resource.Resource):
            @resource.child('a/b/c')
            def _1(self, request, segments):
                return make_resource('a/b/c'), []
            @resource.child('a/b/{c}')
            def _2(self, request, segments, c):
                return make_resource('a/b/{c}'), []
            @resource.child('a/{b}/c/{d}')
            def _3(self, request, segments, b, d):
                return make_resource('a/{b}/c/{d}'), []
            @resource.child('a/b/{c}/{d}')
            def _4(self, request, segments, c, d):
                return make_resource('a/b/{c}/{d}'), []
            @resource.child('a/{b}/{c}')
            def _5(self, request, segments, b, c):
                return make_resource('a/{b}/{c}'), []
            @resource.child('a')
            def _6(self, request, segments):
                return make_resource('a'), []
            @resource.child('{a}/b/c')
            def _7(self, request, segments, a):
                return make_resource('{a}/b/c'), []
            @resource.child('a{b}c')
            def _8(self, request, segments, b):
                return make_resource('a{b}c'), []
            @resource.child('.+([^0-9])*|\S')
            def _9(self, request, segments):
                return make_resource('regexp-like'), []
            @resource.child(resource.any)
            def any(self, request, segments):
                return make_resource('any'), []
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
                ('/foo', 'any'),
                ]
        A = app.RestishApp(Resource())
        for path, expected in tests:
            R = wsgi_out(A, http.Request.blank(path).environ)
            assert R['body'] == expected, expected
    
    def test_regex_match(self):
        class Resource(resource.Resource):
            @resource.child('{a:[0-9]+}')
            def number(self, request, segments, **kw):
                return http.ok([], "number %(a)s" % kw)
            
            @resource.child('{a:[a-z]+}')
            def lower(self, request, segments, **kw):
                return http.ok([], "lower %(a)s" % kw)
            
            @resource.child('{a:[A-Z]+}')
            def upper(self, request, segments, **kw):
                return http.ok([], "upper %(a)s" % kw)

            @resource.child('{a:13{2}7!}')
            def leet(self, request, segments, **kw):
                return http.ok([], "leet %(a)s" % kw)

            @resource.child('{a:_.+}/{b:.+}')
            def multiple(self, request, segments, **kw):
                return http.ok([], "multiple %(a)s, %(b)s" % kw)

            @resource.child('{y:[0-9]{4}}/{m:[0-9]{2}}/{d:[0-9]{2}}')
            def date(self, request, segments, **kw):
                return http.ok([], "date %(y)s %(m)s %(d)s" % kw)
            
            @resource.child('prefix-{id:[0-9]}')
            def prefixed(self, request, segments, **kw):
                return http.ok([], "prefix %(id)s" % kw)

            @resource.child('{id:[0-9]}-suffix')
            def suffixed(self, request, segments, **kw):
                return http.ok([], "suffix %(id)s" % kw)
            
            @resource.child('feeds/{type:atom|rss|rss2}.xml')
            def feeds(self, request, segments, **kw):
                return http.ok([], "feed %(type)s" % kw)

            @resource.child(u'£+{user:[^£]+}')
            def users(self, request, segments, **kw):
                return http.ok([], u"user %(user)s" % kw)
        
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
                (url._quote(u'/£+yøan'.encode('utf-8')), u'user yøan'),
                ]

        A = app.RestishApp(Resource())
        for path, expected in tests:
            R = wsgi_out(A, http.Request.blank(path).environ)
            assert R['body'] == expected, "body: %s" % expected
    
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
                return http.ok([], "%s/a" % self)
            
            @resource.child("b")
            def bb(self, request, segments):
                return http.ok([], "%s/b" % self)

            @resource.child("{c:[a-z]{3,}}")
            def c(self, request, segments, **kw):
                return http.ok([], "%s/%s" % (self, kw["c"]))

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
            R = wsgi_out(App, http.Request.blank(path).environ)
            assert R['body'] == expected

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
                return http.ok([], self.match.encode('utf-8'))
        A = app.RestishApp(Resource())
        R = wsgi_out(A, http.Request.blank('/%C2%A3').environ)
        assert R['body'] == '£'

    def test_child_is_a_response(self):
        class Resource(resource.Resource):
            @resource.child()
            def foo(self, request, segments):
                return http.ok([], 'foobar')

        # Check a leaf child (no more segments).
        A = app.RestishApp(Resource())
        R = wsgi_out(A, http.Request.blank('/foo').environ)
        assert R['body'] == 'foobar'
        # Check a branch child (additional segments)
        A = app.RestishApp(Resource())
        R = wsgi_out(A, http.Request.blank('/foo/bar').environ)
        assert R['body'] == 'foobar'

    def test_root_is_a_response(self):
        A = app.RestishApp(http.ok([], 'foobar'))
        R = wsgi_out(A, http.Request.blank('/foo').environ)
        assert R['body'] == 'foobar'

    def _test_custom_match(self):
        self.fail()


class TestAcceptContentNegotiation(unittest.TestCase):

    def test_no_match(self):
        class Resource(resource.Resource):
            @resource.GET(accept='text/json')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': 'text/plain'}).environ
        response = res(http.Request(environ))
        assert response.status.startswith("406")

    def test_implicit_content_type(self):
        """
        Test that the content type is added automatically.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/html')
            def html(self, request):
                return http.ok([], '<p>Hello!</p>')
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'

    def test_empty_accept(self):
        """
        Check an empty "Accept" header is ignore.
        """
        class Resource(resource.Resource):
            @resource.GET()
            def html(self, request):
                return http.ok([('Content-Type', 'text/html')], "<html />")
        res = Resource()
        environ = http.Request.blank('/', headers=[('Accept', '')]).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'
        res = Resource()

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
        res = Resource()
        environ = http.Request.blank('/', headers=[('Accept', 'application/json')]).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"

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
        res = Resource()
        environ = http.Request.blank('/', headers=[('Accept', 'text/html')]).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
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
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'

    def test_no_subtype_match(self):
        """
        Test that something/* accept matches are found.
        """
        class Resource(resource.Resource):
            @resource.GET(accept='text/*')
            def html(self, request):
                return http.ok([('Content-Type', 'text/plain')], 'Hello!')
        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': 'text/plain'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
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
        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': 'text/html;q=0.9,text/plain'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter,['Hello!'])
        environ = http.Request.blank('/', headers={'Accept': 'text/plain,text/html;q=0.9'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter,['Hello!'])
        environ = http.Request.blank('/', headers={'Accept': 'text/html;q=0.4,text/plain;q=0.5'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/plain'
        self.assertEquals(response.app_iter,['Hello!'])
        environ = http.Request.blank('/', headers={'Accept': 'text/html;q=0.5,text/plain;q=0.4'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'
        self.assertEquals(response.app_iter,['<p>Hello!</p>'])

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
        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': '*/*, application/json, text/javascript'}).environ
        response = res(http.Request(environ))
        self.assertEquals(response.status,"200 OK")
        self.assertEquals(response.headers['Content-Type'],'application/json')

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
        res = Resource()
        req = http.Request.blank('/', headers={'Accept': 'text/plain'})
        req.accept = 'text/plain'
        response = res(req)
        self.assertEquals(response.status,"200 OK")
        self.assertEquals(response.headers['Content-Type'],'text/plain')
        self.assertEquals(response.app_iter,['Hello!'])

        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': 'application/xml'}).environ
        response = res(http.Request(environ))
        self.assertEquals(response.status,"200 OK")
        self.assertEquals(response.headers['Content-Type'],'text/html')
        self.assertEquals(response.app_iter,['<p>Hello!</p>'])


class TestContentTypeContentNegotiation(unittest.TestCase):

    def test_any(self):
        """
        Check that no 'content_type' matches anything, i.e. '*/*'.
        """
        class Resource(resource.Resource):
            @resource.POST()
            def json(self, request):
                return http.ok([], 'json')
        res = Resource()
        response = res(self._request('application/json'))
        assert response.status == "200 OK"
        assert response.body == 'json'

    def test_simple(self):
        """
        Check that a basic 'content_type' match works.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type='application/json')
            def json(self, request):
                return http.ok([], 'json')
        res = Resource()
        response = res(self._request('application/json'))
        assert response.status == "200 OK"
        assert response.body == 'json'

    def test_short_list(self):
        """
        Check that a list of short types is ok.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([], 'json')
        res = Resource()
        response = res(self._request('application/json'))
        assert response.status == "200 OK"
        assert response.body == 'json'

    def test_match(self):
        """
        Check that different handlers are used for different content types.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([], 'json')
            @resource.POST(content_type=['xml'])
            def xml(self, request):
                return http.ok([], 'xml')
        res = Resource()
        response = res(self._request('application/json'))
        assert response.status == "200 OK"
        assert response.body == 'json'
        response = res(self._request('application/xml'))
        assert response.status == "200 OK"
        assert response.body == 'xml'

    def test_no_match(self):
        """
        Check that a match isn't always found.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type=['json'])
            def json(self, request):
                return http.ok([], 'json')
        res = Resource()
        response = res(self._request('application/xml'))
        assert response.status.startswith('406')

    def test_specificity(self):
        """
        Check that the more specific handler is used.
        """
        class Resource(resource.Resource):
            @resource.POST(content_type='image/*')
            def image_any(self, request):
                return http.ok([], 'image/*')
            @resource.POST(content_type='image/png')
            def image_png(self, request):
                return http.ok([], 'image/png')
            @resource.POST()
            def anything(self, request):
                return http.ok([], '*/*')
        res = Resource()
        response = res(self._request('image/png'))
        assert response.status == "200 OK"
        assert response.body == 'image/png'
        response = res(self._request('image/jpeg'))
        assert response.status == "200 OK"
        assert response.body == 'image/*'
        response = res(self._request('text/plain'))
        assert response.status == "200 OK"
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
                return http.ok([], 'json')
        res = Resource()
        response = res(self._request(''))
        assert response.status == "200 OK"
        assert response.body == 'json'

    def test_content_type_and_accept(self):
        """
        Check that various combinations of content_type and accept matches are ok.
        """
        class Resource(resource.Resource):
            @resource.POST(accept='json', content_type='json')
            def json_in_json_out(self, request):
                return http.ok([], 'json_in_json_out')
            @resource.POST(accept='html', content_type='json')
            def json_in_html_out(self, request):
                return http.ok([], 'json_in_html_out')
        res = Resource()
        response = res(self._request('application/json', 'text/html'))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'text/html'
        assert response.body == 'json_in_html_out'
        response = res(self._request('application/json', 'application/json'))
        assert response.status == "200 OK"
        assert response.headers['Content-Type'] == 'application/json'
        assert response.body == 'json_in_json_out'

    def _request(self, content_type, accept=None):
        req = http.Request.blank('/')
        req.content_type = content_type
        req.method = 'POST'
        if accept:
            req.accept = accept

        return req


class TestAcceptLists(unittest.TestCase):

    def test_match(self):
        class Resource(resource.Resource):
            @resource.GET(accept=['text/html', 'application/xhtml+xml'])
            def html(self, request):
                return http.ok([], '<html />')
        res = Resource()
        environ = http.Request.blank('/', headers={'Accept': 'text/html'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"
        environ = http.Request.blank('/', headers={'Accept': 'application/xhtml+xml'}).environ
        response = res(http.Request(environ))
        assert response.status == "200 OK"

    def test_auto_content_type(self):
        class Resource(resource.Resource):
            @resource.GET(accept=['text/html', 'application/xhtml+xml'])
            def html(self, request):
                return http.ok([], '<html />')
        # Check specific accept type.
        environ = http.Request.blank('/', headers={'Accept': 'text/html'}).environ
        response = Resource()(http.Request(environ))
        assert response.headers['content-type'] == 'text/html'
        # Check other specific accept type.
        environ = http.Request.blank('/', headers={'Accept': 'application/xhtml+xml'}).environ
        response = Resource()(http.Request(environ))
        assert response.headers['content-type'] == 'application/xhtml+xml'
        # Check the server's first accept match type is used if the client has
        # no strong preference whatever order the accept header lists types.
        environ = http.Request.blank('/', headers={'Accept': 'text/html,application/xhtml+xml'}).environ
        response = Resource()(http.Request(environ))
        assert response.headers['content-type'] == 'text/html'
        environ = http.Request.blank('/', headers={'Accept': 'application/xhtml+xml,text/html'}).environ
        response = Resource()(http.Request(environ))
        assert response.headers['content-type'] == 'text/html'
        # Client accepts both but prefers one.
        environ = http.Request.blank('/', headers={'Accept': 'text/html,application/xhtml+xml;q=0.9'}).environ
        response = Resource()(http.Request(environ))
        assert response.headers['content-type'] == 'text/html'
        # Client accepts both but prefers other.
        environ = http.Request.blank('/', headers={'Accept': 'text/html;q=0.9,application/xhtml+xml'}).environ
        response = Resource()(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/', headers=[('Accept', 'text/html')]).environ
        response = res(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/', headers=[('Accept', 'application/json')]).environ
        response = res(http.Request(environ))
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
        res = Resource()
        environ = http.Request.blank('/').environ
        response = res(http.Request(environ))
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


        A = app.RestishApp(Resource())

        R = wsgi_out(A, http.Request.blank('/').environ)
        assert R['status'].startswith('200'), R.status
        assert R['body'] == 'resource'
        
        R = wsgi_out(A, http.Request.blank('/bar').environ)
        assert R['status'].startswith('200'), R.status
        assert R['body'] == 'bar'
        
        R = wsgi_out(A, http.Request.blank('/foo').environ)
        assert R['status'].startswith('302')
        
        R = wsgi_out(A, http.Request.blank('/foo2').environ)
        assert R['status'].startswith('302')
        
        R = wsgi_out(A, http.Request.blank('/spam/and/eggs').environ)
        assert R['status'].startswith('200'), R.status
        assert R['body'] == 'spam'
        
        R = wsgi_out(A, http.Request.blank('/spam/or/eggs').environ)
        assert R['status'].startswith('302'), R.status

    def test_declarative(self):
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

        A = app.RestishApp(Resource2("who's your daddy"))

        R = wsgi_out(A, http.Request.blank('/').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'resource'

        R = wsgi_out(A, http.Request.blank('/bar').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'bar'
        
        R = wsgi_out(A, http.Request.blank('/foo').environ)
        assert R['status'].startswith('302')
        
        R = wsgi_out(A, http.Request.blank('/foo2').environ)
        assert R['status'].startswith('302')
        
        R = wsgi_out(A, http.Request.blank('/spam42').environ)
        assert R['status'].startswith('200')
        assert R['body'] == 'who\'s your daddy 42'
        
        R = wsgi_out(A, http.Request.blank('/spum42').environ)
        assert R['status'].startswith('302')
        # location header
        assert R['headers'][0][1].endswith('/spam42')


if __name__ == '__main__':
    unittest.main()
