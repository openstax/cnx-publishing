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

from .. import use_cases
from ..testing import (
    integration_test_settings,
    db_connection_factory,
    )


# FIXME There is an issue with setting up the celery app more than once.
#       Apparently, creating the app a second time doesn't really create
#       it again. There is some global state hanging around that we can't
#       easily get at. This causes the task results tables used in these
#       views to not exist, because the code believes it's already been
#       initialized.
@unittest.skip("celery is too global")
class PostPublicationsViewsTestCase(unittest.TestCase):
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
        init_db(self.db_conn_str, True)

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    @property
    def target(self):
        from ...views.admin import admin_post_publications
        return admin_post_publications

    def test_no_results(self):
        request = testing.DummyRequest()

        resp_data = self.target(request)

        self.assertEqual({'states': []}, resp_data)

    def test(self):
        request = testing.DummyRequest()

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                # Insert one book into archive.
                book = use_cases.setup_BOOK_in_archive(self, cursor)
                db_conn.commit()

                # Insert some data into the association table.
                cursor.execute("""
INSERT INTO document_baking_result_associations
  (result_id, module_ident)
SELECT
  uuid_generate_v4(),
  (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1);""")
                db_conn.commit()

                cursor.execute("""\
INSERT INTO document_baking_result_associations
  (result_id, module_ident)
SELECT
  uuid_generate_v4(),
  (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1);""")

        resp_data = self.target(request)
        self.assertEqual({
            'states': [
                {'created': resp_data['states'][0]['created'],
                 'ident_hash': book.ident_hash,
                 'state': u'PENDING',
                 'state_message': '',
                 'title': 'Book of Infinity'},
                {'created': resp_data['states'][1]['created'],
                 'ident_hash': book.ident_hash,
                 'state': u'PENDING',
                 'state_message': '',
                 'title': 'Book of Infinity'},
                ]}, resp_data)


class SiteMessageViewsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

    def setUp(self):
        self.config = testing.setUp(settings=self.settings)
        init_db(self.db_conn_str, True)
        self.create_post_args = {
            'message': 'test message',
            'priority': 1,
            'type': 1,
            'start_date': '2017-01-01',
            'start_time': '00:01',
            'end_date': '2017-01-02',
            'end_time': '00:02', }

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def test_site_messages_get(self):
        request = testing.DummyRequest()

        from ...views.admin import admin_add_site_message
        defaults = admin_add_site_message(request)
        self.assertEqual(set(defaults.keys()),
                         set(['start_date', 'start_time',
                              'end_date', 'end_time', 'banners']))

    def test_site_messages_add_post(self):
        request = testing.DummyRequest()
        request.POST = self.create_post_args
        from ...views.admin import admin_add_site_message_POST
        results = admin_add_site_message_POST(request)

        # assert the message has been added to the table
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""SELECT message, priority, starts, ends
                                  from service_state_messages
                                  WHERE message='test message';""")
                result = cursor.fetchone()
                self.assertEqual('test message', result[0])
                self.assertEqual(1, result[1])
                self.assertTrue(datetime.strftime(
                    result[2], "%Y-%m-%d %H:%M") == '2017-01-01 00:01')
                self.assertTrue(datetime.strftime(
                    result[3], "%Y-%m-%d %H:%M") == '2017-01-02 00:02')
                cursor.execute("""DELETE from service_state_messages
                                  WHERE message='test message';""")

        # Assert the correct variables were passed to the template
        self.assertEqual('Message successfully added', results['response'])
        self.assertEqual(1, len(results['banners']))

    def test_site_messages_delete(self):
        request = testing.DummyRequest()
        # first add a banner to delete
        request.POST = self.create_post_args
        from ...views.admin import admin_add_site_message_POST
        results = admin_add_site_message_POST(request)

        request.method = 'DELETE'
        request.body = 'id=1'
        from ...views.admin import admin_delete_site_message
        results = admin_delete_site_message(request)
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""SELECT * from service_state_messages
                                  WHERE id=1;""")
                result = cursor.fetchall()
                self.assertEqual(0, len(result))
        self.assertEqual("Message id (1) successfully removed",
                         results['response'])

    def test_site_messages_edit(self):
        request = testing.DummyRequest()
        request = testing.DummyRequest()
        # first add a banner to delete
        request.POST = self.create_post_args
        from ...views.admin import admin_add_site_message_POST
        results = admin_add_site_message_POST(request)

        request.matchdict['id'] = '1'
        from ...views.admin import admin_edit_site_message
        results = admin_edit_site_message(request)
        self.assertEqual({'message': 'test message',
                          'danger': 'selected',
                          'maintenance': 'selected',
                          'start_date': '2017-01-01',
                          'start_time': '00:01',
                          'end_date': '2017-01-02',
                          'end_time': '00:02',
                          'id': '1'}, results)

    def test_site_messages_edit_post(self):
        request = testing.DummyRequest()
        request = testing.DummyRequest()
        # first add a banner to delete
        request.POST = self.create_post_args
        from ...views.admin import admin_add_site_message_POST
        results = admin_add_site_message_POST(request)

        request.matchdict['id'] = '1'
        request.POST = {'message': 'edited message',
                        'priority': 2,
                        'type': 2,
                        'start_date': '2017-01-02',
                        'start_time': '00:02',
                        'end_date': '2017-01-03',
                        'end_time': '00:03',
                        'id': '1'}
        from ...views.admin import admin_edit_site_message_POST
        results = admin_edit_site_message_POST(request)
        self.assertEqual({'response': 'Message successfully Updated',
                          'message': 'edited message',
                          'warning': 'selected',
                          'notice': 'selected',
                          'start_date': '2017-01-02',
                          'start_time': '00:02',
                          'end_date': '2017-01-03',
                          'end_time': '00:03',
                          'id': '1'}, results)

# FIXME There is an issue with setting up the celery app more than once.
#       Apparently, creating the app a second time doesn't really create
#       it again. There is some global state hanging around that we can't
#       easily get at. This causes the task results tables used in these
#       views to not exist, because the code believes it's already been
#       initialized.
class PrintStyleViewsTestCase(unittest.TestCase):
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
        init_db(self.db_conn_str, True)
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""INSERT INTO files
                                  (file, media_type) VALUES ('file', 'css');""")
                cursor.execute("""INSERT INTO print_style_recipes
                                  (print_style, fileid, tag)
                                  VALUES ('ccap-physics', 1, '1.0');""")

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    # @unittest.skip("celery is too global")
    def test_print_styles(self):
        request = testing.DummyRequest()

        from ...views.admin import admin_print_styles
        content = admin_print_styles(request)
        self.assertEqual(1, len(content['styles']))
        for row in content['styles']:
            self.assertEqual(set(row.keys()),
                             set(['print_style', 'file', 'type', 'revised',
                                  'number', 'tag']))

    # @unittest.skip("celery is too global")
    def test_print_style_single(self):
        request = testing.DummyRequest()

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("select fileid from files;")
                print(cursor.fetchall())

        print_style = 'ccap-physics'
        request.matchdict['style'] = print_style

        from ...views.admin import admin_print_styles_single
        content = admin_print_styles_single(request)
        print(content)
        self.assertEqual(content['print_style'], 'ccap-physics')
        self.assertEqual(content['file'], 1)
        self.assertEqual(content['recipe_type'], 'web')
        for row in content['collections']:
            self.assertEqual(set(row.keys()),
                             set(['title', 'authors', 'revised', 'uuid',
                                  'ident_hash', 'status']))
        # add test to assert they are the correct books, and correct ststus when test data updated
