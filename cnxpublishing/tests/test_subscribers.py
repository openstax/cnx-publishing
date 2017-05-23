# -*- coding: utf-8 -*-
import json
import time
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from . import use_cases
from .testing import db_connect
from .test_db import BaseDatabaseIntegrationTestCase


class BaseSubscriberTestCase(BaseDatabaseIntegrationTestCase):

    @db_connect
    def setUp(self, cursor):
        super(BaseSubscriberTestCase, self).setUp()
        self.binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        self.ident_hash = self.binder.ident_hash
        cursor.execute(
            "SELECT module_ident FROM modules "
            "WHERE ident_hash(uuid, major_version, minor_version) = %s",
            (self.ident_hash,))
        self.module_ident = cursor.fetchone()[0]


class PostPublicationStartUpTestCase(BaseSubscriberTestCase):

    @property
    def target(self):
        from cnxpublishing.subscribers import post_publication_start_up
        return post_publication_start_up

    def make_event(self):
        from cnxpublishing.events import ChannelProcessingStartUpEvent
        event = ChannelProcessingStartUpEvent()
        return event

    def call_target(self):
        self.target(self.make_event())

    @db_connect
    def test(self, cursor):
        # Start listening for post_publication notifications.
        cursor.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor.execute('LISTEN post_publication')
        cursor.connection.commit()

        self.call_target()
        # Slowish machines require some time to catch up
        time.sleep(0.5)

        # Commit and poll to get the notifications
        cursor.connection.commit()
        cursor.connection.poll()
        try:
            notify = cursor.connection.notifies.pop(0)
        except IndexError:
            self.fail("the target did not create any notifications")

        # Check that a notification was sent.
        payload = json.loads(notify.payload)
        self.assertEqual(self.module_ident, payload['module_ident'])
        self.assertIn(self.ident_hash, payload['ident_hash'])


class PostPublicationProcessingTestCase(BaseSubscriberTestCase):

    @property
    def target(self):
        from cnxpublishing.subscribers import post_publication_processing
        return post_publication_processing

    def make_event(self, payload=None):
        if payload is None:
            payload = self.make_payload()
        from psycopg2.extensions import Notify
        notif = Notify(pid=555, channel='post_publication', payload=payload)
        from cnxpublishing.events import PostPublicationEvent
        event = PostPublicationEvent(notif)
        return event

    def make_payload(self, module_ident=None, ident_hash=None):
        if module_ident is None:
            module_ident = self.module_ident
        if ident_hash is None:
            ident_hash = self.ident_hash
        payload = '{{"module_ident": {}, "ident_hash": "{}", ' \
                  '"timestamp": "<date>"}}'.format(module_ident,
                                                   ident_hash)
        return payload

    # We don't test for not found, because a notify only takes place when
    #   a module exists.

    @db_connect
    def test(self, cursor):
        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

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
    def test_state_updated_midway(self, cursor):
        from cnxarchive.scripts.export_epub import factory

        class Patcher(object):
            def __init__(self, module_ident):
                self.module_ident = module_ident
                self.captured_state = None

            def __call__(self, *args, **kwargs):
                cursor.execute("SELECT ms.statename "
                               "FROM modules AS m "
                               "NATURAL JOIN modulestates AS ms "
                               "WHERE module_ident = %s",
                               (self.module_ident,))
                self.captured_state = cursor.fetchone()[0]
                return factory(*args, **kwargs)

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        # Before we bake assert the state has changed.
        patched = Patcher(self.module_ident)
        patch_path = 'cnxarchive.scripts.export_epub.factory'
        with mock.patch(patch_path, new=patched):
            self.target(event)

        self.assertEqual(patched.captured_state, 'processing')

    @db_connect
    @mock.patch('cnxpublishing.subscribers.bake')
    def test_error_handling_of_unknown_error(self, cursor, mock_bake):

        def bake(*args, **kwargs):
            raise Exception('something failed during baking')

        mock_bake.side_effect = bake

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Make sure it is marked as 'errored'.
        cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        self.assertEqual(cursor.fetchone()[0], 'errored')

        # Make sure the post_publication state is maked as 'Failed/Error'.
        cursor.execute("SELECT state, state_message FROM post_publications "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        from cnxpublishing.subscribers import CONTACT_SITE_ADMIN_MESSAGE
        self.assertIn(('Failed/Error', CONTACT_SITE_ADMIN_MESSAGE,),
                      [r for r in cursor.fetchall()])

    @db_connect
    @mock.patch('cnxarchive.scripts.export_epub.factory')
    def test_error_handling_during_epub_export(self, cursor, mock_factory):

        def factory(*args, **kwargs):
            raise Exception('something went wrong during export')

        mock_factory.side_effect = factory

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Make sure it is marked as 'errored'.
        cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        self.assertEqual(cursor.fetchone()[0], 'errored')

        # Make sure the post_publication state is maked as 'Failed/Error'.
        cursor.execute("SELECT state, state_message FROM post_publications "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        from cnxpublishing.subscribers import CONTACT_SITE_ADMIN_MESSAGE
        self.assertIn(('Failed/Error', CONTACT_SITE_ADMIN_MESSAGE,),
                      [r for r in cursor.fetchall()])
