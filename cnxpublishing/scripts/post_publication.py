# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import print_function
import logging
import os
import select
import sys
import traceback

from cnxarchive.scripts import export_epub
from cnxepub.formatters import exercise_callback_factory
import psycopg2
import psycopg2.extensions
from pyramid.paster import bootstrap
from pyramid.threadlocal import get_current_registry

from ..collation import remove_collation, collate
from ..config import CONNECTION_STRING


logger = logging.getLogger('post_publication')
CHANNEL = 'post_publication'


def set_post_publications_state(cursor, module_ident, state_name,
                                state_message=''):
    cursor.execute("""\
INSERT INTO post_publications
  (module_ident, state, state_message)
  VALUES (%s, %s, %s)""", (module_ident, state_name, state_message))


def update_module_state(cursor, module_ident, state_name):
    logger.debug('Setting module_ident={} state to "{}"'.format(
        module_ident, state_name))
    cursor.execute("""\
UPDATE modules
SET stateid = (
    SELECT stateid FROM modulestates WHERE statename = %s
) WHERE module_ident = %s""", (state_name, module_ident))


def process(cursor, module_ident, ident_hash, includes):
    logger.debug('Processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    set_post_publications_state(cursor, module_ident, 'Processing')
    try:
        binder = export_epub.factory(ident_hash)
    except export_epub.NotFound:
        logger.error('ident_hash={} module_ident={} not found'
                     .format(ident_hash, module_ident))
        update_module_state(cursor, module_ident, 'errored')
        set_post_publications_state(
            cursor, module_ident, 'Failed/Error',
            'ident_hash={} not found'.format(ident_hash))
        return

    cursor.execute("""\
SELECT submitter, submitlog FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                   (ident_hash,))
    publisher, message = cursor.fetchone()
    remove_collation(ident_hash, cursor=cursor)
    collate(binder, publisher, message, cursor=cursor, includes=includes)

    logger.debug('Finished processing module_ident={} ident_hash={}'.format(
        module_ident, ident_hash))
    update_module_state(cursor, module_ident, 'current')
    set_post_publications_state(cursor, module_ident, 'Done/Success')


def post_publication(conn, includes):
    while True:
        with conn.cursor() as cursor:
            # Pick one item that requires post publication and set its state to
            # "processing"
            # See http://dba.stackexchange.com/questions/69471/
            cursor.execute("""\
UPDATE modules
SET stateid = (
    SELECT stateid FROM modulestates WHERE statename = 'processing'
)
FROM (
    SELECT module_ident
    FROM modules
    WHERE stateid = (
        SELECT stateid FROM modulestates WHERE statename = 'post-publication')
    LIMIT 1
    FOR UPDATE
    ) m
WHERE m.module_ident = modules.module_ident
RETURNING modules.module_ident,
          ident_hash(uuid, major_version, minor_version)""")
            try:
                module_ident, ident_hash = cursor.fetchone()
            except TypeError:
                # No more items to process
                return
            try:
                process(cursor, module_ident, ident_hash, includes)
            except Exception as e:
                logger.exception('ident_hash={} module_ident={} error={}'
                                 .format(ident_hash, module_ident, str(e)))
                update_module_state(cursor, module_ident, 'errored')
                set_post_publications_state(
                    cursor, module_ident, 'Failed/Error',
                    ''.join(traceback.format_exception(*sys.exc_info())))


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('Usage: {} <config_uri>\n'
          '(example: "{} development.ini")'.format(cmd, cmd),
          file=sys.stderr)
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]
    bootstrap(config_uri)
    settings = get_current_registry().settings
    connection_string = settings[CONNECTION_STRING]

    exercise_url_template = settings.get('embeddables.exercise.url_template',
                                         None)
    exercise_match = settings.get('embeddables.exercise.match', None)
    exercise_token = settings.get('embeddables.exercise.token', None)
    mathml_url = settings.get('mathmlcloud.url', None)

    includes = None
    if exercise_url_template and exercise_match:
        includes = [exercise_callback_factory(exercise_match,
                                              exercise_url_template,
                                              exercise_token,
                                              mathml_url)]
    # Code adapted from
    # http://initd.org/psycopg/docs/advanced.html#asynchronous-notifications
    with psycopg2.connect(connection_string) as conn:
        conn.set_isolation_level(
            psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            cursor.execute('LISTEN {}'.format(CHANNEL))

        logger.debug('Waiting for notifications on channel "{}"'
                     .format(CHANNEL))
        rlist = [conn]  # wait until ready for reading
        wlist = []  # wait until ready for writing
        xlist = []  # wait for an "exceptional condition"
        timeout = 5

        while True:
            if select.select(rlist, wlist, xlist, timeout) != ([], [], []):
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    logger.debug('Got NOTIFY: pid={} channel={} payload={}'
                                 .format(notify.pid, notify.channel,
                                         notify.payload))
                    post_publication(conn, includes)
