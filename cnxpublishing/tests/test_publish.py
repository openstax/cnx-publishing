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
import unittest

import cnxepub
import psycopg2
from cnxdb.ident_hash import join_ident_hash
from pyramid import testing

from . import use_cases
from .testing import (
    TEST_DATA_DIR,
    integration_test_settings,
    db_connection_factory,
    db_connect,
    init_db,
)
from .test_db import BaseDatabaseIntegrationTestCase


class PublishUtilityTestCase(unittest.TestCase):
    """Unit tests for publish specific utilities."""

    def test_model_to_portaltype(self):
        """Model types to legacy portal type names."""
        from ..publish import _model_to_portaltype as target
        document = cnxepub.Document.__new__(cnxepub.Document)
        self.assertEqual(target(document), 'Module')
        binder = cnxepub.Binder('fooBinder')  # need init to set metadata
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
        init_db(self.db_conn_str)
        self.config = testing.setUp(settings=self.settings)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def make_resource(self, id, data, media_type):
        resource = cnxepub.Resource(id, data, media_type)
        return resource

    def make_document(self, id=None, content=None, metadata=None):
        if content is None:
            content = io.BytesIO(b'<body><p>Blank.</p></body>')
        document = cnxepub.Document(id, content, metadata=metadata)
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
                         'name': 'Richard Bates'}],
            'editors': [{'id': 'jone', 'type': None},
                        {'id': 'kahn', 'type': None}],
            # XXX We don't have a mapping.
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],
            'translators': [{'id': 'RhowandaOkofarBates', 'type': None},
                            {'id': 'JamesOrwel', 'type': None}],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'subjects': ['Arts', 'Business', 'Mathematics and Statistics'],
            'keywords': ['bates', 'dilemma', 'dingbat'],
            'print_style': None,
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
  m.name, m.language, a.html AS abstract, l.url,
  m.major_version, m.minor_version,
  m.authors, m.submitter, m.submitlog, m.maintainers,
  m.licensors, m.parentauthors, m.google_analytics, m.buylink,
  m.created, m.revised
FROM
  modules AS m
  NATURAL JOIN abstracts AS a
  LEFT JOIN licenses AS l ON m.licenseid = l.licenseid
WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s
""", (ident_hash,))
                module = cursor.fetchone()

        summary = b"""\
<div class="description" data-type="description"\
 xmlns="http://www.w3.org/1999/xhtml">
  The options are limitless.
</div>"""

        self.assertEqual(module[0], metadata['title'])
        self.assertEqual(module[1], metadata['language'])
        self.assertEqual(module[2], summary)
        self.assertEqual(module[3], metadata['license_url'])
        self.assertEqual(module[4], 1)
        self.assertEqual(module[5], None)
        self.assertEqual(module[6],
                         [x['id'] for x in metadata['authors']])
        self.assertEqual(module[7], publisher)
        self.assertEqual(module[8], message)
        self.assertEqual(module[9],
                         [x['id'] for x in metadata['publishers']])
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

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                # Grab the module_ident, for easy lookup of related items.
                cursor.execute("""\
SELECT module_ident
FROM modules AS m
WHERE m.uuid||'@'||m.major_version = %s
""", (ident_hash,))
                module_ident = cursor.fetchone()[0]

                # Lookup the roles...
                cursor.execute("""\
SELECT r.roleparam, mor.personids
FROM moduleoptionalroles AS mor NATURAL JOIN roles AS r
WHERE mor.module_ident = %s
""", (module_ident,))
                roles = dict(cursor.fetchall())

                # Lookup the subjects...
                cursor.execute("""\
SELECT t.tag
FROM moduletags AS mt NATURAL JOIN tags AS t
WHERE mt.module_ident = %s
ORDER BY t.tag ASC
""", (module_ident,))
                subjects = [x[0] for x in cursor.fetchall()]

                # Lookup the keywords...
                cursor.execute("""\
