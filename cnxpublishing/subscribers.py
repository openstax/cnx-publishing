# -*- coding: utf-8 -*-
from __future__ import absolute_import

import logging

from celery.exceptions import SoftTimeLimitExceeded
from cnxarchive.scripts import export_epub
from pyramid.events import subscriber
from pyramid.threadlocal import get_current_registry


from . import events, utils
from .bake import remove_baked, bake
from .db import (
    update_module_state,
    with_db_cursor,
)
from .tasks import task


logger = logging.getLogger('cnxpublishing')


@with_db_cursor
def track_baking_proc_state(result, module_ident, cursor):
    cursor.execute('INSERT INTO document_baking_result_associations '
                   '(module_ident, result_id) VALUES (%s, %s)',
                   (module_ident, result.id))


@subscriber(events.PostPublicationEvent)
@with_db_cursor
def post_publication_processing(event, cursor):
    """Process post-publication events coming out of the database."""
    module_ident, ident_hash = event.module_ident, event.ident_hash

    celery_app = get_current_registry().celery_app

    # Check baking is not already queued.
    cursor.execute('SELECT status '
                   'FROM document_baking_result_associations d '
                   'JOIN celery_taskmeta t ON d.result_id::text = t.task_id '
                   'WHERE module_ident = %s', (module_ident,))
    for result in cursor.fetchall():
        state = result[0]
        if state in ('QUEUED', 'STARTED', 'RETRY'):
            logger.debug('Already queued module_ident={} ident_hash={}'.format(
                module_ident, ident_hash))
            return

    logger.debug('Queued for processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    recipe_ids = _get_recipe_ids(module_ident, cursor)
    update_module_state(cursor, module_ident, 'processing', recipe_ids[0])
    # Commit the state change before preceding.
    cursor.connection.commit()

    # Start of task
    # FIXME Looking up the task isn't the most clear usage here.
    task_name = 'cnxpublishing.subscribers.baking_processor'
    baking_processor = celery_app.tasks[task_name]
    result = baking_processor.delay(module_ident, ident_hash)
    baking_processor.backend.store_result(result.id, None, 'QUEUED')

    # Save the mapping between a celery task and this event.
    track_baking_proc_state(result, module_ident, cursor)


def _get_recipe_ids(module_ident, cursor):
    """Returns a tuple of length 2 of primary and fallback recipe ids.

    The primary will be based on the print_style of the book. It is the first
    of:
        1. default recipe currently associated with the print_style of the book
           being baked (defined by module_ident)
        2. A CSS file associated with this book that is named the same as the
           print_style
        3. A CSS file associated with this book that is named 'ruleset.css'

        The fallback is the recipe used for last successful bake of this book,
        if different than the primary. Either value or both values may be
        None"""

    cursor.execute("""select coalesce(dpsf.fileid, mf.fileid, mf2.fileid),
                         CASE
                           WHEN lm.recipe != coalesce(dpsf.fileid,
                                                      mf.fileid,
                                                      mf2.fileid,0)
                             THEN lm.recipe
                             ELSE NULL
                         END
                      FROM modules m LEFT JOIN default_print_style_recipes dpsf
                                         ON m.print_style = dpsf.print_style
                                     LEFT JOIN module_files mf
                                         ON m.module_ident = mf.module_ident
                                         AND m.print_style = mf.filename
                                     LEFT JOIN module_files mf2
                                         ON m.module_ident = mf2.module_ident
                                         AND mf2.filename = 'ruleset.css'
                                     LEFT JOIN latest_modules lm
                                         ON m.uuid = lm.uuid
                      WHERE m.module_ident = %s""", (module_ident,))
    return cursor.fetchone()


@task(bind=True, time_limit=14400, soft_time_limit=10800)
@with_db_cursor
def baking_processor(self, module_ident, ident_hash, cursor=None):
    try:
        if self.request.retries == 0:
            cursor.execute("""\
SELECT module_ident, ident_hash(uuid, major_version, minor_version)
FROM modules NATURAL JOIN modulestates
WHERE uuid = %s AND statename IN ('post-publication', 'processing')
ORDER BY major_version DESC, minor_version DESC""",
                           (utils.split_ident_hash(ident_hash)[0],))
            latest_module_ident = cursor.fetchone()
            if latest_module_ident:
                if latest_module_ident[0] != module_ident:
                    logger.debug("""\
More recent version (module_ident={} ident_hash={}) in queue. \
Move this message (module_ident={} ident_hash={}) \
to the deferred (low priority) queue"""
                                 .format(latest_module_ident[0],
                                         latest_module_ident[1],
                                         module_ident, ident_hash))

                    raise self.retry(queue='deferred')
            else:
                # In case we can't find the latest version being baked, we'll
                # continue with baking this one
                pass

        logger.debug('Starting baking module_ident={} ident_hash={}'
                     .format(module_ident, ident_hash))

        recipe_ids = _get_recipe_ids(module_ident, cursor)

        state = 'current'
        if recipe_ids[0] is None:
            remove_baked(ident_hash, cursor=cursor)
            logger.debug('Finished unbaking module_ident={} ident_hash={} '
                         'with a final state of \'{}\'.'
                         .format(module_ident, ident_hash, state))
            update_module_state(cursor, module_ident, state, None)
            return

        try:
            binder = export_epub.factory(ident_hash)
        except:  # noqa: E722
            logger.exception('Logging an uncaught exception during baking'
                             'ident_hash={} module_ident={}'
                             .format(ident_hash, module_ident))
            # FIXME If the top module doesn't exist, this is going to fail.
            update_module_state(cursor, module_ident, 'errored', None)
            raise
        finally:
            logger.debug('Exported module_ident={} ident_hash={}'
                         .format(module_ident, ident_hash))

        cursor.execute("""\
SELECT submitter, submitlog FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                       (ident_hash,))
        publisher, message = cursor.fetchone()
        remove_baked(ident_hash, cursor=cursor)

        for recipe_id in recipe_ids:
            try:
                bake(binder, recipe_id, publisher, message, cursor=cursor)
            except Exception:
                if state == 'current' and recipe_ids[1] is not None:
                    state = 'fallback'
                    logger.exception('Exception while baking module {}.'
                                     'Falling back...'
                                     .format(module_ident))
                    continue
                else:
                    state = 'errored'
                    # TODO rollback to pre-removal of the baked content??
                    cursor.connection.rollback()
                    logger.exception('Uncaught exception while'
                                     'baking module {}'
                                     .format(module_ident))
                    update_module_state(cursor, module_ident, state, recipe_id)
                    raise
            else:
                logger.debug('Finished baking module_ident={} ident_hash={} '
                             'with a final state of \'{}\'.'
                             .format(module_ident, ident_hash, state))
                update_module_state(cursor, module_ident, state, recipe_id)
                break
    except SoftTimeLimitExceeded:
        logger.exception('Baking timed out for module {}'
                         .format(module_ident))
        update_module_state(cursor, module_ident, 'errored', None)


@subscriber(events.ChannelProcessingStartUpEvent)
@with_db_cursor
def post_publication_start_up(event, cursor):
    # If you make changes to the payload, be sure to update the trigger
    # code as well.
    cursor.execute("""\
SELECT pg_notify('post_publication',
                 '{"module_ident": '||
                 module_ident||
                 ', "ident_hash": "'||
                 ident_hash(uuid, major_version, minor_version)||
                 '", "timestamp": "'||
                 CURRENT_TIMESTAMP||
                 '"}')
FROM modules
WHERE stateid = (
    SELECT stateid
    FROM modulestates
    WHERE statename = 'post-publication');""")


__all__ = (
    'post_publication_processing',
    'post_publication_start_up',
)
