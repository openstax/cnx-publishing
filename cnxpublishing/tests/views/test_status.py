# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest
from datetime import datetime

from cnxdb.init import init_db
from pyramid import testing
from pyramid import httpexceptions

from .. import use_cases
from ..testing import (
    integration_test_settings,
    db_connection_factory,
    )


class PostStyleViewsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

    def setUp(self):
        self.config = testing.setUp(settings=self.settings)
        self.config.include('cnxpublishing.tasks')
        self.config.add_route('resource', '/resources/{hash}{ignore:(/.*)?}')  # noqa cnxarchive.views:get_resource
        self.config.add_route('print-style-history-name',
                              '/status/print-style-history/{name}')
        self.config.add_route('print-style-history-version',
                              '/status/print-style-history/{name}/{version}')
        init_db(self.db_conn_str, True)
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                # Insert one book into archive.
                use_cases.setup_BOOK_in_archive(self, cursor)
                db_conn.commit()

                cursor.execute("""\
                INSERT INTO print_style_recipes
                (print_style, fileid, tag)
                VALUES
                ('*print style*', 1, '1.0')""")

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def test_print_style_history(self):
        request = testing.DummyRequest()

        from ...views.status import print_style_history
        content = print_style_history(request)
        self.assertEqual([{
                'version': '1.0',
                'recipe': 1,
                'print_style': '*print style*',
                'revised': content[0]['revised'],
                'print_style_url': 'http://example.com/status/print-style-history/*print%20style*',
                'recipe_url': 'http://example.com/status/print-style-history/*print%20style*/1.0'
            }],
            content)

    def test_print_style_history_post(self):
        request = testing.DummyRequest()
        request.POST = {'recipe': 'test fake file',
                        'name': 'name',
                        'version': '1.0'}

        from ...views.status import print_style_history_POST
        content = print_style_history_POST(request)

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:

                cursor.execute("""SELECT fileid, file, media_type
                                  FROM files
                                  ORDER BY fileid;""")
                results = cursor.fetchall()
                fileid = results[-1][0]
                self.assertEqual(results[-1][2], 'text/css')
                self.assertEqual(len(results[-1][1]), 14)

                cursor.execute("""SELECT fileid, print_style, tag
                                FROM print_style_recipes
                                ORDER BY revised;""")
                results = cursor.fetchall()[-1]
                self.assertEqual(results[0], fileid)
                self.assertEqual(results[1], 'name')
                self.assertEqual(results[2], '1.0')

    def test_print_style_history_single_style(self):
        request = testing.DummyRequest()

        name = '*print style*'
        request.matchdict['name'] = name

        from ...views.status import print_style_history_name
        content = print_style_history_name(request)
        self.assertEqual([{
                'version': '1.0',
                'recipe': 1,
                'print_style': '*print style*',
                'revised': content[0]['revised'],
                'recipe_url': 'http://example.com/status/print-style-history/*print%20style*/1.0'
            }],
            content)

    def test_print_style_history_single_version(self):
        request = testing.DummyRequest()

        name = '*print style*'
        request.matchdict['name'] = name
        request.matchdict['version'] = '1.0'

        from ...views.status import print_style_history_version
        with self.assertRaises(httpexceptions.HTTPFound) as cm:
            print_style_history_version(request)

        self.assertEqual(cm.exception.headers['Location'],
                         '/resources/8d539366a39af1715bdf4154d0907d4a5360ba29/*print%20style*-1.0.css')
        self.assertEqual(cm.exception.headers['Content-Type'],
                         'text/html; charset=UTF-8')
