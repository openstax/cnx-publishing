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


def test_recipe_selection(db_cursor, complex_book_one, recipes):
    book_one, ident_mapping = complex_book_one
    module_ident = ident_mapping[book_one.ident_hash]

    from cnxpublishing.subscribers import _get_recipe_ids as target

    # Get ruleset recipe fileid
    db_cursor.execute("SELECT fileid "
                      "FROM module_files "
                      "WHERE module_ident = %s"
                      "AND filename = 'ruleset.css'",
                      (module_ident,))
    ruleset_id = db_cursor.fetchone()[0]

    recipe_ids = target(module_ident, db_cursor)

    assert recipe_ids == (ruleset_id, None)

    # Delete the ruleset, to the no-recipe unbake

    db_cursor.execute("DELETE FROM module_files "
                      "WHERE filename = 'ruleset.css' "
                      "AND  module_ident = %s ", (module_ident,))

    recipe_ids = target(module_ident, db_cursor)

    assert recipe_ids == (None, None)

    # Set a print_style w/ linked recipe
    db_cursor.execute("UPDATE modules "
                      "SET print_style = %s "
                      "WHERE module_ident = %s",
                      ('style_with_recipe_one', module_ident))

    recipe_ids = target(module_ident, db_cursor)

    assert recipe_ids == (recipes[0], None)

    # Fake successful baking, to see fallback

    db_cursor.execute("UPDATE modules "
                      "SET recipe = %s, stateid = 1 "
                      "WHERE module_ident = %s",
                      (recipes[1], module_ident))

    recipe_ids = target(module_ident, db_cursor)

    assert recipe_ids == recipes

    # Set a print_style w/o linked recipe
    db_cursor.execute("UPDATE modules "
                      "SET print_style = %s "
                      "WHERE module_ident = %s",
                      ('style_with_no_recipe', module_ident))

    recipe_ids = target(module_ident, db_cursor)

    assert recipe_ids == (None, recipes[1])


