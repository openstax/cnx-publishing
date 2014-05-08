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

from .testing import (
    integration_test_settings,
    db_connection_factory,
    )


here = os.path.abspath(os.path.dirname(__file__))


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
            'publishers': [{'id': 'ream', 'type': None}],
            'authors': [{'id': 'rbates', 'type': 'cnx-id',
                         'name': 'Richard Bates'},],
            'editors': [{'id': 'jone', 'type': None},
                        {'id': 'kahn', 'type': None}],
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
  m.licensors, m.parentauthors, m.google_analytics, m.buylink
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
        self.assertEqual(module[6], [x['id'] for x in metadata['authors']])
        self.assertEqual(module[7], publisher)
        self.assertEqual(module[8], message)
        self.assertEqual(module[9], None)  # TODO maintainers list?
        self.assertEqual(module[10], [x['id'] for x in metadata['copyright_holders']])
        self.assertEqual(module[11], None)  # TODO parent authors?
        self.assertEqual(module[12], None)  # TODO analytics code?
        self.assertEqual(module[13], None)  # TODO buy link?

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
        self.assertEqual(roles['licensors'], [x['id'] for x in metadata['copyright_holders']])
        self.assertEqual(roles['translators'], [x['id'] for x in metadata['translators']])

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
