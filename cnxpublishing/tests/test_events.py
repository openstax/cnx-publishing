# -*- coding: utf-8 -*-
import json
import unittest


class PGNotifyFactoryTestCase(unittest.TestCase):

    @property
    def target(self):
        from cnxpublishing.events import create_pg_notify_event
        return create_pg_notify_event

    def _make_one(self, payload, channel=None, pid=None):
        """Make a `psycopg2.extensions.Notify` object"""
        if channel is None:
            channel = 'testing'
        if pid is None:
            pid = 5555
        from psycopg2.extensions import Notify
        notif = Notify(pid=pid, channel=channel, payload=payload)
        return notif

    def test_base_pg_notify(self):
        payload = {"item": "cookie"}
        channel = 'mouth'
        pid = 1234
        notif = self._make_one(json.dumps(payload), channel, pid)

        event = self.target(notif)

        from cnxpublishing.events import PGNotifyEvent
        self.assertEqual(type(event), PGNotifyEvent)
        self.assertEqual(event.notification, notif)
        self.assertEqual(event.channel, channel)
        self.assertEqual(event.payload, payload)
        self.assertEqual(event.pid, pid)

    def test_specific_notify_to_event(self):
        payload = {"module_ident": 12, "ident_hash": "ef12ab7@1",
                   "timestamp": "<date>"}
        channel = 'post_publication'
        pid = 1234
        notif = self._make_one(json.dumps(payload), channel, pid)

        event = self.target(notif)

        from cnxpublishing.events import PostPublicationEvent
        self.assertEqual(type(event), PostPublicationEvent)
        self.assertEqual(event.module_ident, payload['module_ident'])
        self.assertEqual(event.ident_hash, payload['ident_hash'])
        self.assertEqual(event.timestamp, payload['timestamp'])

    def test_null_notify_to_event(self):
        payload = None  # null payload
        channel = 'testing'
        pid = 1234
        notif = self._make_one(payload, channel, pid)

        event = self.target(notif)

        from cnxpublishing.events import PGNotifyEvent
        self.assertEqual(type(event), PGNotifyEvent)
        self.assertEqual(event.notification, notif)
        self.assertEqual(event.channel, channel)
        self.assertEqual(event.payload, {})
        self.assertEqual(event.pid, pid)

    def test_blank_notify_to_event(self):
        payload = ''  # blank payload
        channel = 'testing'
        pid = 1234
        notif = self._make_one(payload, channel, pid)

        event = self.target(notif)

        from cnxpublishing.events import PGNotifyEvent
        self.assertEqual(type(event), PGNotifyEvent)
        self.assertEqual(event.notification, notif)
        self.assertEqual(event.channel, channel)
        self.assertEqual(event.payload, {})
        self.assertEqual(event.pid, pid)
