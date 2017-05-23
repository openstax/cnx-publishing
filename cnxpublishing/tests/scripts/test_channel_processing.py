# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import json
import time
import unittest
from multiprocessing import Process
try:
    from unittest import mock
except ImportError:
    import mock

import psycopg2
from pyramid import testing
from pyramid.paster import bootstrap

from ..testing import (
    config_uri,
    db_connect,
    integration_test_settings,
)


@db_connect
def start_up_subscriber(event, cursor):
    data = json.dumps({'channel': None,
                       'payload': '{"msg": "start up"}'})
    cursor.execute('INSERT INTO notify_received (data) values (%s)',
                   (data,))


@db_connect
def subscriber(event, cursor):
    data = json.dumps({'channel': event.channel,
                       'payload': event.payload})
    cursor.execute('INSERT INTO notify_received (data) values (%s)',
                   (data,))


def error_subscriber(event):
    raise Exception('forced exception for testing purposes')


class ChannelProcessingTestCase(unittest.TestCase):

    settings = None
    db_conn_str = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]

    @db_connect
    def setUp(self, cursor):
        self.config = testing.setUp(settings=self.settings)

        cursor.execute('CREATE TABLE IF NOT EXISTS "notify_received" '
                       '("id" SERIAL PRIMARY KEY, "data" JSON)')

    @db_connect
    def tearDown(self, cursor):
        # Terminate the post publication worker script.
        if hasattr(self, 'process') and self.process.is_alive():
            self.process.terminate()
        if hasattr(self, 'subscribers'):
            delattr(self, 'subscribers')
        cursor.execute('DELETE FROM notify_received *')
        testing.tearDown()

    @classmethod
    def tearDownClass(cls):
        with psycopg2.connect(cls.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")

    @db_connect
    def make_one(self, cursor, channel, payload):
        """Create a Postgres notification"""
        pl = json.dumps(payload)
        cursor.execute("select pg_notify(%s, %s);", (channel, pl,))
        cursor.connection.commit()
        # Wait for the channel processor to process the notification.
        time.sleep(1)

    def add_subscriber(self, subscriber, event_cls=None):
        if not hasattr(self, 'subscribers'):
            self.subscribers = []
        if event_cls is None:
            from cnxpublishing.events import PGNotifyEvent
            event_cls = PGNotifyEvent
        self.subscribers.append((subscriber, event_cls,))

    def test_usage(self):
        self.target(args=())
        self.process.join()
        self.assertEqual(1, self.process.exitcode)

    @mock.patch('cnxpublishing.scripts.channel_processing.bootstrap')
    def target(self, mocked_bootstrap, args=(config_uri(),)):

        def wrapped_bootstrap(config_uri, request=None, options=None):
            bootstrap_info = bootstrap(config_uri, request, options)
            registry = bootstrap_info['registry']
            # Unregister handlers
            from cnxpublishing import events
            interfaces = [
                events.ChannelProcessingStartUpEvent,
                events.PostPublicationEvent,
            ]
            handlers = list(registry.registeredHandlers())
            for handler in handlers:
                for iface in handler.required:
                    if iface.inherit in interfaces:
                        registry.unregisterHandler(handler.handler,
                                                   handler.required,
                                                   handler.name)
            # Register the test subscriber
            for subscriber, event_cls in self.subscribers:
                registry.registerHandler(subscriber, (event_cls,))
            return bootstrap_info

        mocked_bootstrap.side_effect = wrapped_bootstrap

        from cnxpublishing.scripts.channel_processing import main
        # Start the post publication worker script.
        # (The post publication worker is in an infinite loop, this is a way to
        # test it)
        args = ('cnx-publishing-channel-processing',) + args
        self.process = Process(target=main, args=(args,))
        self.process.start()
        # Wait for the process to fully start.
        time.sleep(1)

    @db_connect
    def test_on_start_up(self, cursor):
        from cnxpublishing.events import ChannelProcessingStartUpEvent
        self.add_subscriber(start_up_subscriber,
                            ChannelProcessingStartUpEvent)
        self.target()

        cursor.execute('SELECT data FROM notify_received')
        data = cursor.fetchone()[0]
        assert data['channel'] is None
        assert data['payload'] == '{"msg": "start up"}'

    @db_connect
    def test_in_loop(self, cursor):
        self.add_subscriber(subscriber)
        self.target()

        channel = 'faux_channel'
        payload = {'a': 25, 'b': 24, 'c': 23}
        self.make_one(channel, payload)

        cursor.execute('SELECT data FROM notify_received')
        data = cursor.fetchone()[0]
        assert data['channel'] == channel
        assert data['payload'] == payload

    def test_error_recovery(self):
        self.add_subscriber(error_subscriber)
        self.target()

        payload = {'error': 0, 'bug': '*.*'}
        self.make_one('faux_channel', payload)

        # Unfortunately there isn't an easy way to test for the logging
        # output from an exception. So the best we can do is check to see
        # if the process continues running.
        # You can see this in action if you configure the logger in the
        # testing.ini file.

        assert self.process.is_alive()
