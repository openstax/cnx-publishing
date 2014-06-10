# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import datetime
import uuid
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

import cnxepub
import psycopg2
from cnxarchive.utils import join_ident_hash
from webob import Request
from pyramid import testing

from . import use_cases
from .testing import (
    integration_test_settings,
    db_connection_factory,
    db_connect,
    )


class PublishUtilityTestCase(unittest.TestCase):
    """Unit tests for publish specific utilities."""

    def test_model_to_portaltype(self):
        """Model types to legacy portal type names."""
        from ..publish import _model_to_portaltype as target
        document = cnxepub.Document.__new__(cnxepub.Document)
        self.assertEqual(target(document), 'Module')
        binder = cnxepub.Binder.__new__(cnxepub.Binder)
        self.assertEqual(target(binder), 'Collection')
        ugly = object()
        with self.assertRaises(ValueError):
            target(ugly)


class PublishIntegrationTestCase(unittest.TestCase):
    """Verify publication interactions with the archive database."""

    settings = None
    db_conn_str = None
    db_connect = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())

    def setUp(self):
        from cnxarchive.database import initdb
        initdb({'db-connection-string': self.db_conn_str})
        from ..db import initdb
        initdb(self.db_conn_str)
        self.config = testing.setUp(settings=self.settings)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def make_document(self, id=None, content=None, metadata=None):
        if content is None:
            content = io.BytesIO(b'<p>Blank.</p>')
        document = cnxepub.Document(id, content,
                                    metadata=metadata)
        return document

    def test_document_insertion_wo_id_n_version(self):
        """\
        Check that document insertion code inserts a documents's metadata
        into the archive.
        The scope of this test and its function is the metadata,
        not the content associated with it.
        """
        metadata = {
            'title': "Dingbat's Dilemma",
            'language': 'en-us',
            'summary': "The options are limitless.",
            'created': '1420-02-03 23:36:20.583149-05',
            'revised': '1420-02-03 23:36:20.583149-05',
            'license_url': 'http://creativecommons.org/licenses/by/3.0/',
            # XXX We don't have a mapping.
            'publishers': [{'id': 'ream', 'type': None}],
            'authors': [{'id': 'rbates', 'type': 'cnx-id',
                         'name': 'Richard Bates'},],
            'editors': [{'id': 'jone', 'type': None},
                        {'id': 'kahn', 'type': None}],
            # XXX We don't have a mapping.
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],
            'translators': [{'id': 'RhowandaOkofarBates', 'type': None},
                            {'id': 'JamesOrwel', 'type': None}],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            }
        publisher = 'ream'
        message = 'no msg'
        document = self.make_document(metadata=metadata)

        from ..publish import _insert_metadata
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                ident_hash = _insert_metadata(cursor, document,
                                              publisher, message)[1]

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT
  m.name, m.language, a.abstract, l.url,
  m.major_version, m.minor_version,
  m.authors, m.submitter, m.submitlog, m.maintainers,
  m.licensors, m.parentauthors, m.google_analytics, m.buylink,
  m.created, m.revised
FROM
  modules AS m
  NATURAL JOIN abstracts AS a
  LEFT JOIN licenses AS l ON m.licenseid = l.licenseid
