# -*- coding: utf-8 -*-

import unittest
 
from restish import app, http, resource, templating, url
from restish.util import wsgi_out


class TestUrlFor(unittest.TestCase):
    def test_simple(self):
        class Index(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], "index")

        class Entry(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], "entry")

        class Blog(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], "blog")

            @resource.child()
            def entry2(self, request, segments):
                return Entry(), segments

            entry = resource.child(Entry)
 
        class Resource(resource.Resource):
            @resource.child()
            def index2(self, request, segments):
                return Index(), segments
            @resource.child()
            def blog2(self, request, segments):
                return Blog(), segments

            index = resource.child(Index)
            blog = resource.child(Blog)
 
        tests = [("/index2", "index"),
                 ("/index", "index"),
                 ("/blog2", "blog"),
                 ("/blog", "blog"),
                 ("/blog2/entry2", "entry"),
                 ("/blog2/entry", "entry"),
                 ("/blog/entry2", "entry"),
                 ("/blog/entry", "entry"),
                ]
        
        A = app.RestishApp(Resource())
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = wsgi_out(A, environ)
            assert response["status"].startswith("200")
            assert response["body"] == body
        
        tests = [(Resource, "/"),
                 (Index, "/index"),
                 (Blog, "/blog"),
                 (Entry, "/blog/entry"),
                 ("Resource", "/"),
                 ("Index", "/index"),
                 ("Blog", "/blog"),
                 ("Entry", "/blog/entry"),
                 ("resource", "/"),
                 ("index", "/index"),
                 ("blog", "/blog"),
                 ("entry", "/blog/entry")
                ]

        for klass, url in tests:
            assert resource.url_for(klass) == url, "%s != %s" % (url, resource.url_for(klass))
    
    def test_with_matchers(self):
        class Entry(resource.Resource):
            def __init__(self, id, slug):
                self.id = id
                self.slug = slug

            @resource.GET()
            def get(self, request):
                return http.ok([], "entry (%s): %s" % (self.id, self.slug))

        class Blog(resource.Resource):
            def __init__(self, blogname):
                self.blogname = blogname

            @resource.GET()
            def get(self, request):
                return http.ok([], "blog: %s" % self.blogname)

            entry = resource.child("{id}/{slug}", Entry)
 
        class Resource(resource.Resource):
            @resource.GET()
            def index(self, request):
                return http.ok([], "index")

            blog = resource.child("{blogname}", Blog)

        tests = [("/", "index"),
                 ("/blog", "blog: blog"),
                 ("/wordpress", "blog: wordpress"),
                 ("/blog/1/hello world", "entry (1): hello world"),
                 ("/wordpress/2/hello world", "entry (2): hello world")
                ]
        
        A = app.RestishApp(Resource())
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = wsgi_out(A, environ)
            #print path, response["body"]
            assert response["status"].startswith("200")
            assert response["body"] == body
        
        
        tests = [((Resource, {}), "/"),
                 (("resource", {}), "/"),
                 ((Blog, {"blogname": "b2"}), "/b2"),
                 (("blog", {"blogname": "b2"}), "/b2"),
                 ((Entry, {"blogname": "b2evolution",
                           "id": "1",
                           "slug": "foo"}),
                  "/b2evolution/1/foo"),
                 (("entry", {"blogname": "b2evolution",
                           "id": "1",
                           "slug": "foo"}),
                  "/b2evolution/1/foo"),
                ]

        for (klass, args), url in tests:
            assert resource.url_for(klass, **args) == url, url

    def test_with_regexp(self):
        class Entry(resource.Resource):
            def __init__(self, id, slug):
                self.id = id
                self.slug = slug

            @resource.GET()
            def get(self, request):
                return http.ok([], "entry (%s): %s" % (self.id, self.slug))

        class Blog(resource.Resource):
            def __init__(self, blogname):
                self.blogname = blogname

            @resource.GET()
            def get(self, request):
                return http.ok([], "blog: %s" % self.blogname)

            entry = resource.child("_{id:[0-9]+}_/slug-{slug}", Entry)
 
        class Resource(resource.Resource):
            @resource.GET()
            def index(self, request):
                return http.ok([], "index")

            blog = resource.child("{blogname:[a-z]{4,}}-is-a-blog", Blog)

        tests = [("/", "index"),
                 ("/blog-is-a-blog", "blog: blog"),
                 ("/wordpress-is-a-blog", "blog: wordpress"),
                 ("/blog-is-a-blog/_1_/slug-hello world", "entry (1): hello world"),
                 ("/wordpress-is-a-blog/_2_/slug-hello world", "entry (2): hello world")
                ]
        
        A = app.RestishApp(Resource())
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = wsgi_out(A, environ)
            #print path, response["body"]
            assert response["status"].startswith("200")
            assert response["body"] == body
        
        tests = [((Resource, {}), "/"),
                 ((Blog, {"blogname": "b2"}), "/b2-is-a-blog"),
                 ((Entry, {"blogname": "b2evolution",
                           "id": "1",
                           "slug": "foo"}),
                  "/b2evolution-is-a-blog/_1_/slug-foo")
                ]

        for (klass, args), url in tests:
            assert resource.url_for(klass, **args) == url, url
            assert resource.url_for(klass, args) == url, url
    
    def test_canonical(self):
        class Book(resource.Resource):
            def __init__(self, title, **kwargs):
                self.title = title

            @resource.GET()
            def get(self, request):
                return http.ok([], self.title)

        class Resource(resource.Resource):
            category = resource.child("category/{category}/{title}", Book)
            permalink = resource.child("book/{title}", Book, canonical=True)
            shortlink = resource.child("b/{title}", Book)
            bydate = resource.child("{year}/{month}/{day}/{title}", Book)
        
        tests = [("/book/0", "0"),
                 ("/b/1", "1"),
                 ("/category/sleepy/2", "2"),
                 ("/2009/11/08/3", "3")
                ]

        A = app.RestishApp(Resource())
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = wsgi_out(A, environ)
            assert response["status"].startswith("200")
            assert response["body"] == body
        
        assert resource.url_for(Book, title="4") == "/book/4"
        assert resource.url_for("book", title="5") == "/book/5"
        # TODO: requires extra flying ponies!
        #assert resource.url_for("book", category="animal", title="6") == "/category/animal/6"
        #assert resource.url_for("book", year="2009", month="03", day="09", title="7") == "/2009/03/09/7"
    
    def test_unicode(self):
        class Moo(resource.Resource):
            def __init__(self, arg):
                self.arg = arg
    
            def __call__(self, segments):
                return http.ok([("Content-type", "text/plain; charset=utf-8")],
                                self.arg)
    
        class Root(resource.Resource):
            moo = resource.child(u"£-{arg}", Moo)
        
        tests = [(u"£-a", u"a"),
                 (u"£-ä", u"ä")
                ]
    
        A = app.RestishApp(Root())
        for path, body in tests:
            req = http.Request.blank(url.join_path([path]))
            response = wsgi_out(A, req.environ)
            assert response["status"].startswith("200")
            assert response["body"] == body
             
            assert resource.url_for("moo", arg=body) == url.join_path([path])

    def test_urlfor_using_object(self):
        class Data(object):
            def __init__(self, a, b, c):
                self.a = a
                self.b = b
                self.c = c

            def __str__(self):
                return (u"%s %s %s " % (self.a, self.b, self.c)).encode("utf-8")

        class Abc(resource.Resource):
            def __init__(self, a, b, c):
                self.data = Data(a, b, c)

            @resource.GET()
            def get(self, request):
                return http.ok([("Content-type", "text/plain; charset=utf-8")],
                               str(self.data))

        class Root(resource.Resource):
            data = resource.child("{a}/{b}/{c}", Abc)
        
        tests = [(("a", "b", "c"), "/a/b/c"),
                 ((1, 2, 3), "/1/2/3"),
                 ((u"£", u"$", u"€"), url.join_path([u"£", u"$", u"€"]))
                ]

        A = app.RestishApp(Root())
        for data, path in tests:
            obj = Data(*data)
            # request
            req = http.Request.blank(path)
            response = wsgi_out(A, req.environ)
            assert response["status"].startswith("200")
            assert response["body"] == str(obj)
            # reverse url
            assert resource.url_for("abc", obj) == path


if __name__ == "__main__":
    unittest.main()
