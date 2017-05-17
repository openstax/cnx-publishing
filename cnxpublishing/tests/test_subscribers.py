# -*- coding: utf-8 -*-
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from pyramid import testing

from . import use_cases
from .testing import db_connect
from .test_db import BaseDatabaseIntegrationTestCase


class PostPublicationProcessingTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.subscribers import post_publication_processing
        return post_publication_processing

    def _make_event(self, payload=None):
        if payload is None:
            payload = self._make_payload()
        from psycopg2.extensions import Notify
        notif = Notify(pid=555, channel='post_publication', payload=payload)
        from cnxpublishing.events import PostPublicationEvent
        event = PostPublicationEvent(notif)
        return event

    def _make_payload(self, module_ident=None, ident_hash=None):
        if module_ident is None:
            module_ident = self.module_ident
        if ident_hash is None:
            ident_hash = self.ident_hash
        payload = '{{"module_ident": {}, "ident_hash": "{}", ' \
                  '"timestamp": "<date>"}}'.format(module_ident,
                                                   ident_hash)
        return payload

    @db_connect
    def setUp(self, cursor):
        super(PostPublicationProcessingTestCase, self).setUp()
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        self.ident_hash = binder.ident_hash
        cursor.execute(
            "SELECT module_ident FROM modules "
            "WHERE ident_hash(uuid, major_version, minor_version) = %s",
            (self.ident_hash,))
        self.module_ident = cursor.fetchone()[0]

    # We don't test for not found, because a notify only takes place when
    #   a module exists.

    @db_connect
    def test(self, cursor):
        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self._make_event()

        self.target(event)
        cursor.execute("SELECT count(*) FROM trees WHERE is_collated = 't';")
        collation_count = cursor.fetchone()[0]
        assert collation_count > 0, "baking didn't happen"

        cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        self.assertEqual(cursor.fetchone()[0], 'current')

        # We check for all the states because the timestamps are exactly
        # the same since the processes run almost in sequence.
        cursor.execute("SELECT state FROM post_publications "
                       "WHERE module_ident = %s "
                       "ORDER BY timestamp DESC",
                       (self.module_ident,))
        self.assertIn('Done/Success', [r[0] for r in cursor.fetchall()])

    @db_connect
    @mock.patch('cnxpublishing.subscribers.bake')
    def test_error_handling(self, cursor, mock_bake):

        def bake(*args, **kwargs):
            raise Exception('something failed during baking')

        mock_bake.side_effect = bake

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self._make_event()

        self.target(event)

        # Make sure it is marked as 'errored'.
        cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        self.assertEqual(cursor.fetchone()[0], 'errored')

        # Make sure the post_publication state is maked as 'Failed/Error'.
        cursor.execute("SELECT state FROM post_publications "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        self.assertIn('Failed/Error', [r[0] for r in cursor.fetchall()])
