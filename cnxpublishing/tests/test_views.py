# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest

from webob import Request
from pyramid import testing
from pyramid import httpexceptions


class PublishViewTestCase(unittest.TestCase):

    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def test_epub_format_exception(self):
        """Test that we have a way to immediately fail if the EPUB
        is a valid EPUB structure. And all the files specified within
        the manifest and OPF documents.
        """
        post_data = {'epub': ('book.epub', b'')}
        request = Request.blank('/publications', POST=post_data)

        from ..views import publish
        with self.assertRaises(httpexceptions.HTTPBadRequest) as caught_exc:
            publish(request)

        exc = caught_exc.exception
        self.assertEqual(exc.args, ('Format not recognized.',))