SELECT k.word
FROM modulekeywords AS mk NATURAL JOIN keywords AS k
WHERE mk.module_ident = %s
ORDER BY k.word ASC
""", (module_ident,))
                keywords = [x[0] for x in cursor.fetchall()]

        # Check the roles...
        self.assertEqual(roles['translators'],
                         [x['id'] for x in metadata['translators']])
        # Check the subjects...
        self.assertEqual(subjects, metadata['subjects'])
        # Check the keywords...
        self.assertEqual(keywords, metadata['keywords'])

    def test_optional_roles_table_entires(self):
        """
        Check to see if authors and copyright_holders data,
        as well as empty lists from translators and editors
        are not entered into the optional roles table.
        """
        metadata = {
            'title': "Dingbat's Dilemma",
            'language': 'en-us',
            'summary': "The options are limitless.",
            'created': '1420-02-03 23:36:20.583149-05',
            'revised': '1420-02-03 23:36:20.583149-05',
            'license_url': 'http://creativecommons.org/licenses/by/3.0/',
            'publishers': [{'id': 'ream', 'type': None}],
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],
            'subjects': ['Arts', 'Business', 'Mathematics and Statistics'],
            'keywords': ['bates', 'dilemma', 'dingbat'],
            # these values should not be entered into the roles
            # table
            'translators': [],
            'editors': [],
            'authors': [{'id': 'rbates', 'type': 'cnx-id',
                         'name': 'Richard Bates'}, ],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'print_style': None,
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
                # Grab the module_ident, for easy lookup of related items.
                cursor.execute("""\
SELECT module_ident
FROM modules AS m
WHERE m.uuid||'@'||m.major_version = %s
""", (ident_hash,))
                module_ident = cursor.fetchone()[0]

                # Lookup the roles...
                cursor.execute("""\
