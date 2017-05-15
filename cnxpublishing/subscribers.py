# -*- coding: utf-8 -*-
import logging

import psycopg2
from cnxarchive.scripts import export_epub
from pyramid.events import subscriber
from pyramid.threadlocal import get_current_registry


from . import events
from .bake import remove_baked, bake
from .db import (
    set_post_publications_state,
    update_module_state,
    with_db_cursor,
)


logger = logging.getLogger('cnxpublishing')


@subscriber(events.PostPublicationEvent)
@with_db_cursor
def post_publication_processing(event, cursor):
    """Process post-publication events coming out of the database."""
    module_ident, ident_hash = event.module_ident, event.ident_hash
    logger.debug('Processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    set_post_publications_state(cursor, module_ident, 'Processing')
    # TODO commit state change
    try:
        binder = export_epub.factory(ident_hash)
    except export_epub.NotFound:  # pragma: no cover
        logger.error('ident_hash={} module_ident={} not found'
                     .format(ident_hash, module_ident))
        # FIXME If the top module entry doesn't exist, this is going to fail.
        try:
            update_module_state(cursor, module_ident, 'errored')
        except psycopg2.Error:
            pass
        set_post_publications_state(
            cursor, module_ident, 'Failed/Error',
            'ident_hash={} or a child node is not found'.format(ident_hash))
        return

    cursor.execute("""\
SELECT submitter, submitlog FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                   (ident_hash,))
    publisher, message = cursor.fetchone()
    remove_baked(ident_hash, cursor=cursor)
    bake(binder, publisher, message, cursor=cursor)

    logger.debug('Finished processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    update_module_state(cursor, module_ident, 'current')
    set_post_publications_state(cursor, module_ident, 'Done/Success')


__all__ = (
    'post_publication_processing',
)
