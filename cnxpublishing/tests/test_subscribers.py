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


# FIXME Several of these tests are skipped because the celery_worker
#       process hangs after one test.
#       See https://github.com/celery/celery/issues/4088
#       If you remove the skip and run them one at a time they do pass.


@pytest.mark.usefixtures('scoped_pyramid_app')
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
    def suite_fixture(self, scoped_pyramid_app, complex_book_one,
                      celery_worker):
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

        # Check the module state has changed prior to task execution.
        db_cursor.execute("SELECT ms.statename "
                          "FROM modules AS m "
                          "NATURAL JOIN modulestates AS ms "
                          "WHERE module_ident = %s",
                          (self.module_ident,))
        state = db_cursor.fetchone()[0]
        assert state == 'processing'

        # Rather than time.sleep for some arbitrary amount of time,
        # let's check the result, since we'll need to do that anyway.
        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s "
                          "ORDER BY created DESC",
                          (self.module_ident,))
        result_id = db_cursor.fetchone()[0]

        from celery.result import AsyncResult
        result = AsyncResult(id=result_id)
        result.get()  # blocking operation

        db_cursor.execute("SELECT count(*) FROM trees WHERE is_collated = 't';")
        collation_count = db_cursor.fetchone()[0]
        assert collation_count > 0, "baking didn't happen"

        db_cursor.execute("SELECT ms.statename "
                          "FROM modules AS m NATURAL JOIN modulestates AS ms "
                          "WHERE module_ident = %s",
                          (self.module_ident,))
        assert db_cursor.fetchone()[0] == 'current'

    @pytest.mark.skip('issue running more than on celery worker test')
    def test_error_handling_of_unknown_error(self, db_cursor, mocker):
        exc_msg = 'something failed during baking'

        def bake(*args, **kwargs):
            raise Exception(exc_msg)

        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')
        mock_bake.side_effect = bake

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Rather than time.sleep for some arbitrary amount of time,
        # let's check the result, since we'll need to do that anyway.
        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s "
                          "ORDER BY created DESC",
                          (self.module_ident,))
        result_id = db_cursor.fetchone()[0]

        from celery.result import AsyncResult
        result = AsyncResult(id=result_id)
        with pytest.raises(Exception) as exc_info:
            result.get()  # blocking operation
            assert exc_info.exception.args[0] == exc_msg

        # Make sure it is marked as 'errored'.
        db_cursor.execute("SELECT ms.statename "
                          "FROM modules AS m NATURAL JOIN modulestates AS ms "
                          "WHERE module_ident = %s",
                          (self.module_ident,))
        db_cursor.fetchone()[0] == 'errored'

    # TODO move to a bake_process unit-test
    @pytest.mark.skip('issue running more than on celery worker test')
    def test_error_handling_during_epub_export(self, db_cursor, mocker):
        exc_msg = 'something failed during baking'

        def factory(*args, **kwargs):
            raise Exception(exc_msg)

        mock_factory = mocker.patch('cnxarchive.scripts.export_epub.factory')
        mock_factory.side_effect = factory

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        # Rather than time.sleep for some arbitrary amount of time,
        # let's check the result, since we'll need to do that anyway.
        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s "
                          "ORDER BY created DESC",
                          (self.module_ident,))
        result_id = db_cursor.fetchone()[0]

        from celery.result import AsyncResult
        result = AsyncResult(id=result_id)
        with pytest.raises(Exception) as exc_info:
            result.get()  # blocking operation
            assert exc_info.exception.args[0] == exc_msg

        # Make sure it is marked as 'errored'.
        db_cursor.execute("SELECT ms.statename "
                          "FROM modules AS m NATURAL JOIN modulestates AS ms "
                          "WHERE module_ident = %s",
                          (self.module_ident,))
        db_cursor.fetchone()[0] == 'errored'
