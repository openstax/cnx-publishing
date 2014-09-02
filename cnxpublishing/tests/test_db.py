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
import json
import uuid
import unittest
from copy import deepcopy
try:
    from unittest import mock
except ImportError:
    import mock

import psycopg2
import cnxepub
from cnxarchive.utils import split_ident_hash
from pyramid import testing

from . import use_cases
from .testing import db_connect, integration_test_settings


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

    @db_connect
    def persist_model(self, cursor, publication_id, model):
        from ..db import add_pending_model, add_pending_model_content
        ident_hash = add_pending_model(cursor, publication_id, model)
        add_pending_model_content(cursor, publication_id, model)


class PublicationLicenseAcceptanceTestCase(BaseDatabaseIntegrationTestCase):
    """Verify license acceptance functionality"""

    def setUp(self):
        super(PublicationLicenseAcceptanceTestCase, self).setUp()
        self.publication_id = self.make_publication()

    def call_target(self, *args, **kwargs):
        from ..db import upsert_pending_licensors
        return upsert_pending_licensors(*args, **kwargs)

    @db_connect
    def test_licensor_insertion(self, cursor):
        """Are we able to insert all roles found on in the content?"""
        # Set up the content to be referenced.
        metadata = json.dumps(use_cases.BOOK.metadata)
        cursor.execute("""\
WITH control_insert AS (
  INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid)
INSERT INTO pending_documents
  (publication_id, uuid, major_version, minor_version,
   type, metadata)
VALUES (%s, (SELECT uuid FROM control_insert), 1, 1, 'Binder', %s)
RETURNING id, uuid""", (self.publication_id, metadata,))
        pending_id, uuid_ = cursor.fetchone()

        # Call the target.
        self.call_target(cursor, pending_id)

        # Check the results.
        cursor.execute("""\
SELECT user_id, accepted
FROM license_acceptances
WHERE uuid = %s
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = [('charrose', None), ('frahablar', None),
                    ('impicky', None), ('marknewlyn', None),
                    ('ream', None), ('rings', None)]
        self.assertEqual(entries, expected)

    @db_connect
    def test_licensor_additions(self, cursor):
        """Add licensors to the acceptance list"""
        # Make it look like BOOK is already in the database.
        # Add these roles to the license acceptance
        # Set up the content to be referenced.
        metadata = json.dumps(use_cases.BOOK.metadata)
        cursor.execute("""\
WITH control_insert AS (
  INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid)
INSERT INTO pending_documents
  (publication_id, uuid, major_version, minor_version,
   type, metadata)
VALUES (%s, (SELECT uuid from control_insert), 1, 1, 'Binder', %s)
RETURNING id, uuid""", (self.publication_id, metadata,))
        pending_id, uuid_ = cursor.fetchone()

        # Create existing licensor records.
        values = [
            (uuid_, 'charrose', True), ##(uuid_, 'frahablar', None),
            (uuid_, 'impicky', True), (uuid_, 'marknewlyn', True),
            (uuid_, 'ream', True), ##(uuid_, 'rings', None),
            ]
        serial_values = []
        for v in values:
            serial_values.extend(v)
        value_format = ', '.join(['(%s, %s, %s)'] * len(values))
        cursor.execute("""\
INSERT INTO license_acceptances (uuid, user_id, accepted)
VALUES {}""".format(value_format), serial_values)

        # Call the target.
        self.call_target(cursor, pending_id)

        # Check the additions.
        cursor.execute("""\
SELECT user_id
FROM license_acceptances
WHERE uuid = %s AND accepted is UNKNOWN
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = [('frahablar',), ('rings',)]
        self.assertEqual(entries, expected)


class PublicationRoleAcceptanceTestCase(BaseDatabaseIntegrationTestCase):
    """Verify license acceptance functionality"""

    def setUp(self):
        super(PublicationRoleAcceptanceTestCase, self).setUp()
        self.publication_id = self.make_publication()

    def call_target(self, *args, **kwargs):
        from ..db import upsert_pending_roles
        return upsert_pending_roles(*args, **kwargs)

    @db_connect
    def test_role_insertion(self, cursor):
        """Are we able to insert all roles found on in the content?"""
        # Set up the content to be referenced.
        metadata = json.dumps(use_cases.BOOK.metadata)
        cursor.execute("""\
WITH control_insert AS (
  INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid)
INSERT INTO pending_documents
  (publication_id, uuid, major_version, minor_version,
   type, metadata)
VALUES (%s, (SELECT uuid FROM control_insert), 1, 1, 'Binder', %s)
RETURNING id, uuid""", (self.publication_id, metadata,))
        pending_id, uuid_ = cursor.fetchone()

        # Call the target.
        self.call_target(cursor, pending_id)

        # Check the results.
        cursor.execute("""\
SELECT user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s
ORDER BY user_id ASC, role_type ASC""", (uuid_,))
        entries = cursor.fetchall()
        expected = [
            ('charrose', 'Author', None), ('frahablar', 'Illustrator', None),
            ('frahablar', 'Translator', None),
            ('impicky', 'Editor', None), ('marknewlyn', 'Author', None),
            ('ream', 'Copyright Holder', None),
            ('ream', 'Publisher', None), ('rings', 'Publisher', None),
            ]
        self.assertEqual(entries, expected)

    @db_connect
    def test_role_additions(self, cursor):
        """Add roles to the acceptance list"""
        # Make it look like BOOK is already in the database.
        # Add these roles to the role acceptance
        # Set up the content to be referenced.
        metadata = json.dumps(use_cases.BOOK.metadata)
        cursor.execute("""\
WITH control_insert AS (
  INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid)
INSERT INTO pending_documents
  (publication_id, uuid, major_version, minor_version,
   type, metadata)
VALUES (%s, (SELECT uuid FROM control_insert), 1, 1, 'Binder', %s)
RETURNING id, uuid""", (self.publication_id, metadata,))
        pending_id, uuid_ = cursor.fetchone()

        # Create existing role records.
        values = [
            (uuid_, 'charrose', 'Author', True),
            (uuid_, 'frahablar', 'Translator', True),
            ##(uuid_, 'frahablar', 'Illustrator', None),
            (uuid_, 'impicky', 'Editor', True),
            (uuid_, 'marknewlyn', 'Author', True),
            (uuid_, 'ream', 'Copyright Holder', True),
            (uuid_, 'ream', 'Publisher', True),
            ##(uuid_, 'rings', 'Publisher', None),
            ]
        serial_values = []
        for v in values:
            serial_values.extend(v)
        value_format = ', '.join(['(%s, %s, %s, %s)'] * len(values))
        cursor.execute("""\
INSERT INTO role_acceptances (uuid, user_id, role_type, accepted)
VALUES {}""".format(value_format), serial_values)

        # Call the target.
        self.call_target(cursor, pending_id)

        # Check the additions.
        cursor.execute("""\
SELECT user_id, role_type
FROM role_acceptances
WHERE uuid = %s AND accepted is UNKNOWN
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = [('frahablar', 'Illustrator',),
                    ('rings', 'Publisher',)]
        self.assertEqual(entries, expected)


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
        self.assertEqual(is_license_accepted, False)
        self.assertEqual(are_roles_accepted, False)

    def test_add_pending_document_w_existing_license_accepted(self):
        """Add a pending document to the database.
        In this case we have an existing license acceptance for the author
        of the document.
        This tests the trigger that will update the license acceptance
        state on the pending document.
        """
        document_uuid = str(uuid.uuid4())
        uri = 'http://cnx.org/contents/{}@1'.format(document_uuid)
        user_id = 'smoo'
        role_struct = {'id': 'smoo', 'name': 'smOO chIE', 'type': 'cnx-id'}

        document_metadata = {
            'authors': [role_struct],
            'publishers': [role_struct],
            'cnx-archive-uri': uri,
            'license_url': VALID_LICENSE_URL,
            }

        # Create a publication and an acceptance record.
        publication_id = self.make_publication()
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (document_uuid,))
                cursor.execute("""\
INSERT INTO license_acceptances
  ("uuid", "user_id", "accepted")
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
        self.assertEqual(are_roles_accepted, False)

    def test_add_pending_document_w_existing_role_accepted(self):
        """Add a pending document to the database.
        In this case we have an existing license acceptance for the author
        of the document.
        This tests the trigger that will update the license acceptance
        state on the pending document.
        """
        document_uuid = str(uuid.uuid4())
        uri = 'http://cnx.org/contents/{}@1'.format(document_uuid)
        user_id = 'smoo'
        role_struct = {'id': 'smoo', 'name': 'smOO chIE', 'type': 'cnx-id'}

        document_metadata = {
            'authors': [role_struct],
            'publishers': [role_struct],
            'cnx-archive-uri': uri,
            'license_url': VALID_LICENSE_URL,
            }

        # Create a publication and an acceptance record.
        publication_id = self.make_publication()
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (document_uuid,))
                args = (document_uuid, user_id, 'Author',
                        document_uuid, user_id, 'Publisher',)
                cursor.execute("""\
INSERT INTO role_acceptances (uuid, user_id, role_type, accepted)
VALUES (%s, %s, %s, 't'), (%s, %s, %s, 't')""", args)

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
        self.assertEqual(is_license_accepted, False)
        self.assertEqual(are_roles_accepted, True)

    @db_connect
    def test_add_pending_document_wo_permission(self, cursor):
        """Add a pending document from publisher without permission."""
        publication_id = self.make_publication()
        document_id = 'a040717c-8d70-4953-9ed0-10d5095d5448'

        # Set up the controls and acl entries.
        cursor.execute("""\
WITH
control_insert AS (
  INSERT INTO document_controls (uuid)
  VALUES (%s::uuid) RETURNING uuid)
INSERT INTO document_acl (uuid, user_id, permission)
VALUES ((SELECT uuid from control_insert), 'ream', 'publish'::permission_type)
""",
                               (document_id,))

        # Create and add a document for the publication.
        metadata = {'authors': [{'id': 'able', 'type': 'cnx-id'}],
                    'publishers': [{'id': 'able', 'type': 'cnx-id'}],
                    'cnx-archive-uri': 'http://cnx.org/contents/{}' \
                                       .format(document_id),
                    }
        document = self.make_document(metadata=metadata)

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model
        document_ident_hash = add_pending_model(
            cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        cursor.execute("""
SELECT concat_ws('@', uuid, concat_ws('.', major_version, minor_version))
FROM pending_documents
WHERE publication_id = %s""", (publication_id,))
        expected_ident_hash = cursor.fetchone()[0]
        # We're pulling the first value in the state_messages array,
        # there are other exceptions related to validation in there,
        # but we can depend on the value's location because the permission
        # check will always happen before the validations.
        cursor.execute("""\
SELECT state, (state_messages->>0)::json
FROM publications
WHERE id = %s""", (publication_id,))
        state, state_messages = cursor.fetchone()

        self.assertEqual(state, 'Failed/Error')
        expected_message = u"Not allowed to publish '{}'.".format(document_id)
        expected_state_messages = {
            u'code': 8,
            u'publication_id': 1,
            u'epub_filename': None,
            u'pending_document_id': 1,
            u'pending_ident_hash': unicode(expected_ident_hash),
            u'type': u'NotAllowed',
            u'message': expected_message,
            u'uuid': document_id,
            }
        self.assertEqual(state_messages, expected_state_messages)

    def test_add_pending_document_w_invalid_license(self):
        """Add a pending document to the database."""
        invalid_license_url = 'http://creativecommons.org/licenses/by-sa/1.0'

        publication_id = self.make_publication()

        # Create and add a document for the publication.
        metadata = {'authors': [{'id': 'able', 'type': 'cnx-id'}],
                    'publishers': [{'id': 'able', 'type': 'cnx-id'}],
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
                    'publishers': [{'id': 'able', 'type': 'cnx-id'}],
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


class ArchiveIntegrationTestCase(BaseDatabaseIntegrationTestCase):
    """Verify database interactions with a *Connexions Archive*
    Most of the minor details for this interaction are handled in the
    publish module tests. These tests bridge those a slightly,
    when trying to test overall logic that needs to know
    the complete publication context.
    """
    # These tests push to archive defined tables, which
    # DatabaseIntegrationTestCase tests do not do.
    # In other words this works against the ``publish_pending`` function.

    @db_connect
    def test_republish(self, cursor):
        """Ensure republication of binders that share documents."""
        shared_book_setup = use_cases.setup_COMPLEX_BOOK_ONE_in_archive
        shared_binder = shared_book_setup(self, cursor)
        # We will republish book two.
        binder = use_cases.setup_COMPLEX_BOOK_TWO_in_archive(self, cursor)
        cursor.connection.commit()

        # * Assemble the publication request.
        publication_id = self.make_publication(publisher='ream')
        for doc in cnxepub.flatten_to_documents(binder):
            self.persist_model(publication_id, doc)
        self.persist_model(publication_id, binder)

        # * Fire the publication request.
        from ..db import publish_pending
        state = publish_pending(cursor, publication_id)
        self.assertEqual(state, 'Done/Success')

        # * Ensure the binder was only published once due to the publication
        # request and the shared binder was republished as a minor revision.
        cursor.execute("SELECT count(*) FROM modules WHERE uuid = %s",
                       (binder.id,))
        shared_binder_publication_count = cursor.fetchone()[0]
        self.assertEqual(shared_binder_publication_count, 2)
        # Check the shared binder got a minor version bump.
        cursor.execute("""\
SELECT uuid::text, major_version, minor_version
FROM modules
WHERE portal_type = 'Collection'
ORDER BY major_version ASC, minor_version ASC""")
        versions = {}
        for row in cursor.fetchall():
            versions.setdefault(row[0], [])
            versions[row[0]].append(tuple(row[1:]))
        expected_versions = {
            'dbb28a6b-cad2-4863-986f-6059da93386b': [(1, 1,), (2, 1,)],
            'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408': [(1, 1,), (1, 2,)],
            }
        self.assertEqual(versions, expected_versions)

        # Check the shared binder's tree got updated.
        cursor.execute("SELECT tree_to_json(%s, '1.2')::json",
                       (shared_binder.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408@1.2',
            u'title': u'Book of Infinity',
            u'contents': [
                {u'id': u'subcol',
                 u'title': u'Part One',
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@2',
                      u'title': u'Document One'},
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'title': u'Part Two',
                 u'contents': [
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@2',
                      u'title': u'Document Three'},
                     {u'id': u'deadbeef-a927-4652-9a8d-deb2d28fb801@1',
                      u'title': u'Document Four'}],
                 }],
            }
        self.assertEqual(tree, expected_tree)
        cursor.execute("SELECT tree_to_json(%s, '2.1')::json",
                       (binder.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'dbb28a6b-cad2-4863-986f-6059da93386b@2.1',
            u'title': u'Book of Infinity',
            u'contents': [
                {u'id': u'subcol',
                 u'title': u'Part One',
                 u'contents': [
                     {u'id': u'32b11ecd-a1c2-4141-95f4-7c27f8c71dff@2',
                      u'title': u'Document One'},
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@2',
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'title': u'Part Two',
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@2',
                      u'title': u'Document Three'}],
                 }],
            }
        self.assertEqual(tree, expected_tree)
