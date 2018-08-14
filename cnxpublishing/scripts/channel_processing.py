# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2017, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""\
This script is used to listen for notifications coming from PostgreSQL.
This script translates the notifications into events that are handled
by this project's logic.

To handle a notification, register an event subscriber for the specific
channel event.
For further instructions see `cnxpublishing.events.PGNotifyEvent`
and `cnxpublishing.events.create_pg_notify_event` (an event factory).

"""
from __future__ import print_function
import logging
import os
import select
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from pyramid.paster import bootstrap, setup_logging
from pyramid.threadlocal import get_current_registry

from cnxpublishing.config import CONNECTION_STRING
from cnxpublishing.events import (
    create_pg_notify_event,
    ChannelProcessingStartUpEvent,
)


logger = logging.getLogger('channel_processing')


def usage(argv):  # pragma: no cover
    cmd = os.path.basename(argv[0])
    print('Usage: {} <config_uri>\n'
          '(example: "{} development.ini")'.format(cmd, cmd),
          file=sys.stderr)
    sys.exit(1)


def _get_channels(settings):  # pragma: no cover
    setting_name = 'channel_processing.channels'
    channels = [channel.strip()
                for channel in settings[setting_name].split(',')
                if channel.strip()]
    return list(channels)


def processor():  # pragma: no cover
    """Churns over PostgreSQL notifications on configured channels.
    This requires the application be setup and the registry be available.
    This function uses the database connection string and a list of
    pre configured channels.

    """
    registry = get_current_registry()
    settings = registry.settings
    connection_string = settings[CONNECTION_STRING]
    channels = _get_channels(settings)

    # Code adapted from
    # http://initd.org/psycopg/docs/advanced.html#asynchronous-notifications
    with psycopg2.connect(connection_string) as conn:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cursor:
            for channel in channels:
                cursor.execute('LISTEN {}'.format(channel))
                logger.debug('Waiting for notifications on channel "{}"'
                             .format(channel))

        registry.notify(ChannelProcessingStartUpEvent())

        rlist = [conn]  # wait until ready for reading
        wlist = []  # wait until ready for writing
        xlist = []  # wait for an "exceptional condition"
        timeout = 5

        while True:
            if select.select(rlist, wlist, xlist, timeout) != ([], [], []):
                conn.poll()
                while conn.notifies:
                    notif = conn.notifies.pop(0)
                    logger.debug('Got NOTIFY: pid={} channel={} payload={}'
                                 .format(notif.pid, notif.channel,
                                         notif.payload))
                    event = create_pg_notify_event(notif)
                    try:
                        registry.notify(event)
                    except Exception:
                        logger.exception('Logging an uncaught exception')


def main(argv=sys.argv):  # pragma: no cover
    if len(argv) < 2:
        usage(argv)

    config_uri = argv[1]
    bootstrap(config_uri)
    setup_logging(config_uri)

    processor()


if __name__ == '__main__':
    main()
