# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest

from cnxdb.init import init_db
from pyramid import testing

from .. import use_cases
from ..testing import (
    integration_test_settings,
    db_connection_factory,
    )


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

                # Insert some data into post_publications.
                cursor.execute("""\
INSERT INTO post_publications
    (module_ident, state, state_message)
    SELECT
        (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1),
           'Processing', '';""")
                db_conn.commit()

                cursor.execute("""\
INSERT INTO post_publications
    (module_ident, state, state_message)
    SELECT
        (SELECT module_ident FROM modules ORDER BY module_ident DESC LIMIT 1),
           'Done/Success', 'Yay';
""")

        resp_data = self.target(request)
        self.assertEqual({
            'states': [
                {'timestamp': resp_data['states'][0]['timestamp'],
                 'ident_hash': book.ident_hash,
                 'state': 'Done/Success',
                 'state_message': 'Yay',
                 'title': 'Book of Infinity'},
                {'timestamp': resp_data['states'][1]['timestamp'],
                 'ident_hash': book.ident_hash,
                 'state': 'Processing',
                 'state_message': '',
                 'title': 'Book of Infinity'},
                ]}, resp_data)
