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


class ErrorBannerViewsTestCase(unittest.TestCase):
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

    @unittest.skip("celery is too global")
    def test_error_banner_get(self):
        request = testing.DummyRequest()

        from ...views.admin import admin_post_error_banner
        defaults = admin_post_error_banner(request)
        self.assertEqual(set(defaults.keys()),
                         set(['start_date', 'start_time',
                              'end_date', 'end_time']))

    @unittest.skip("celery is too global")
    def test_error_banner_post(self):
        request = testing.DummyRequest()
        request.POST = {
            'message': 'test message',
            'priority': 1,
            'start_date': '2017-01-01',
            'start_time': '00:01',
            'end_date': '2017-01-02',
            'end_time': '00:02',
        }
        from ...views.admin import admin_post_error_banner_POST
        results = admin_post_error_banner_POST(request)

        # assert the error message has been added to the table
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
        self.assertEqual('test message', results['message'])
        self.assertEqual(1, results['priority'])
        self.assertTrue(datetime.strftime(
            results['starts'], "%Y-%m-%d %H:%M") == '2017-01-01 00:01')
        self.assertTrue(datetime.strftime(
            results['ends'], "%Y-%m-%d %H:%M") == '2017-01-02 00:02')