WHERE m.uuid||'@'||concat_ws('.',m.major_version,m.minor_version) = %s
""", (ident_hash,))
                module = cursor.fetchone()

        self.assertEqual(module[0], metadata['title'])
        self.assertEqual(module[1], metadata['language'])
        self.assertEqual(module[2], metadata['summary'])
        self.assertEqual(module[3], metadata['license_url'])
        self.assertEqual(module[4], 1)
        self.assertEqual(module[5], None)
        self.assertEqual(module[6],
                         [x['id'] for x in metadata['authors']])
        self.assertEqual(module[7], publisher)
        self.assertEqual(module[8], message)
        self.assertEqual(module[9], None)  # TODO maintainers list?
        self.assertEqual(module[10],
                         [x['id'] for x in metadata['copyright_holders']])
        self.assertEqual(module[11], None)  # TODO parent authors?
        self.assertEqual(module[12], None)  # TODO analytics code?
        self.assertEqual(module[13], None)  # TODO buy link?

        # datetimes in UTC
        created = datetime.datetime(1420, 2, 4, 4, 36)
        revised = datetime.datetime.utcnow()
        self.assertEqual(module[14].utctimetuple()[:5],
                         created.timetuple()[:5])
        self.assertEqual(module[15].utctimetuple()[:5],
                         revised.timetuple()[:5])

        # Check the roles...
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
WITH module AS (
  SELECT module_ident
  FROM modules AS m
  WHERE m.uuid||'@'||m.major_version = %s)
SELECT r.roleparam, mor.personids
FROM moduleoptionalroles AS mor NATURAL JOIN roles AS r
WHERE mor.module_ident = (SELECT module_ident from module)
""", (ident_hash,))
                roles = dict(cursor.fetchall())
        self.assertEqual(roles['authors'],
                         [x['id'] for x in metadata['authors']])
        self.assertEqual(roles['licensors'],
                         [x['id'] for x in metadata['copyright_holders']])
        self.assertEqual(roles['translators'],
                         [x['id'] for x in metadata['translators']])

    def test_document_insertion_w_id_n_version_provided(self):
        id, version = '3a70f722-b7b0-4b41-83dd-2790cee98c39', '1'
        expected_ident_hash = join_ident_hash(id, version)
        metadata = {
            'version': version,
            'title': "Dingbat's Dilemma",
            'language': 'en-us',
            'summary': "The options are limitless.",
            'created': '1420-02-03 23:36:20.583149-05',
            'revised': '1420-02-03 23:36:20.583149-05',
            'license_url': 'http://creativecommons.org/licenses/by/3.0/',
            # XXX We don't have a mapping.
            'publishers': [{'id': 'ream', 'type': None}],
            'authors': [{'id': 'rbates', 'type': 'cnx-id',
                         'name': 'Richard Bates'},],
            'editors': [{'id': 'jone', 'type': None},
                        {'id': 'kahn', 'type': None}],
            # XXX We don't have a mapping.
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],
            'translators': [{'id': 'RhowandaOkofarBates', 'type': None},
                            {'id': 'JamesOrwel', 'type': None}],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            'version': version,
            }
        publisher = 'ream'
        message = 'no msg'
        document = self.make_document(id=id, metadata=metadata)

        from ..publish import _insert_metadata
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                ident_hash = _insert_metadata(cursor, document,
                                              publisher, message)[1]

        self.assertEqual(ident_hash, expected_ident_hash)

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT m.name, uuid::text, m.major_version, m.minor_version
FROM modules AS m
WHERE m.uuid||'@'||concat_ws('.',m.major_version,m.minor_version) = %s
""", (ident_hash,))
                module = cursor.fetchone()

        self.assertEqual(module[0], metadata['title'])
        self.assertEqual(module[1], id)
        self.assertEqual(module[2], int(version))
        self.assertEqual(module[3], None)

    def test_document_w_derived_from(self):
        id, version = '3a70f722-b7b0-4b41-83dd-2790cee98c39', '1'
        expected_ident_hash = join_ident_hash(id, version)
        metadata = {
            'version': version,
            'title': "Dingbat's Dilemma",
            'language': 'en-us',
            'summary': "The options are limitless.",
            'created': '1420-02-03 23:36:20.583149-05',
            'revised': '1420-02-03 23:36:20.583149-05',
            'license_url': 'http://creativecommons.org/licenses/by/3.0/',
            'publishers': [{'id': 'ream', 'type': None}],  # XXX We don't have a mapping.
            'authors': [{'id': 'rbates', 'type': 'cnx-id',
                         'name': 'Richard Bates'},],
            'editors': [{'id': 'jone', 'type': None}, {'id': 'kahn', 'type': None}],
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],  # XXX We don't have a mapping.
            'translators': [{'id': 'RhowandaOkofarBates', 'type': None},
                            {'id': 'JamesOrwel', 'type': None}],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            }
        publisher = 'ream'
        message = 'no msg'
        document = self.make_document(id=id, metadata=metadata)

        from ..publish import _insert_metadata
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                ident_hash = _insert_metadata(cursor, document,
                                              publisher, message)[1]

        self.assertEqual(ident_hash, expected_ident_hash)

        metadata = {
            'title': "Copy of Dingbat's Dilemma",
            'language': 'en-us',
            'summary': "The options are limitless.",
            'created': '1420-02-03 23:36:20.583149-05',
            'revised': '1420-02-03 23:36:20.583149-05',
            'license_url': 'http://creativecommons.org/licenses/by/3.0/',
            'publishers': [{'id': 'someone', 'type': None}],  # XXX We don't have a mapping.
            'authors': [{'id': 'someone', 'type': 'cnx-id',
                         'name': 'Someone'},],
            'editors': [],
            'illustrators': [],  # XXX We don't have a mapping.
            'translators': [],
            'copyright_holders': [{'id': 'someone', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            'derived_from_uri': 'http://cnx.org/contents/{}'.format(ident_hash),
            }
        publisher = 'someone'
        message = 'derived a copy'
        document = self.make_document(metadata=metadata)

        from ..publish import _insert_metadata
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                derived_ident_hash = _insert_metadata(cursor, document,
                                              publisher, message)[1]

        self.assertNotEqual(derived_ident_hash.split('@')[0], ident_hash.split('@')[0])
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT m.name, pm.uuid || '@' || concat_ws('.', pm.major_version, pm.minor_version), m.parentauthors
FROM modules m JOIN modules pm ON m.parent = pm.module_ident
WHERE m.uuid || '@' || concat_ws('.', m.major_version, m.minor_version) = %s
""", (derived_ident_hash,))
                title, parent, parentauthors = cursor.fetchone()

        self.assertEqual(title, "Copy of Dingbat's Dilemma")
        self.assertEqual(parent, ident_hash)
        self.assertEqual(parentauthors, ['rbates'])


