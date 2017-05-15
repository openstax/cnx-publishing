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
def subscriber(event, cursor):
    data = json.dumps({'channel': event.channel,
                       'payload': event.payload})
    cursor.execute('INSERT INTO faux_channel_received (data) values (%s)',
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

        cursor.execute('CREATE TABLE IF NOT EXISTS "faux_channel_received" '
                       '("id" SERIAL PRIMARY KEY, "data" JSON)')

    def tearDown(self):
        # Terminate the post publication worker script.
        if hasattr(self, 'process') and self.process.is_alive():
            self.process.terminate()
        if hasattr(self, 'subscribers'):
            delattr(self, 'subscribers')
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

    def add_subscriber(self, subscriber):
        if not hasattr(self, 'subscribers'):
            self.subscribers = []
        self.subscribers.append(subscriber)

    def test_usage(self):
        self.target(args=())
        self.process.join()
        self.assertEqual(1, self.process.exitcode)

    @mock.patch('cnxpublishing.scripts.channel_processing.bootstrap')
    def target(self, mocked_bootstrap, args=(config_uri(),)):

        def wrapped_bootstrap(config_uri, request=None, options=None):
            bootstrap_info = bootstrap(config_uri, request, options)
            registry = bootstrap_info['registry']
            # Register the test subscriber
            for subscriber in self.subscribers:
                from cnxpublishing.events import PGNotifyEvent
                registry.registerHandler(subscriber, (PGNotifyEvent,))
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
    def test(self, cursor):
        self.add_subscriber(subscriber)
        self.target()

        payload = {'a': 25, 'b': 24, 'c': 23}
        self.make_one('faux_channel', payload)

        cursor.execute('SELECT data FROM faux_channel_received')
        data = cursor.fetchone()[0]
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


class DeprecatedChannelProcessingTestCase(unittest.TestCase):
    @db_connect
    def setUp(self, cursor):
        settings = integration_test_settings()
        from ...config import CONNECTION_STRING
        self.db_conn_str = settings[CONNECTION_STRING]

        # Initialize database
        init_db(self.db_conn_str, True)

    def tearDown(self):
        # Terminate the post publication worker script.
        if hasattr(self, 'process') and self.process.is_alive():
            self.process.terminate()

        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")

    def target(self, args=(config_uri(),)):
        from ...scripts.channel_processing import main

        # Start the post publication worker script.
        # (The post publication worker is in an infinite loop, this is a way to
        # test it)
        args = ('cnx-publishing-channel-processing',) + args
        self.process = Process(target=main, args=(args,))
        self.process.start()

    @db_connect
    def test_revised_module_inserted(self, cursor):
        self.target()

        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()

        revised = deepcopy(use_cases.COMPLEX_BOOK_ONE)
        revised.id = binder.id
        revised.metadata['cnx-archive-uri'] = binder.id
        revised.metadata['version'] = '2.1'
        revised[0][0] = binder[0][0]
        revised[0][1] = binder[0][1]
        revised[1][0] = binder[1][0]
        revised[1][1] = binder[1][1]

        revised.resources.append(
            cnxepub.Resource(
                'ruleset.css',
                io.BytesIO("""\
p.para {
  content: "Ruleset applied";
}

/* copied from cnx-recipes books/rulesets/output/physics.css */
body > div[data-type="page"]:pass(20)::after,
body > div[data-type="composite-page"]:pass(20)::after {
  content: pending(page-link);
  move-to: eob-toc;
  container: li;
}
body > div[data-type='chapter'] > h1[data-type='document-title']:pass(20) {
  copy-to: eoc-toc;
}
body > div[data-type='chapter'] > div[data-type="page"]:pass(20),
body > div[data-type='chapter'] > div[data-type="composite-page"]:pass(20) {
  string-set: page-idi attr(id);
}
body > div[data-type='chapter'] > div[data-type="page"] > [data-type='document-title']:pass(20),
body > div[data-type='chapter'] > div[data-type="composite-page"] > [data-type='document-title']:pass(20) {
  copy-to: page-title;
}
body > div[data-type='chapter'] > div[data-type="page"]:pass(20)::after,
body > div[data-type='chapter'] > div[data-type="composite-page"]:pass(20)::after {
  content: pending(page-title);
  attr-href: "#" string(page-id);
  container: a;
  move-to: page-link;
}
body > div[data-type='chapter'] > div[data-type="page"]:pass(20)::after,
body > div[data-type='chapter'] > div[data-type="composite-page"]:pass(20)::after {
  content: pending(page-link);
  move-to: eoc-toc-pages;
  container: li;
}
body > div[data-type='chapter']:pass(20)::after {
  content: pending(eoc-toc-pages);
  container: ol;
  class: chapter;
  move-to: eoc-toc;
}
body > div[data-type='chapter']:pass(20)::after {
  content: pending(eoc-toc);
  container: li;
  move-to: eob-toc;
}
body > div[data-type="unit"] > h1[data-type='document-title']:pass(20) {
  copy-to: eou-toc;
}
body > div[data-type="unit"] > div[data-type='chapter'] > h1[data-type='document-title']:pass(20) {
  copy-to: eoc-toc;
}
body > div[data-type="unit"] > div[data-type='chapter'] > div[data-type="page"] > [data-type='document-title']:pass(20),
body > div[data-type="unit"] > div[data-type='chapter'] div[data-type="composite-page"] > [data-type='document-title']:pass(20) {
  copy-to: page-title;
}
body > div[data-type="unit"] > div[data-type='chapter'] > div[data-type="page"]:pass(20)::after,
body > div[data-type="unit"] > div[data-type='chapter'] div[data-type="composite-page"]:pass(20)::after {
  content: pending(page-title);
  move-to: eoc-toc-pages;
  container: li;
}
body > div[data-type="unit"] > div[data-type='chapter']:pass(20)::after {
  content: pending(eoc-toc-pages);
  container: ol;
  class: chapter;
  move-to: eoc-toc;
}
body > div[data-type="unit"] > div[data-type='chapter']:pass(20)::after {
  content: pending(eoc-toc);
  container: li;
  move-to: eou-toc-chapters;
}
body > div[data-type="unit"]:pass(20)::after {
  content: pending(eou-toc-chapters);
  container: ol;
  class: unit;
  move-to: eou-toc;
}
body > div[data-type="unit"]:pass(20)::after {
  content: pending(eou-toc);
  container: li;
  move-to: eob-toc;
}
nav#toc:pass(30) {
  content: '';
}
nav#toc:pass(30)::after {
  content: pending(eob-toc);
  container: ol;
}
"""),
                'text/css',
                filename='ruleset.css'))

        from ...publish import publish_model
        publisher = 'karenc'
        publication_message = 'Added a ruleset'
        publish_model(cursor, revised, publisher, publication_message)
        cursor.connection.commit()

        cursor.execute("""\
SELECT module_ident FROM modules
WHERE portal_type = 'Collection'
ORDER BY module_ident DESC LIMIT 1""")
        module_ident = cursor.fetchone()[0]

        wait_for_module_state(module_ident)

        cursor.execute("""\
SELECT nodeid, is_collated FROM trees WHERE documentid = %s
ORDER BY nodeid""", (module_ident,))
        is_collated = [i[1] for i in cursor.fetchall()]
        self.assertEqual([False, True], is_collated)

        content = get_collated_content(
            revised[0][0].ident_hash, revised.ident_hash, cursor)
        self.assertIn('Ruleset applied', content[:])

        cursor.execute("""\
SELECT state FROM post_publications
WHERE module_ident = %s ORDER BY timestamp DESC""", (module_ident,))
        self.assertEqual('Done/Success', cursor.fetchone()[0])

    @db_connect
    @mock.patch('cnxpublishing.subscribers.remove_baked')
    def test_error_handling(self, cursor, mock_remove_collation):
        from ...scripts import channel_processing
        from ...bake import remove_baked

        # Fake remove_baked, the first time it's called, it will raise an
        # exception, after that it'll call the normal remove_baked function
        class FakeRemoveCollation(object):
            # this is necessary inside a class because just a variable "count"
            # cannot be accessed inside fake_remove_collation
            count = 0

        def fake_remove_collation(*args, **kwargs):
            if FakeRemoveCollation.count == 0:
                FakeRemoveCollation.count += 1
                raise Exception('something failed during collation')
            return remove_baked(*args, **kwargs)

        mock_remove_collation.side_effect = fake_remove_collation

        self.target()

        binder1 = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        binder2 = use_cases.setup_COMPLEX_BOOK_TWO_in_archive(self, cursor)
        cursor.connection.commit()

        cursor.execute("""\
SELECT module_ident FROM modules
WHERE portal_type = 'Collection'
ORDER BY module_ident DESC LIMIT 2""")

        ((module_ident1,), (module_ident2,)) = cursor.fetchall()

        wait_for_module_state(module_ident1)
        wait_for_module_state(module_ident2)

        cursor.execute("""\
SELECT stateid FROM modules
WHERE module_ident IN %s""", ((module_ident1, module_ident2),))

        # make sure one is marked as "errored" and the other one "current"
        self.assertEqual([(1,), (7,)], sorted(cursor.fetchall()))

        cursor.execute("""\
SELECT state FROM post_publications
WHERE module_ident IN %s""", ((module_ident1, module_ident2),))
        self.assertEqual(
            ['Done/Success', 'Failed/Error', 'Processing', 'Processing'],
            sorted([i[0] for i in cursor.fetchall()]))