class TestPostPublicationProcessing(object):
    @pytest.fixture(autouse=True)
    def suite_fixture(self, scoped_pyramid_app, complex_book_one,
                      recipes, celery_worker):
        self.binder, ident_mapping = complex_book_one
        self.ident_hash = self.binder.ident_hash
        self.module_ident = ident_mapping[self.binder.ident_hash]
        self.recipes = recipes

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

    def test_duplicate_baking(self, db_cursor):
        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event1 = self.make_event()

        self.target(event1)

        # While the baking is happening, if the module state is set to
        # "post-publication" again, another event is created
        event2 = self.make_event()

        self.target(event2)

        # Check there is only one request being queued
        db_cursor.execute("SELECT count(*) "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s", (self.module_ident,))
        assert db_cursor.fetchone()[0] == 1

    def test_rebaking(self, db_cursor, mocker):
        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.
        event = self.make_event()

        self.target(event)

        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s ", (self.module_ident,))
        result_id = db_cursor.fetchone()[0]

        from celery.result import AsyncResult
        result = AsyncResult(id=result_id)
        result.get()  # blocking operation
        assert result.state == 'SUCCESS'
        assert mock_bake.call_count == 1

        # After baking is finished, if the module state is set to
        # "post-publication" again, another event is created
        event = self.make_event()

        self.target(event)

        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s "
                          "ORDER BY created DESC", (self.module_ident,))
        result_id2 = db_cursor.fetchone()

        assert result_id2 != result_id
        result2 = AsyncResult(id=result_id2)
        result2.get()  # blocking operation
        assert result2.state == 'SUCCESS'
        assert mock_bake.call_count == 2

    def test_no_recipe(self, db_cursor, mocker):
        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')

        # Set up (setUp) creates the content, thus putting it in the
        # post-publication state. We simply create the event associated
        # with that state change.

        event = self.make_event()

        # Delete the ruleset, to follow the no-recipe path

        db_cursor.execute("DELETE FROM module_files "
                          "WHERE filename = 'ruleset.css' "
                          "AND  module_ident = %s ", (self.module_ident,))

        db_cursor.connection.commit()

        self.target(event)

        db_cursor.execute("SELECT result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident = %s ", (self.module_ident,))
        result_id = db_cursor.fetchone()[0]

        from celery.result import AsyncResult
        result = AsyncResult(id=result_id)
        result.get()  # blocking operation
        assert result.state == 'SUCCESS'
        assert mock_bake.call_count == 0

        db_cursor.execute("SELECT recipe, stateid "
                          "FROM modules "
                          "WHERE module_ident = %s ", (self.module_ident,))
        result_recipe, result_stateid = db_cursor.fetchone()

        assert result_recipe is None
        assert result_stateid == 1

    def test_priority(self, db_cursor, mocker, complex_book_one_v2):
        mock_retry = mocker.patch('celery.app.task.Task.retry')
        mock_retry.return_value = Exception('Task can be retried')

        binder_v2, ident_mapping = complex_book_one_v2
        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')
        binder_v2_module_ident = ident_mapping[binder_v2.ident_hash]

        # Create the post publication event for complex book one
        event1 = self.make_event()

        # Create the post publication event for complex book one v2
        event2 = self.make_event(payload=self.make_payload(
            module_ident=binder_v2_module_ident,
            ident_hash=binder_v2.ident_hash))

        self.target(event1)
        self.target(event2)

        db_cursor.execute("SELECT module_ident, result_id::text "
                          "FROM document_baking_result_associations "
                          "WHERE module_ident IN %s",
                          ((self.module_ident, binder_v2_module_ident),))
        result_ids = dict(db_cursor.fetchall())

        from celery.result import AsyncResult
        result1 = AsyncResult(id=result_ids[self.module_ident])
        with pytest.raises(Exception) as exc_info:
            result1.get()  # blocking operation
            assert str(exc_info.exception) == 'Task can be retried'
            assert mock_retry.call_args_list == [((), {'queue': 'deferred'})]

        result2 = AsyncResult(id=result_ids[binder_v2_module_ident])
        result2.get()  # blocking operation

        assert mock_bake.call_count == 1
        assert mock_bake.call_args[0][0].ident_hash == binder_v2.ident_hash

    def test_recipe_fallback(self, db_cursor, recipes, mocker):
        exc_msg = 'something failed during baking'
        from cnxpublishing.subscribers import bake

        # Set up mock to fail on initial bake, else pass through

        def my_bake(*args, **kwargs):
            if args[1] != recipes[1]:  # recipe_id
                raise Exception(exc_msg)
            else:
                bake(*args, **kwargs)

        mock_bake = mocker.patch('cnxpublishing.subscribers.bake')
        mock_bake.side_effect = my_bake

        # Delete the ruleset
        db_cursor.execute("DELETE FROM module_files "
                          "WHERE filename = 'ruleset.css' "
                          "AND  module_ident = %s ", (self.module_ident,))

        # Set a print_style w/ linked recipe
        db_cursor.execute("UPDATE modules "
                          "SET print_style = %s "
                          "WHERE module_ident = %s",
                          ('style_with_recipe_one', self.module_ident))

        # Fake successful baking, to setup fallback
        db_cursor.execute("UPDATE modules "
                          "SET recipe = %s, stateid = 1 "
                          "WHERE module_ident = %s",
                          (recipes[1], self.module_ident))

        # Put post-publication state back
        db_cursor.execute("UPDATE modules "
                          "SET stateid = 5 "
                          "WHERE module_ident = %s",
                          (self.module_ident,))

        db_cursor.connection.commit()

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

        # Make sure it is marked as 'fallback'.
        db_cursor.execute("SELECT ms.statename, m.recipe "
                          "FROM modules AS m NATURAL JOIN modulestates AS ms "
                          "WHERE module_ident = %s",
                          (self.module_ident,))
        res = db_cursor.fetchone()
        assert res[0] == 'fallback'
        assert res[1] == recipes[1]
