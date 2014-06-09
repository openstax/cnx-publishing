# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import sys
import io
import uuid
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

import psycopg2
from pyramid import testing

from .testing import integration_test_settings


VALID_LICENSE_URL = "http://creativecommons.org/licenses/by/4.0/"
# This version checking is required because python's ``traceback`` module
# does not write unicode to ``sys.stderr``, which ``io.StringIO`` requires.
if sys.version_info > (3,):
    STDERR_MOCK_CLASS = io.StringIO
else:
    from StringIO import StringIO
    STDERR_MOCK_CLASS = StringIO


class BaseDatabaseIntegrationTestCase(unittest.TestCase):
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


class DatabaseIntegrationTestCase(BaseDatabaseIntegrationTestCase):
    """Verify database interactions"""

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

    def test_add_pending_document_w_invalid_license(self):
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
        expected_message = u"Invalid license: {}".format(invalid_license_url)
        expected_state_messages = [
            {u'code': 10,
             u'publication_id': 1,
             u'epub_filename': None,
             u'pending_document_id': 1,
             u'pending_ident_hash': unicode(expected_ident_hash),
             u'type': u'InvalidLicense',
             u'message': expected_message,
             u'value': invalid_license_url,
             }]
        self.assertEqual(state_messages, expected_state_messages)

    def test_add_pending_document_w_invalid_role(self):
        """Add a pending document to the database with an invalid role."""
        publication_id = self.make_publication()

        # Create and add a document for the publication.
        author_value = {u'id': u'able', u'type': u'diaspora-id'}
        metadata = {'authors': [author_value],
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
        expected_message = u"Invalid role for 'authors': {}" \
                           .format(repr(author_value))

        expected_state_messages = [
            {u'code': 11,
             u'publication_id': 1,
             u'epub_filename': None,
             u'pending_document_id': 1,
             u'pending_ident_hash': unicode(expected_ident_hash),
             u'type': u'InvalidRole',
             u'message': expected_message,
             u'key': u'authors',
             u'value': author_value,
             }]
        self.assertEqual(state_messages, expected_state_messages)

    @mock.patch('sys.stderr', new_callable=STDERR_MOCK_CLASS)
    def test_add_pending_document_w_critical_error(self, stderr):
        """Add a pending document to the database with an invalid role."""
        publication_id = self.make_publication()

        # No metadata, so some exception related to that will be raised.
        document = self.make_document()

        def raise_exception(*args, **kwargs):
            raise Exception("*** test exception ***")

        patch_args = {
            'target': 'cnxpublishing.db.set_publication_failure',
            'new': raise_exception,
            }

        from ..exceptions import PublicationException
        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                with mock.patch(**patch_args):
                    # This insures that we raise the original exception.
                    with self.assertRaises(PublicationException):
                        document_ident_hash = add_pending_model(
                            cursor, publication_id, document)
        # Check ``sys.stderr`` for the inner exception that caused
        # the critical failure.
        stderr.seek(0)
        self.assertTrue(stderr.read().find("*** test exception ***") >= 0)

    def test_add_pending_model_content(self):
        publication_id = self.make_publication()

        # Create and add a document for the publication.
        metadata = {
            'authors': [{'id': 'able', 'type': 'cnx-id'}],
            'license_url': VALID_LICENSE_URL,
            }
        import md5
        from cnxepub import Resource
        content = """\
<p>Document with some resources</p>
<p><a href="http://cnx.org/">external link</a></p>
<p><a href="../resources/a.txt">internal link</a></p>
"""
        resource = Resource('a.txt', io.BytesIO('asdf\n'), 'text/plain')
        resource_md5 = md5.md5('asdf\n').hexdigest()
        document = self.make_document(id=str(uuid.uuid4()), content=content,
                metadata=metadata)
        document.resources = [resource]
        document.references[-1].bind(resource, '../resources/{}')

        # Here we are testing the function of add_pending_model_content
        from ..db import add_pending_model, add_pending_model_content
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                add_pending_model(cursor, publication_id, document)
                add_pending_model_content(cursor, publication_id, document)

        # Confirm the addition of pending document and resources
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT content
FROM pending_documents
WHERE publication_id = %s AND uuid = %s
""", (publication_id, document.id))
                content = cursor.fetchone()[0]
                self.assertEqual(content[:], document.content)
                self.assertTrue('href="/resources/{}"'.format(resource_md5)
                        in content[:])

                cursor.execute("""\
SELECT data, media_type
FROM pending_resources
WHERE hash = %s
""", (resource_md5,))
                data, media_type = cursor.fetchone()
                self.assertEqual(data[:], 'asdf\n')
                self.assertEqual(media_type, 'text/plain')


class ValidationsTestCase(BaseDatabaseIntegrationTestCase):
    """Verify model validations"""
    # Nameing convension for these tests is:
    #   test_{exception-code}_{point-of-interest}

    def test_9_license_url(self):
        """Check for raised exception when license is missing."""
        # Create a Document model.
        model = self.make_document()

        # Call the in-question validator.
        from ..exceptions import MissingRequiredMetadata
        from ..db import _validate_license as validator
        with self.assertRaises(MissingRequiredMetadata) as caught_exc:
            validator(model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['key'], 'license_url')

    def test_9_authors(self):
        """Check for raised exception when authors are missing."""
        # Create a Document model.
        model = self.make_document()

        # Call the in-question validator.
        from ..exceptions import MissingRequiredMetadata
        from ..db import _validate_roles as validator
        with self.assertRaises(MissingRequiredMetadata) as caught_exc:
            validator(model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['key'], 'authors')

    def test_9_publishers(self):
        """Check for raised exception when publishers are missing."""
        # Create a Document model.
        metadata = {'authors': [{u'type': u'cnx-id', u'id': u'able'}]}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import MissingRequiredMetadata
        from ..db import _validate_roles as validator
        with self.assertRaises(MissingRequiredMetadata) as caught_exc:
            validator(model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['key'], 'publishers')

    def test_10_license_not_found(self):
        """Check for raised exception when the given license doesn't match
        any of the known licenses.
        """
        # Create a Document model.
        invalid_license_url = u"http://example.org/public-domain"
        metadata = {u'license_url': invalid_license_url}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import InvalidLicense
        from ..db import _validate_license as validator
        with self.assertRaises(InvalidLicense) as caught_exc:
            validator(model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['value'], invalid_license_url)

    def test_10_not_valid_for_publication(self):
        """Check for raised exception when the given license is not fit
        for new publications.
        """
        # Create a Document model.
        invalid_license_url = u"http://creativecommons.org/licenses/by/1.0"
        metadata = {u'license_url': invalid_license_url}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import InvalidLicense
        from ..db import _validate_license as validator
        with self.assertRaises(InvalidLicense) as caught_exc:
            validator(model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['value'], invalid_license_url)
