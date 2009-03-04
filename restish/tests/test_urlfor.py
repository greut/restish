# -*- coding: utf-8 -*-

import unittest

from restish import app, http, resource, templating
from restish.ext.urlfor import child, url_for
from restish.tests.util import wsgi_out

class TestUrlFor(unittest.TestCase):
    def test_simple(self):
        class Index(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], 'index')

        class Blog(resource.Resource):
            @resource.GET()
            def get(self, request):
                return http.ok([], 'blog')

        class Resource(resource.Resource):
            index = child("", Index)
            blog = child(Blog)

        tests = [('/', 'index'),
                 ('/blog', 'blog')
                ]
        
        for path, body in tests:
            environ = http.Request.blank(path).environ
            response = Resource()(http.Request(environ))
            print response.status, response.body
