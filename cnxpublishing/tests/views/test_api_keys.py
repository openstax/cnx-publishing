# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest

from pyramid import testing

from ..testing import (
    integration_test_settings,
    db_connection_factory,
    init_db,
)


class ApiKeyViewsTestCase(unittest.TestCase):
    # This ignores testing the security policy. The views are directly
    # protected by permissions. If at some point a view starts checking
    # for particular permissions inside the view, then you should test
    # for that case.

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

    def setUp(self):
        self.config = testing.setUp(settings=self.settings)
        init_db(self.db_conn_str)

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def test_get(self):
        request = testing.DummyRequest()

        # Insert some keys to list in the view.
        api_keys = [
            ['abc', "ABC", ['g:publishers']],
            ['xyz', "XYZ", ['g:trusted-publishers']],
        ]
        insert_stmt = "INSERT INTO api_keys (key, name, groups) " \
                      "VALUES (%s, %s, %s)" \
                      "RETURNING id, key, name, groups"
        expected_api_keys = []
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                for values in api_keys:
                    cursor.execute(insert_stmt, values)
                    row = cursor.fetchone()
                    expected_api_keys.append(row)
        _keys = ['id', 'key', 'name', 'groups']
        expected_api_keys = [dict(zip(_keys, x)) for x in expected_api_keys]

        # Call the target...
        from cnxpublishing.views.api_keys import get_api_keys
        resp_data = get_api_keys(request)

        self.assertEqual(resp_data, expected_api_keys)