SELECT r.roleparam, mor.personids
FROM moduleoptionalroles AS mor NATURAL JOIN roles AS r
WHERE mor.module_ident = %s
""", (module_ident,))
                roles = dict(cursor.fetchall())

        # Check to see if roles raises key errors because
        # these entries should not be in the roles table.
        self.assertRaises(KeyError, lambda: roles['translators'])
        self.assertRaises(KeyError, lambda: roles['editors'])
        self.assertRaises(KeyError, lambda: roles['authors'])
        self.assertRaises(KeyError, lambda: roles['licensors'])

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
                         'name': 'Richard Bates'}],
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
            'print_style': None,
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
WHERE ident_hash(m.uuid,m.major_version,m.minor_version) = %s
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
                         'name': 'Richard Bates'}],
            'editors': [{'id': 'jone', 'type': None}, {'id': 'kahn', 'type': None}],
            'illustrators': [{'id': 'AbagaleBates', 'type': None}],  # XXX We don't have a mapping.
            'translators': [{'id': 'RhowandaOkofarBates', 'type': None},
                            {'id': 'JamesOrwel', 'type': None}],
            'copyright_holders': [{'id': 'ream', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            'print_style': '* first print style* ',
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
                         'name': 'Someone'}],
            'editors': [],
            'illustrators': [],  # XXX We don't have a mapping.
            'translators': [],
            'copyright_holders': [{'id': 'someone', 'type': None}],
            'subjects': ['Business', 'Arts', 'Mathematics and Statistics'],
            'keywords': ['dingbat', 'bates', 'dilemma'],
            'derived_from_uri': 'http://cnx.org/contents/{}'.format(ident_hash),
            'print_style': '* second print style* ',
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
SELECT m.name, ident_hash(pm.uuid, pm.major_version, pm.minor_version), m.parentauthors
FROM modules m JOIN modules pm ON m.parent = pm.module_ident
WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s
""", (derived_ident_hash,))
                title, parent, parentauthors = cursor.fetchone()

        self.assertEqual(title, "Copy of Dingbat's Dilemma")
        self.assertEqual(parent, ident_hash)
        self.assertEqual(parentauthors, ['rbates'])

        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT print_style FROM modules m"
                               "    WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s", (ident_hash,))
                print_style = cursor.fetchone()[0]
                self.assertEqual(print_style, '* first print style* ')

                cursor.execute("SELECT print_style FROM modules m"
                               "    WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s", (derived_ident_hash,))
                print_style = cursor.fetchone()[0]
                self.assertEqual(print_style, '* second print style* ')

    def test_double_resource_usage(self):
        """
        Ensure that a document with a resource can be inserted.
        This specifically tests a document with a resource
        that is used more than once within the same document.
        """
        # https://github.com/Connexions/cnx-publishing/issues/94
        resource_path = os.path.join(TEST_DATA_DIR, '85c441fc.png')
        with open(resource_path, 'rb') as f:
            resource = self.make_resource('dummy', io.BytesIO(f.read()),
                                          'image/png')
            resource.id = resource.hash

        from ..publish import _insert_resource_file
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                # Insert a stub module
                cursor.execute("""\
INSERT INTO abstracts (abstract) VALUES (' ') RETURNING abstractid""")
                abstractid = cursor.fetchone()[0]
                cursor.execute("""\
INSERT INTO modules
  (moduleid, portal_type, version, name,
   authors, maintainers, licensors, stateid, licenseid, doctype,
   submitter, submitlog, language, parent, abstractid)
VALUES
  ('m42119', 'Module', '1.1', 'New Version',
   NULL, NULL, NULL, NULL, 11,'',
   '', '', 'en', NULL, %s)
RETURNING module_ident""", (abstractid,))
                module_ident = cursor.fetchone()[0]

                _insert_resource_file(cursor, module_ident, resource)
                # And call it again, to simulate a second reference to
                #   the same resource.
                _insert_resource_file(cursor, module_ident, resource)


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
        init_db(self.db_conn_str)
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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        cursor.execute("""\
            UPDATE modules SET stateid = 1 WHERE stateid = 5""")
        cursor.connection.commit()

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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        cursor.execute("""\
            UPDATE modules SET stateid = 1 WHERE stateid = 5""")
        cursor.connection.commit()

        # * Ensure book one and two have been republished.
        # We can ensure this through checking for the existence of the
        # collection tree and the updated contents.
        cursor.execute("SELECT tree_to_json(%s, '1.2', FALSE)::json",
                       (book_one.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408@1.2',
            u'shortId': u'w7tL-ztT@1.2',
            u'title': u'Book of Infinity',
            u'slug': None,
            u'contents': [
                {u'id': u'subcol',
                 u'shortId': u'subcol',
                 u'title': u'Part One',
                 u'slug': None,
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@1',
                      u'shortId': u'LyhY6pM8@1',
                      u'slug': None,
                      u'title': u'Document One'},
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'shortId': u'MrEezaHC@2',
                      u'slug': None,
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'shortId': u'subcol',
                 u'title': u'Part Two',
                 u'slug': None,
                 u'contents': [
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@1',
                      u'shortId': u'AUQV3irg@1',
                      u'slug': None,
                      u'title': u'Document Three'},
                     {u'id': u'deadbeef-a927-4652-9a8d-deb2d28fb801@2',
                      u'shortId': u'3q2-76kn@2',
                      u'slug': None,
                      u'title': u'Document Four'}],
                 }],
        }
        self.assertEqual(tree, expected_tree)
        cursor.execute("SELECT tree_to_json(%s, '1.2', FALSE)::json",
                       (book_two.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'dbb28a6b-cad2-4863-986f-6059da93386b@1.2',
            u'shortId': u'27KKa8rS@1.2',
            u'title': u'Book of Infinity',
            u'slug': None,
            u'contents': [
                {u'id': u'subcol',
                 u'shortId': u'subcol',
                 u'title': u'Part One',
                 u'slug': None,
                 u'contents': [
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'shortId': u'MrEezaHC@2',
                      u'slug': None,
                      u'title': u'Document One'},
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@1',
                      u'shortId': u'AUQV3irg@1',
                      u'slug': None,
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'shortId': u'subcol',
                 u'title': u'Part Two',
                 u'slug': None,
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@1',
                      u'shortId': u'LyhY6pM8@1',
                      u'slug': None,
                      u'title': u'Document Three'}],
                 }],
        }
        self.assertEqual(tree, expected_tree)

    @db_connect
    def test_republish_binder_tree_not_latest(self, cursor):
        """Verify republishing of binders that has trees with latest flag set
        to null in shared document situations.  Binders published by
        cnx-publishing always have latest flag set to true at the time of
        writing.  This is for existing binders in the database."""
        # * Set up one book in archive.  One of the pages in this book will be
        # updated causing this book to be republished.
        book_one = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)

        # Post publication worker will change the collection stateid to
        # "current" (1).
        cursor.execute("""\
            UPDATE modules SET stateid = 1 WHERE stateid = 5""")
        cursor.connection.commit()

        # * Set the latest flag in trees for book one to null.
        cursor.execute("""\
UPDATE trees SET latest = NULL WHERE documentid = (
    SELECT module_ident FROM modules
        WHERE ident_hash(uuid, major_version, minor_version) = %s)
""", (book_one.ident_hash,))

        # * Make a new publication of page one
        page_one = book_one[0][0]
        page_one.metadata['version'] = '2'
        from ..publish import publish_model
        publish_model(cursor, page_one, 'tester', 'test pub')

        # * Invoke the republish logic.
        self.call_target(cursor, [page_one])

        # * Ensure book one has been republished.
        cursor.execute("""\
SELECT 1 FROM trees WHERE documentid = (
    SELECT module_ident FROM modules
        WHERE ident_hash(uuid, major_version, minor_version) =
              %s||'@1.2')
""", (book_one.id,))
        self.assertEqual((1,), cursor.fetchone())


class PublishCompositeDocumentTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.publish import publish_composite_model
        return publish_composite_model

    @db_connect
    def test(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)

        # Build some new metadata for the composite document.
        metadata = [x.metadata.copy()
                    for x in cnxepub.flatten_to_documents(binder)][0]
        del metadata['cnx-archive-uri']
        del metadata['version']
        metadata['title'] = "Made up of other things"

        publisher = [p['id'] for p in metadata['publishers']][0]
        message = "Composite addition"

        # Add some fake collation objects to the book.
        content = '<body><p class="para">composite</p></body>'
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)

        ident_hash = self.target(cursor, composite_doc, binder,
                                 publisher, message)

        # Ensure the model's identifiers has been set.
        self.assertEqual(ident_hash, composite_doc.ident_hash)
        self.assertEqual(ident_hash, composite_doc.get_uri('cnx-archive'))

        # The only thing different in the module metadata insertion is
        # the `portal_type` value
        cursor.execute(
            "SELECT portal_type "
            "FROM modules "
            "WHERE ident_hash(uuid, major_version, minor_version) = %s",
            (ident_hash,))
        portal_type = cursor.fetchone()[0]
        self.assertEqual(portal_type, 'CompositeModule')

        # Ensure the file entry and association entry.
        cursor.execute("""\
SELECT f.file
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS m1, -- context
     modules AS m2  -- item
WHERE
  (ident_hash(m1.uuid, m1.major_version, m1.minor_version) = %s
   AND m1.module_ident = cfa.context)
  AND
  (ident_hash(m2.uuid, m2.major_version, m2.minor_version) = %s
   AND m2.module_ident = cfa.item)""",
                       (binder.ident_hash, ident_hash,))
        persisted_content = cursor.fetchone()[0][:]
        self.assertIn(content, persisted_content)


class PublishCollatedDocumentTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.publish import publish_collated_document
        return publish_collated_document

    @db_connect
    def test(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)

        # Modify the content of a document to mock the collation changes.
        doc = [x for x in cnxepub.flatten_to_documents(binder)][0]

        # Add some fake collation objects to the book.
        content = '<body><p class="para">collated</p></body>'
        doc.content = content

        self.target(cursor, doc, binder)

        # Ensure the file entry and association entry.
        cursor.execute("""\
SELECT f.file
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS m1, -- context
     modules AS m2  -- item
WHERE
  (ident_hash(m1.uuid, m1.major_version, m1.minor_version) = %s
   AND m1.module_ident = cfa.context)
  AND
  (ident_hash(m2.uuid, m2.major_version, m2.minor_version) = %s
   AND m2.module_ident = cfa.item)""",
                       (binder.ident_hash, doc.ident_hash,))
        persisted_content = cursor.fetchone()[0][:]
        self.assertIn(content, persisted_content)

    @db_connect
    def test_no_change_to_contents(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)

        # Modify the content of a document to mock the collation changes.
        doc = [x for x in cnxepub.flatten_to_documents(binder)][0]

        self.target(cursor, doc, binder)

        # Ensure the file entry and association entry.
        cursor.execute("""\
SELECT f.file
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS m1, -- context
     modules AS m2  -- item
WHERE
  (ident_hash(m1.uuid, m1.major_version, m1.minor_version) = %s
   AND m1.module_ident = cfa.context)
  AND
  (ident_hash(m2.uuid, m2.major_version, m2.minor_version) = %s
   AND m2.module_ident = cfa.item)""",
                       (binder.ident_hash, doc.ident_hash,))
        persisted_content = cursor.fetchone()[0][:]
        self.assertIn(doc.content, persisted_content)


class PublishCollatedTreeTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.publish import publish_collated_tree
        return publish_collated_tree

    @db_connect
    def test(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)

        # Build some new metadata for the composite document.
        metadata = [x.metadata.copy()
                    for x in cnxepub.flatten_to_documents(binder)][0]
        del metadata['cnx-archive-uri']
        del metadata['version']
        metadata['title'] = "Made up of other things"

        publisher = [p['id'] for p in metadata['publishers']][0]
        message = "Composite addition"

        # Add some fake collation objects to the book.
        content = '<body><p class="para">composite</p></body>'
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)

        from cnxpublishing.publish import publish_composite_model
        publish_composite_model(
            cursor,
            composite_doc,
            binder,
            publisher,
            message,
        )

        # Shim the composite document into the binder.
        binder.append(composite_doc)

        tree = cnxepub.model_to_tree(binder)
        self.target(cursor, tree)

        cursor.execute("SELECT tree_to_json(%s, %s, TRUE)::json;",
                       (binder.id, binder.metadata['version'],))
        collated_tree = cursor.fetchone()[0]
        self.assertIn(composite_doc.ident_hash,
                      cnxepub.flatten_tree_to_ident_hashes(collated_tree))