class RepublishTestCase(unittest.TestCase):
    """Verify republication of binders that contain share documents
    with the publication context.
    """

    settings = None
    db_conn_str = None

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]

    def setUp(self):
        from cnxarchive.database import initdb
        initdb({'db-connection-string': self.db_conn_str})
        from ..db import initdb
        initdb(self.db_conn_str)
        self.config = testing.setUp(settings=self.settings)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def call_target(self, *args, **kwargs):
        from ..publish import republish_binders
        return republish_binders(*args, **kwargs)

    @db_connect
    def test_republish(self, cursor):
        """Verify republishing of binders in shared document situations."""
        # * Set up three collections in the archive. These are used
        # two of the three will be republished as minor versions.
        # The other will be part of the main publication context,
        # who's insertion into archive is outside the scope of this
        # test case.
        book_one = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        book_two = use_cases.setup_COMPLEX_BOOK_TWO_in_archive(self, cursor)
        book_three = use_cases.setup_COMPLEX_BOOK_THREE_in_archive(self, cursor)

        # * Make a new publication of book three.
        book_three.metadata['version'] = '2.1'
        book_three[0].metadata['version'] = '2'
        book_three[1].metadata['version'] = '2'
        from ..publish import publish_model
        for model in (book_three[0], book_three[1], book_three,):
            ident_hash = publish_model(cursor, model, 'tester', 'test pub')
            model.set_uri('cnx-archive', '/contents/{}'.format(ident_hash))

        # * Invoke the republish logic.
        self.call_target(cursor, [book_three])

        # * Ensure book one and two have been republished.
        # We can ensure this through checking for the existence of the
        # collection tree and the updated contents.
        cursor.execute("SELECT tree_to_json(%s, '1.2')::json", (book_one.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408@1.2',
            u'title': u'Book of Infinity',
            u'contents': [
                {u'id': u'subcol',
                 u'title': u'Part One',
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@1',
                      u'title': u'Document One'},
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'title': u'Part Two',
                 u'contents': [
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@1',
                      u'title': u'Document Three'},
                     {u'id': u'deadbeef-a927-4652-9a8d-deb2d28fb801@2',
                      u'title': u'Document Four'}],
                 }],
            }
        self.assertEqual(tree, expected_tree)
        cursor.execute("SELECT tree_to_json(%s, '1.2')::json", (book_two.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'dbb28a6b-cad2-4863-986f-6059da93386b@1.2',
            u'title': u'Book of Infinity',
            u'contents': [
                {u'id': u'subcol',
                 u'title': u'Part One',
                 u'contents': [
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'title': u'Document One'},
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@1',
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'title': u'Part Two',
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@1',
                      u'title': u'Document Three'}],
                 }],
            }
        self.assertEqual(tree, expected_tree)
