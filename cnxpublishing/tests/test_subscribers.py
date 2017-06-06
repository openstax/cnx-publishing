# -*- coding: utf-8 -*-
import json
import time

import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


@pytest.fixture
def channel_processing_start_up_event():
    from cnxpublishing.events import ChannelProcessingStartUpEvent
    event = ChannelProcessingStartUpEvent()
    return event


@pytest.mark.usefixtures('publishing_app')
def test_startup_event(db_cursor, complex_book_one,
                       channel_processing_start_up_event):
    cursor = db_cursor
    book_one, ident_mapping = complex_book_one
    # Start listening for post_publication notifications.
    cursor.connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor.execute('LISTEN post_publication')
    cursor.connection.commit()

    from cnxpublishing.subscribers import post_publication_start_up
    post_publication_start_up(channel_processing_start_up_event)
    # Slowish machines require some time to catch up
    time.sleep(0.5)

    # Commit and poll to get the notifications
    cursor.connection.commit()
    cursor.connection.poll()
    try:
        notify = cursor.connection.notifies.pop(0)
    except IndexError:
        pytest.fail("the target did not create any notifications")

    # Check that a notification was sent.
    payload = json.loads(notify.payload)
    assert book_one.ident_hash in payload['ident_hash']
    assert ident_mapping[book_one.ident_hash] == payload['module_ident']


class TestPostPublicationProcessing(object):

    @pytest.fixture(autouse=True)
    def suite_fixture(self, complex_book_one):
        self.binder, ident_mapping = complex_book_one
        self.ident_hash = self.binder.ident_hash
        self.module_ident = ident_mapping[self.binder.ident_hash]

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

    def test(self, db_cursor):
        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)
        db_cursor.execute("SELECT count(*) FROM trees WHERE is_collated = 't';")
        collation_count = db_cursor.fetchone()[0]
        assert collation_count > 0, "baking didn't happen"

        db_cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        assert db_cursor.fetchone()[0] == 'current'

        # We check for all the states because the timestamps are exactly
        # the same since the processes run almost in sequence.
        db_cursor.execute("SELECT state FROM post_publications "
                       "WHERE module_ident = %s "
                       "ORDER BY timestamp DESC",
                       (self.module_ident,))
        assert 'Done/Success' in [r[0] for r in db_cursor.fetchall()]

    def test_state_updated_midway(self, db_cursor, mocker):
        from cnxarchive.scripts.export_epub import factory

        class Patcher(object):
            def __init__(self, module_ident):
                self.module_ident = module_ident
                self.captured_state = None

            def __call__(self, *args, **kwargs):
                db_cursor.execute("SELECT ms.statename "
                               "FROM modules AS m "
                               "NATURAL JOIN modulestates AS ms "
                               "WHERE module_ident = %s",
                               (self.module_ident,))
                self.captured_state = db_cursor.fetchone()[0]
                return factory(*args, **kwargs)

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        # Before we bake assert the state has changed.
        patched = Patcher(self.module_ident)
        mocker.patch('cnxarchive.scripts.export_epub.factory', new=patched)

        self.target(event)

        assert patched.captured_state == 'processing'

    def test_error_handling_of_unknown_error(self, db_cursor, mocker):

        def bake(*args, **kwargs):
            raise Exception('something failed during baking')

        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')
        mock_bake.side_effect = bake

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Make sure it is marked as 'errored'.
        db_cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        db_cursor.fetchone()[0] == 'errored'

        # Make sure the post_publication state is maked as 'Failed/Error'.
        db_cursor.execute("SELECT state, state_message FROM post_publications "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        from cnxpublishing.subscribers import CONTACT_SITE_ADMIN_MESSAGE
        expected = ('Failed/Error', CONTACT_SITE_ADMIN_MESSAGE,)
        assert expected in [r for r in db_cursor.fetchall()]

    def test_error_handling_during_epub_export(self, db_cursor, mocker):

        def factory(*args, **kwargs):
            raise Exception('something went wrong during export')

        mock_factory = mocker.patch('cnxarchive.scripts.export_epub.factory')
        mock_factory.side_effect = factory

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Make sure it is marked as 'errored'.
        db_cursor.execute("SELECT ms.statename "
                       "FROM modules AS m NATURAL JOIN modulestates AS ms "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        db_cursor.fetchone()[0] == 'errored'

        # Make sure the post_publication state is maked as 'Failed/Error'.
        db_cursor.execute("SELECT state, state_message FROM post_publications "
                       "WHERE module_ident = %s",
                       (self.module_ident,))
        from cnxpublishing.subscribers import CONTACT_SITE_ADMIN_MESSAGE
        expected = ('Failed/Error', CONTACT_SITE_ADMIN_MESSAGE,)
        assert expected in [r for r in db_cursor.fetchall()]
