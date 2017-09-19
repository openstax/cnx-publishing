# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import pytest
import uuid
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from datetime import datetime

from pyramid import testing
import pytest
import psycopg2
from pyramid.httpexceptions import HTTPBadRequest

from .. import use_cases
from ..testing import (
    integration_test_settings,
    db_connection_factory,
    init_db,
    )


def add_data(self):
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
    return book


@pytest.mark.usefixtures('scoped_pyramid_app')
class PostPublicationsViewsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

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

        book = add_data(self)

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
        init_db(self.db_conn_str)
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


@pytest.mark.usefixtures('scoped_pyramid_app')
class ContentStatusViewsTestCase(unittest.TestCase):
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
        self.config.add_route('admin-content-status-single',
                              '/a/content-status/{uuid}')
        self.config.add_route('get-content', '/contents/{ident_hash}')

        add_data(self)

    def test_admin_content_status_no_filters(self):
        request = testing.DummyRequest()

        from ...views.admin import admin_content_status
        content = admin_content_status(request)
        self.assertEqual({
            'SUCCESS': 'checked',
            'PENDING': 'checked',
            'STARTED': 'checked',
            'RETRY': 'checked',
            'FAILURE': 'checked',
            'start_entry': 0,
            'page': 1,
            'num_entries': 100,
            'sort': 'bpsa.created DESC',
            'sort_created': 'fa fa-angle-down',
            'total_entries': 2,
            'states': content['states']
        }, content)
        self.assertEqual(
            content['states'],
            sorted(content['states'], key=lambda x: x['created'], reverse=True))

    def test_admin_content_status_w_filters(self):
        request = testing.DummyRequest()

        request.GET = {'page': 1,
                       'number': 2,
                       'sort': 'STATE ASC',
                       'author': 'charrose',
                       'pending_filter': 'PENDING'}
        from ...views.admin import admin_content_status
        content = admin_content_status(request)
        self.assertEqual({
            'PENDING': 'checked',
            'start_entry': 0,
            'page': 1,
            'num_entries': 2,
            'author': 'charrose',
            'sort': 'STATE ASC',
            'sort_state': 'fa fa-angle-up',
            'total_entries': 2,
            'states': content['states']
        }, content)
        self.assertEqual(len(content['states']), 2)
        for state in content['states']:
            self.assertTrue('charrose' in state['authors'])
            self.assertTrue('PENDING' in state['state'])
        self.assertEqual(
            content['states'],
            sorted(content['states'], key=lambda x: x['state']))

    def test_admin_content_status_stale_recipe(self):
        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET recipe=1
                    WHERE uuid=%s;
                    """, (uuid, ))

        request = testing.DummyRequest()
        request.GET = {'page': 1,
                       'number': 1}
        from ...views.admin import admin_content_status
        content = admin_content_status(request)
        print [x['state'] for x in content['states']]
        self.assertEqual('PENDING stale_content stale_recipe',
                         content['states'][0]['state'])

    def test_admin_content_status_bad_sort(self):
        request = testing.DummyRequest()

        request.GET = {'sort': 'bad sort'}
        from ...views.admin import admin_content_status
        with self.assertRaises(HTTPBadRequest) as caught_exc:
            admin_content_status(request)
        self.assertIn('invalid sort', caught_exc.exception.message)

    def test_admin_content_status_bad_page_number(self):
        request = testing.DummyRequest()

        request.GET = {'page': 'abc'}
        from ...views.admin import admin_content_status
        with self.assertRaises(HTTPBadRequest) as caught_exc:
            admin_content_status(request)
        self.assertIn('invalid page', caught_exc.exception.message)

    @mock.patch('cnxpublishing.views.admin.AsyncResult')
    @mock.patch('psycopg2.connect')
    def test_admin_content_status_state_icons(self, mock_psycopg2_connect,
                                              mock_async_result):
        states = ['PENDING', 'QUEUED', 'STARTED', 'RETRY', 'SUCCESS',
                  'FAILURE', 'REVOKED', 'UNKNOWN']

        def round_robin_states(*args, **kwargs):
            result = mock.Mock(
                state=states[mock_async_result.call_count - 1 % len(states)])
            result.failed.return_value = False
            return result

        mock_async_result.side_effect = round_robin_states

        cursor = mock.MagicMock()
        cursor.fetchall.return_value = [
            ('Just some random module {} for testing'.format(i),
             ['authors'],
             uuid.uuid4(),
             'print-style',
             'latest-recipe',
             'latest-recipe',
             '1.1',
             '1.1',
             datetime.now().isoformat(),
             'result-{}'.format(i))
            for i in range(len(states))]

        db_conn = mock_psycopg2_connect.return_value.__enter__()
        db_conn.cursor().__enter__.return_value = cursor

        request = testing.DummyRequest()
        from ...views.admin import admin_content_status

        content = admin_content_status(request)
        state_icons = [(i['state'], i['state_icon'])
                       for i in content['states']]

        self.assertEqual([
            ('PENDING', 'fa fa-exclamation-triangle'),
            ('QUEUED', 'fa fa-exclamation-triangle'),
            ('STARTED', 'fa fa-exclamation-triangle'),
            ('RETRY', 'fa fa-close'),
            ('SUCCESS', 'fa fa-check-square'),
            ('FAILURE', 'fa fa-close'),
            ('REVOKED', 'fa fa-exclamation-triangle'),
            ('UNKNOWN', 'fa fa-exclamation-triangle')], state_icons)

    def test_admin_content_status_single_page(self):
        request = testing.DummyRequest()

        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        request.matchdict['uuid'] = uuid

        from ...views.admin import admin_content_status_single
        content = admin_content_status_single(request)
        self.assertEqual({
            'uuid': uuid,
            'title': 'Book of Infinity',
            'authors': 'marknewlyn, charrose',
            'print_style': None,
            'current_recipe': None,
            'current_ident': 2,
            'current_state': u'PENDING stale_content',
            'states': [
                {'version': '1.1',
                 'recipe': None,
                 'created': content['states'][0]['created'],
                 'state': 'PENDING stale_content',
                 'state_message': ''},
                {'version': '1.1',
                 'recipe': None,
                 'created': content['states'][1]['created'],
                 'state': 'PENDING stale_content',
                 'state_message': ''}
            ]
        }, content)

    def test_admin_content_status_single_bad_uuid(self):
        request = testing.DummyRequest()

        uuid = 'bad-uuid'
        request.matchdict['uuid'] = uuid

        from ...views.admin import admin_content_status_single
        with self.assertRaises(HTTPBadRequest) as caught_exc:
            admin_content_status_single(request)
        self.assertIn('is not a valid uuid', caught_exc.exception.message)

    def test_admin_content_status_single_uuid_no_book(self):
        request = testing.DummyRequest()

        uuid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
        request.matchdict['uuid'] = uuid

        from ...views.admin import admin_content_status_single
        with self.assertRaises(HTTPBadRequest) as caught_exc:
            admin_content_status_single(request)
        self.assertIn('not a book', caught_exc.exception.message)

    def test_admin_content_status_single_stale_recipe(self):
        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET recipe=1
                    WHERE uuid=%s;
                    """, (uuid, ))

        request = testing.DummyRequest()

        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        request.matchdict['uuid'] = uuid

        from ...views.admin import admin_content_status_single

        request.GET = {'page': 1,
                       'number': 1}
        from ...views.admin import admin_content_status
        content = admin_content_status_single(request)
        print [x['state'] for x in content['states']]
        self.assertEqual('PENDING stale_recipe stale_content',
                         content['states'][0]['state'])

    def test_admin_content_status_single_page_POST_already_baking(self):
        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid=5
                    WHERE uuid=%s;
                    """, (uuid, ))

        request = testing.DummyRequest()
        from ...views.admin import admin_content_status_single_POST

        request.matchdict['uuid'] = uuid
        content = admin_content_status_single_POST(request)
        self.assertEqual(content['response'],
                         'Book of Infinity is already baking/set to bake')

    def test_admin_content_status_single_page_POST_bake(self):
        uuid = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid=1
                    WHERE uuid=%s;
                    """, (uuid, ))

        request = testing.DummyRequest()
        from ...views.admin import admin_content_status_single_POST

        request.matchdict['uuid'] = uuid
        content = admin_content_status_single_POST(request)
        self.assertEqual(content['response'],
                         'Book of Infinity set to bake!')

        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    SELECT stateid FROM modules WHERE uuid=%s;
                    """, (uuid, ))
                state = cursor.fetchone()
                self.assertEqual(state[0], 5)

    def test_admin_content_status_single_page_POST_bad_uuid(self):
        request = testing.DummyRequest()
        from ...views.admin import admin_content_status_single_POST

        uuid = 'd5dbbd8e-d137-4f89-9d0a-eeeeeeeeeeee'
        request.matchdict['uuid'] = uuid
        with self.assertRaises(HTTPBadRequest) as caught_exc:
            content = admin_content_status_single_POST(request)
        self.assertIn('not a book', caught_exc.exception.message)
