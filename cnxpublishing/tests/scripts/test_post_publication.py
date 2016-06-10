# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from copy import deepcopy
from contextlib import contextmanager
import io
from multiprocessing import Process
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from cnxarchive.database import get_collated_content
from cnxdb.init import init_db
import cnxepub
import psycopg2

from .. import testing, use_cases


def check_module_state(module_ident):
    connect = testing.db_connection_factory()
    with connect() as db_conn:
        with db_conn.cursor() as cursor:
            while True:
                cursor.execute("""\
SELECT module_ident, stateid FROM modules
    WHERE portal_type = 'Collection'
    ORDER BY module_ident DESC LIMIT 1""")
                module_ident, stateid = cursor.fetchone()

                if stateid in (1, 7):
                    break


def wait_for_module_state(module_ident, timeout=10):
    p = Process(target=check_module_state, args=((module_ident,)))
    p.start()
    p.join(timeout)
    if p.is_alive():
        p.terminate()


class PostPublicationTestCase(unittest.TestCase):
    @testing.db_connect
    def setUp(self, cursor):
        settings = testing.integration_test_settings()
        from ...config import CONNECTION_STRING
        self.db_conn_str = settings[CONNECTION_STRING]

        # Initialize database
        init_db(self.db_conn_str, True)

    def tearDown(self):
        # Terminate the post publication worker script.
        if self.process.is_alive():
            self.process.terminate()

        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")

    def target(self, args=(testing.config_uri(),)):
        from ...scripts.post_publication import main

        # Start the post publication worker script.
        # (The post publication worker is in an infinite loop, this is a way to
        # test it)
        args = ('cnx-publishing-post-publication',) + args
        self.process = Process(target=main, args=(args,))
        self.process.start()

    def test_usage(self):
        self.target(args=())
        self.process.join()
        self.assertEqual(1, self.process.exitcode)

    @testing.db_connect
    def test_new_module_inserted(self, cursor):
        self.target()

        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
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
            binder[0][0].ident_hash, binder.ident_hash, cursor)
        self.assertIn('there will be cake', content[:])

        cursor.execute("""\
SELECT state FROM post_publications
    WHERE module_ident = %s ORDER BY timestamp DESC""", (module_ident,))
        self.assertEqual('Done/Success', cursor.fetchone()[0])

    @testing.db_connect
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

    @testing.db_connect
    @mock.patch('cnxpublishing.scripts.post_publication.remove_collation')
    def test_error_handling(self, cursor, mock_remove_collation):
        from ...scripts import post_publication
        from ...collation import remove_collation

        # Fake remove_collation, the first time it's called, it will raise an
        # exception, after that it'll call the normal remove_collation function
        class FakeRemoveCollation(object):
            # this is necessary inside a class because just a variable "count"
            # cannot be accessed inside fake_remove_collation
            count = 0

        def fake_remove_collation(*args, **kwargs):
            if FakeRemoveCollation.count == 0:
                FakeRemoveCollation.count += 1
                raise Exception('something failed during collation')
            return remove_collation(*args, **kwargs)

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
