# -*- coding: utf-8 -*-

import unittest
 
from restish import app, http, resource, templating
from restish.tests.util import wsgi_out
 
class TestUrlFor(unittest.TestCase):
    def test_simple(self):
        class Index(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], 'index')

        class Entry(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], 'entry')

        class Blog(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], 'blog')

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
 
        tests = [('/index2', 'index'),
                 ('/index', 'index'),
                 ('/blog2', 'blog'),
                 ('/blog', 'blog'),
                 ('/blog2/entry2', 'entry'),
                 ('/blog2/entry', 'entry'),
                 ('/blog/entry2', 'entry'),
                 ('/blog/entry', 'entry'),
                ]
        
        A = app.RestishApp(Resource())
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = wsgi_out(A, environ)
            #print path, response["body"]
            assert response["status"].startswith("200")
            assert response["body"] == body
        
        tests = [(Index, '/index'),
                 (Blog, '/blog'),
                 (Entry, '/blog/entry')
                ]

        for klass, url in tests:
            assert resource.url_for(klass) == url, "%s != %s" % (url, resource.url_for(klass))


if __name__ == "__main__":
    import nose
    nose.run([], [__file__])
