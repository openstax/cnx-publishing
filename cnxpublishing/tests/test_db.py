# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import uuid
import unittest

import psycopg2
from pyramid import testing

from .testing import integration_test_settings


VALID_LICENSE_URL = "http://creativecommons.org/licenses/by/4.0/"


class DatabaseIntegrationTestCase(unittest.TestCase):
    """Verify database interactions"""

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

        # Declare a request, so that we can use the route generator methods.
        request = testing.DummyRequest()
        self.config = testing.setUp(settings=self.settings, request=request)
        # Register the routes for reverse generation of urls.
        from ..main import declare_routes
        declare_routes(self.config)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

    def make_publication(self, publisher='nobody', message="no msg",
                         epub=None):
        """Make a publication entry in the database."""
        if epub is None:
            epub = b'abc123'
        epub = psycopg2.Binary(epub)
        args = (publisher, message, epub,)
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
INSERT INTO publications ("publisher", "publication_message", "epub")
VALUES (%s, %s, %s) RETURNING "id";""", args)
                publication_id = cursor.fetchone()[0]
        return publication_id

    def make_document(self, id=None, content=None, metadata=None):
        from cnxepub import Document
        if content is None:
            content = io.BytesIO(b'<p>Blank.</p>')
        document = Document(id, content,
                            metadata=metadata)
        return document

    def persist_document(self, publication_id, document):
        from ..db import add_pending_document
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                document_ident_hash = add_pending_document(
                    cursor, publication_id, document)

    def test_add_new_pending_document(self):
        """Add a pending document to the database."""
        publication_id = self.make_publication()

        # Create and add a document for the publication.
        metadata = {
            'authors': [{'id': 'able', 'type': 'cnx-id'}],
            'license_url': VALID_LICENSE_URL,
            }
        document = self.make_document(metadata=metadata)

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                document_ident_hash = add_pending_model(
                    cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT "type", "license_accepted", "roles_accepted"
FROM pending_documents
WHERE
  publication_id = %s
  AND uuid || '@' || concat_ws('.', major_version, minor_version) = %s
""", (publication_id, document_ident_hash,))
                record = cursor.fetchone()
        type_, is_license_accepted, are_roles_accepted = record
        self.assertEqual(type_, 'Document')
        self.assertEqual(is_license_accepted, True)
        self.assertEqual(are_roles_accepted, True)

    def test_add_pending_document_w_exist_license_accept(self):
        """Add a pending document to the database.
        In this case we have an existing license acceptance for the author
        of the document.
        This tests the trigger that will update the license acceptance
        state on the pending document.
        """
        document_uuid = str(uuid.uuid4())
        uri = 'http://cnx.org/contents/{}@1'.format(document_uuid)
        user_id = 'smoo'
        document_metadata = {
            'authors': [
                {'id': 'smoo',
                 'name': 'smOO chIE',
                 'type': 'cnx-id'}],
            'cnx-archive-uri': uri,
            'license_url': VALID_LICENSE_URL,
            }

        # Create a publication and an acceptance record.
        publication_id = self.make_publication()
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
INSERT INTO publications_license_acceptance
  ("uuid", "user_id", "acceptance")
VALUES (%s, %s, 't')""", (document_uuid, user_id,))

        # Create and add a document for the publication.
        document = self.make_document(metadata=document_metadata)
        from ..db import add_pending_model
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                document_ident_hash = add_pending_model(
                    cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT "type", "license_accepted", "roles_accepted"
FROM pending_documents
WHERE
  publication_id = %s
  AND concat_ws('@', uuid, concat_ws('.', major_version, minor_version)) = %s
""", (publication_id, document_ident_hash,))
                record = cursor.fetchone()
        type_, is_license_accepted, are_roles_accepted = record
        self.assertEqual(type_, 'Document')
        self.assertEqual(is_license_accepted, True)
        self.assertEqual(are_roles_accepted, True)

    def test_add_new_pending_document_w_invalid_license(self):
        """Add a pending document to the database."""
        invalid_license_url = 'http://creativecommons.org/licenses/by-sa/1.0'

        publication_id = self.make_publication()

        # Create and add a document for the publication.
        metadata = {'authors': [{'id': 'able', 'type': 'cnx-id'}],
                    'license_url': invalid_license_url,
                    }
        document = self.make_document(metadata=metadata)

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                document_ident_hash = add_pending_model(
                    cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT concat_ws('@', uuid, concat_ws('.', major_version, minor_version))
FROM pending_documents
WHERE publication_id = %s""", (publication_id,))
                expected_ident_hash = cursor.fetchone()[0]
                cursor.execute("""
SELECT "state", "state_messages"
FROM publications
WHERE id = %s""", (publication_id,))
                state, state_messages = cursor.fetchone()
        self.assertEqual(state, 'Failed/Error')
        expected_message = u"License '{}' is not valid for " \
                           "contemporary publications." \
                               .format(invalid_license_url)
        expected_state_messages = [
            {u'code': 10,
             u'publication_id': 1,
             u'epub_filename': None,
             u'pending_document_id': 1,
             u'pending_ident_hash': unicode(expected_ident_hash),
             u'type': u'InvalidLicense',
             u'message': expected_message
             }]
        self.assertEqual(state_messages, expected_state_messages)
