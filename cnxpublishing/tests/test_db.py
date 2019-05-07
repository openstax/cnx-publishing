# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
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
from pyramid import testing

from ..utils import join_ident_hash, split_ident_hash
from . import use_cases
from .testing import db_connect, integration_test_settings, init_db


VALID_LICENSE_URL = "http://creativecommons.org/licenses/by/4.0/"
# This version checking is required because python's ``traceback`` module
# does not write unicode to ``sys.stderr``, which ``io.StringIO`` requires.
if sys.version_info > (3,):
    STDERR_MOCK_CLASS = io.StringIO
else:
    from StringIO import StringIO
    STDERR_MOCK_CLASS = StringIO


class DatabaseUtilsTestCase(unittest.TestCase):
    """Verify the database utility functions are working as expected"""

    def test_db_connect(self):
        from ..db import db_connect

        settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        db_conn_str = settings[CONNECTION_STRING]

        with db_connect(db_conn_str) as conn:
            with conn.cursor() as cur:
                cur.execute("select true")
                result = cur.fetchone()[0]
        self.assertTrue(result)


class BaseDatabaseIntegrationTestCase(unittest.TestCase):
    """Verify database interactions"""

    settings = None
    db_conn_str = None
    is_first_run = True

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        if cls.is_first_run:
            BaseDatabaseIntegrationTestCase.is_first_run = False
            cls._tear_down_database()

    def setUp(self):
        init_db(self.db_conn_str)

        # Declare a request, so that we can use the route generator methods.
        request = testing.DummyRequest()
        self.config = testing.setUp(settings=self.settings, request=request)
        # Register the routes for reverse generation of urls.
        self.config.include('cnxpublishing.views')

        # Initialize the authentication policy.
        from openstax_accounts.stub import main
        main(self.config)

        self.config.include('..tasks')

    def tearDown(self):
        self._tear_down_database()
        testing.tearDown()

    @classmethod
    def _tear_down_database(cls):
        with psycopg2.connect(cls.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")

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
            content = io.BytesIO(b'<body><p>Blank.</p></body>')
        document = Document(id, content,
                            metadata=metadata)
        return document

    @db_connect
    def persist_model(self, cursor, publication_id, model):
        from ..db import add_pending_model, add_pending_model_content
        add_pending_model(cursor, publication_id, model)
        add_pending_model_content(cursor, publication_id, model)


class DatabaseUtilitiesTestCase(BaseDatabaseIntegrationTestCase):
    """Verify various utilties that interact with the database."""

    @db_connect
    def test_is_revision_publication(self, cursor):
        archive_ids = (
            '1a33f51c-cc7b-4b62-bc93-b297e14e9733',
            'd648765a-9a05-4414-a772-71466ec3a1bf',
        )
        pending_ids = (
            '5e254713-2050-4fa7-9b4c-5e5e8a71768a',  # new id
            '1a33f51c-cc7b-4b62-bc93-b297e14e9733',
            'd648765a-9a05-4414-a772-71466ec3a1bf',
        )
        publication_id = self.make_publication()

        # Setup stub entries for these values.
        for id in archive_ids:
            cursor.execute("""\
INSERT INTO modules (uuid, name, licenseid, doctype)
VALUES (%s, 'title', 11, '')""", (id,))
        for id in pending_ids:
            cursor.execute("INSERT INTO document_controls (uuid) VALUES (%s)",
                           (id,))
            cursor.execute("""\
INSERT INTO pending_documents (uuid, publication_id, type)
VALUES (%s, %s, 'Document')""", (id, publication_id,))

        from ..db import is_revision_publication
        self.assertTrue(is_revision_publication(publication_id, cursor))

    @db_connect
    def test_is_not_revision_publication(self, cursor):
        pending_ids = (
            '5e254713-2050-4fa7-9b4c-5e5e8a71768a',  # new id
            '1a33f51c-cc7b-4b62-bc93-b297e14e9733',
            'd648765a-9a05-4414-a772-71466ec3a1bf',
        )
        publication_id = self.make_publication()

        # Setup stub entries for these values.
        for id in pending_ids:
            cursor.execute("INSERT INTO document_controls (uuid) VALUES (%s)",
                           (id,))
            cursor.execute("""\
INSERT INTO pending_documents (uuid, publication_id, type)
VALUES (%s, %s, 'Document')""", (id, publication_id,))

        from ..db import is_revision_publication
        self.assertFalse(is_revision_publication(publication_id, cursor))


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
            (uuid_, 'charrose', True),  # (uuid_, 'frahablar', None),
            (uuid_, 'impicky', True), (uuid_, 'marknewlyn', True),
            (uuid_, 'ream', True),  # (uuid_, 'rings', None),
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


class LicenseRequestTestCase(BaseDatabaseIntegrationTestCase):
    """Verify license request functionality"""

    def setUp(self):
        super(LicenseRequestTestCase, self).setUp()
        self.publication_id = self.make_publication()

    def call_target(self, *args, **kwargs):
        from ..db import upsert_license_requests
        return upsert_license_requests(*args, **kwargs)

    @db_connect
    def test_add(self, cursor):
        """Add to the license to the acceptance list"""
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]

        # Create existing records.
        values = [
            (uuid_, 'charrose', None),
            (uuid_, 'frahablar', None),
            (uuid_, 'impicky', True),
            (uuid_, 'marknewlyn', True),
            (uuid_, 'ream', True),
            (uuid_, 'rings', True),
        ]
        first_set_size = 2

        # Call the target on the first group.
        roles = [{'uid': x[1], 'has_accepted': None}
                 for x in values[:first_set_size]]
        self.call_target(cursor, uuid_, roles)

        # Check the additions.
        cursor.execute("""\
SELECT uuid, user_id, accepted
FROM license_acceptances
WHERE uuid = %s AND accepted is UNKNOWN
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = values[:first_set_size]
        self.assertEqual(entries, expected)

        # Call the target on the second group.
        roles = [{'uid': x[1], 'has_accepted': True}
                 for x in values[first_set_size:]]
        self.call_target(cursor, uuid_, roles)

        # Check the additions.
        cursor.execute("""\
SELECT uuid, user_id, accepted
FROM license_acceptances
WHERE uuid = %s AND accepted is TRUE
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = values[first_set_size:]
        self.assertEqual(entries, expected)

    @db_connect
    def test_update(self, cursor):
        """Update the license to the acceptance list"""
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]

        # Create existing records.
        values = [
            (uuid_, 'charrose', None),
            (uuid_, 'frahablar', None),
            (uuid_, 'impicky', True),
            (uuid_, 'marknewlyn', True),
            (uuid_, 'ream', True),
            (uuid_, 'rings', True),
        ]
        serial_values = []
        for v in values:
            serial_values.extend(v)
        value_format = ', '.join(['(%s, %s, %s)'] * len(values))
        cursor.execute("""\
INSERT INTO license_acceptances (uuid, user_id, accepted)
VALUES {}""".format(value_format), serial_values)

        # Call the target on a selection of uids.
        roles = [{'uid': x[1], 'has_accepted': False}
                 for x in values[:2] + values[-1:]]
        self.call_target(cursor, uuid_, roles)

        # Check the update.
        cursor.execute("""\
SELECT uuid, user_id, accepted
FROM license_acceptances
WHERE uuid = %s AND accepted is FALSE
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = [
            tuple(list(values[0][:2]) + [False]),
            tuple(list(values[1][:2]) + [False]),
            tuple(list(values[-1][:2]) + [False]),
        ]
        self.assertEqual(entries, expected)


class PublicationRoleAcceptanceTestCase(BaseDatabaseIntegrationTestCase):
    """Verify role acceptance functionality"""

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
            # (uuid_, 'frahablar', 'Illustrator', None),
            (uuid_, 'impicky', 'Editor', True),
            (uuid_, 'marknewlyn', 'Author', True),
            (uuid_, 'ream', 'Copyright Holder', True),
            (uuid_, 'ream', 'Publisher', True),
            # (uuid_, 'rings', 'Publisher', None),
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


class RoleRequestTestCase(BaseDatabaseIntegrationTestCase):
    """Verify role acceptance request functionality"""

    def setUp(self):
        super(RoleRequestTestCase, self).setUp()
        self.publication_id = self.make_publication()

    def call_target(self, *args, **kwargs):
        from ..db import upsert_role_requests
        return upsert_role_requests(*args, **kwargs)

    @db_connect
    def test_add(self, cursor):
        """Add roles to the acceptance list"""
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]

        # Create existing role records.
        values = [
            (uuid_, 'charrose', 'Author', None),
            (uuid_, 'frahablar', 'Illustrator', None),
            (uuid_, 'frahablar', 'Translator', None),
            (uuid_, 'impicky', 'Editor', True),
            (uuid_, 'marknewlyn', 'Author', True),
            (uuid_, 'ream', 'Copyright Holder', True),
            (uuid_, 'ream', 'Publisher', True),
            (uuid_, 'rings', 'Publisher', True),
        ]
        first_set_size = 3

        # Call the target on the first group.
        roles = [{'uid': x[1], 'role': x[2]} for x in values[:first_set_size]]
        self.call_target(cursor, uuid_, roles)

        # Check the additions.
        cursor.execute("""\
SELECT uuid, user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s AND accepted is UNKNOWN
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = values[:first_set_size]
        self.assertEqual(entries, expected)

        # Call the target on the second group.
        roles = [{'uid': x[1], 'role': x[2], 'has_accepted': True}
                 for x in values[first_set_size:]]
        self.call_target(cursor, uuid_, roles)

        # Check the additions.
        cursor.execute("""\
SELECT uuid, user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s AND accepted is TRUE
ORDER BY user_id, role_type ASC""", (uuid_,))
        entries = cursor.fetchall()
        expected = values[first_set_size:]
        self.assertEqual(entries, expected)

    @db_connect
    def test_update(self, cursor):
        """Update roles to the acceptance list"""
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]

        # Create existing role records.
        values = [
            (uuid_, 'charrose', 'Author', None),
            (uuid_, 'frahablar', 'Translator', None),
            (uuid_, 'frahablar', 'Illustrator', None),
            (uuid_, 'impicky', 'Editor', True),
            (uuid_, 'marknewlyn', 'Author', True),
            (uuid_, 'ream', 'Copyright Holder', True),
            (uuid_, 'ream', 'Publisher', True),
            (uuid_, 'rings', 'Publisher', None),
        ]
        serial_values = []
        for v in values:
            serial_values.extend(v)
        value_format = ', '.join(['(%s, %s, %s, %s)'] * len(values))
        cursor.execute("""\
INSERT INTO role_acceptances (uuid, user_id, role_type, accepted)
VALUES {}""".format(value_format), serial_values)

        # Call the target on the first group.
        roles = [{'uid': x[1], 'role': x[2], 'has_accepted': False}
                 for x in values[:2] + values[6:7]]
        self.call_target(cursor, uuid_, roles)

        # Check the updates.
        cursor.execute("""\
SELECT uuid, user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s AND accepted is FALSE
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        expected = [
            tuple(list(values[0][:3]) + [False]),
            tuple(list(values[1][:3]) + [False]),
            tuple(list(values[6][:3]) + [False]),
        ]
        self.assertEqual(entries, expected)

    @db_connect
    def test_mixed_update(self, cursor):
        """Update roles with a mixed set of acceptance values"""
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]

        # Create existing role records.
        values = [
            (uuid_, 'charrose', 'Author', None),
            (uuid_, 'frahablar', 'Translator', None),
            # (uuid_, 'frahablar', 'Illustrator', None),
            (uuid_, 'impicky', 'Editor', True),
            (uuid_, 'marknewlyn', 'Author', True),
            (uuid_, 'ream', 'Copyright Holder', True),
            (uuid_, 'ream', 'Publisher', True),
            (uuid_, 'rings', 'Publisher', True),
        ]
        serial_values = []
        for v in values:
            serial_values.extend(v)
        value_format = ', '.join(['(%s, %s, %s, %s)'] * len(values))
        cursor.execute("""\
INSERT INTO role_acceptances (uuid, user_id, role_type, accepted)
VALUES {}""".format(value_format), serial_values)

        # Call the target on the first group.
        roles = [
            # new role...
            {'uid': 'frahablar', 'role': 'Illustrator', 'has_accepted': False},
            # update, testing the optional has_accepted...
            {'uid': 'rings', 'role': 'Publisher'},
            # update, testing usage of has_accepted...
            {'uid': 'frahablar', 'role': 'Translator', 'has_accepted': True},
        ]
        self.call_target(cursor, uuid_, roles)

        # Update values to the expected state.
        values.insert(2, (uuid_, 'frahablar', 'Illustrator', False,))
        values[-1] = tuple(list(values[-1][:3]) + [None])
        values[1] = tuple(list(values[1][:3]) + [True])

        # Check the updates.
        cursor.execute("""\
SELECT uuid, user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s
ORDER BY user_id""", (uuid_,))
        entries = cursor.fetchall()
        self.assertEqual(entries, values)


class UserUpsertTestCase(BaseDatabaseIntegrationTestCase):
    """Verify user upsert functionality"""

    def call_target(self, *args, **kwargs):
        from ..db import upsert_users
        return upsert_users(*args, **kwargs)

    @db_connect
    def test_persons_table_email(self, cursor):
        """check to see that persons table
           contains an empty string for emails"""

        # Create existing role records.
        uids = ['charrose', 'frahablar', 'impicky', 'marknewlyn',
                'ream', 'rings', 'smoo']
        first_set_size = 3

        # Call the target on the first group.
        self.call_target(cursor, uids[:first_set_size])

        # Check the additions.
        cursor.execute("SELECT username FROM users ORDER BY username")
        entries = [x[0] for x in cursor.fetchall()]
        expected = uids[:first_set_size]
        self.assertEqual(entries, expected)

        # Check the additions in legacy.
        cursor.execute("SELECT personid FROM persons ORDER BY personid")
        entries = [x[0] for x in cursor.fetchall()]
        expected = uids[:first_set_size]
        self.assertEqual(entries, expected)

        # Check the email in legacy.
        cursor.execute("SELECT email FROM persons")
        entries = [x[0] for x in cursor.fetchall()]
        expected = [''] * first_set_size
        self.assertEqual(entries, expected)

    @db_connect
    def test_success(self, cursor):
        """upsert user info"""

        # Create existing role records.
        uids = ['charrose', 'frahablar', 'impicky', 'marknewlyn',
                'ream', 'rings', 'smoo']
        first_set_size = 3

        # Call the target on the first group.
        self.call_target(cursor, uids[:first_set_size])

        # Check the additions.
        cursor.execute("SELECT username FROM users ORDER BY username")
        entries = [x[0] for x in cursor.fetchall()]
        expected = uids[:first_set_size]
        self.assertEqual(entries, expected)

        # Check the additions in legacy.
        cursor.execute("SELECT personid FROM persons ORDER BY personid")
        entries = [x[0] for x in cursor.fetchall()]
        expected = uids[:first_set_size]
        self.assertEqual(entries, expected)

        # Call the target on the second group.
        self.call_target(cursor, uids[:-1])

        # Check the additions.
        cursor.execute("SELECT username FROM users ORDER BY username")
        entries = [x[0] for x in cursor.fetchall()]
        self.assertEqual(entries, uids[:-1])

        # Check the additions in legacy.
        cursor.execute("SELECT personid FROM persons ORDER BY personid")
        entries = [x[0] for x in cursor.fetchall()]
        self.assertEqual(entries, uids[:-1])

        # Check for similar usernames.
        # ... smoo & smoopy
        self.call_target(cursor, uids[-1:])

        # Check the additions.
        cursor.execute("SELECT username FROM users ORDER BY username")
        entries = [x[0] for x in cursor.fetchall()]
        self.assertIn(uids[-1], entries)

        # Check the additions in legacy.
        cursor.execute("SELECT personid FROM persons ORDER BY personid")
        entries = [x[0] for x in cursor.fetchall()]
        self.assertIn(uids[-1], entries)

    @db_connect
    def test_fetch_error(self, cursor):
        """Verify user fetch error"""
        from ..db import UserFetchError
        with self.assertRaises(UserFetchError):
            self.call_target(cursor, ['mia'])


class DatabaseIntegrationTestCase(BaseDatabaseIntegrationTestCase):
    """Verify database interactions"""

    def test_add_duplicate_pending_resources(self):
        """Add duplicate pending resources to the database"""
        resource = cnxepub.Resource('a.txt', io.BytesIO('hello world\n'),
                                    'text/plain')

        from ..db import add_pending_resource
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                add_pending_resource(cursor, resource)
                add_pending_resource(cursor, resource)
                cursor.execute("""\
SELECT COUNT(*) FROM pending_resources WHERE hash = %s""", [
                    resource.hash])
                self.assertEqual(cursor.fetchone()[0], 1)

        self.assertEqual(resource.hash,
                         '22596363b3de40b06f981fb85d82312e8c0ed511')
        self.assertEqual(resource.id,
                         '22596363b3de40b06f981fb85d82312e8c0ed511')

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
  AND ident_hash(uuid, major_version, minor_version) = %s
""", (publication_id, document_ident_hash,))
                record = cursor.fetchone()
        type_, is_license_accepted, are_roles_accepted = record
        self.assertEqual(type_, 'Document')
        self.assertEqual(is_license_accepted, False)
        self.assertEqual(are_roles_accepted, False)

    def test_add_pending_document_w_existing_license_accepted(self):
        """Add a pending document to the database.
        In this case we have an existing license acceptance for the author(s)
        of the document.
        This tests the logic that will update the license acceptance
        state on the pending document.
        """
        document_uuid = str(uuid.uuid4())
        uri = 'http://cnx.org/contents/{}@1'.format(document_uuid)
        user_id = 'smoo'
        role_struct = {'id': 'smoo', 'name': 'smOO chIE', 'type': 'cnx-id'}

        document_metadata = {
            'title': "Test Document",
            'summary': "Test Document Abstract",
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
INSERT INTO document_controls (uuid, licenseid)
SELECT %s, licenseid FROM licenses WHERE url = %s""",
                               (document_uuid, VALID_LICENSE_URL,))
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
  AND ident_hash(uuid, major_version, minor_version) = %s
""", (publication_id, document_ident_hash,))
                record = cursor.fetchone()
        type_, is_license_accepted, are_roles_accepted = record
        self.assertEqual(type_, 'Document')
        self.assertEqual(is_license_accepted, True)
        self.assertEqual(are_roles_accepted, False)

    def test_add_pending_document_w_existing_role_accepted(self):
        """Add a pending document to the database.
        In this case we have an existing role acceptance for the author(s)
        of the document.
        This tests the logic that will update the role acceptance
        state on the pending document.
        """
        document_uuid = str(uuid.uuid4())
        uri = 'http://cnx.org/contents/{}@1'.format(document_uuid)
        user_id = 'smoo'
        role_struct = {'id': 'smoo', 'name': 'smOO chIE', 'type': 'cnx-id'}

        document_metadata = {
            'title': "Test Document",
            'summary': "Test Document Abstract",
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
INSERT INTO document_controls (uuid, licenseid)
SELECT %s, licenseid FROM licenses WHERE url = %s""",
                               (document_uuid, VALID_LICENSE_URL,))
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
  AND ident_hash(uuid, major_version, minor_version) = %s
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
                    'cnx-archive-uri': 'http://cnx.org/contents/{}'
                                       .format(document_id),
                    }
        document = self.make_document(metadata=metadata)

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model
        add_pending_model(cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        cursor.execute("""
SELECT ident_hash(uuid, major_version, minor_version)
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
        """Add a pending document to the database.
        This tests the the metadata validations.
        """
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
                add_pending_model(cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT ident_hash(uuid, major_version, minor_version)
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
                add_pending_model(cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT ident_hash(uuid, major_version, minor_version)
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

    @db_connect
    def test_add_pending_document_w_invalid_references(self, cursor):
        """Add a pending document with an invalid content references."""
        publication_id = self.make_publication()

        # Insert a valid module for referencing...
        cursor.execute("""\
INSERT INTO abstracts (abstract) VALUES ('abstract')
RETURNING abstractid""")
        cursor.execute("""\
INSERT INTO modules
(module_ident, portal_type, name,
 created, revised, abstractid, licenseid,
 doctype, submitter, submitlog, stateid, parent, parentauthors,
 language, authors, maintainers, licensors,
 google_analytics, buylink)
VALUES
(1, 'Module', 'referenced module',
 DEFAULT, DEFAULT, 1, 1,
 0, 'admin', 'log', DEFAULT, NULL, NULL,
 'en', '{admin}', NULL, '{admin}',
 DEFAULT, DEFAULT) RETURNING uuid || '@' || major_version""")
        doc_ident_hash = cursor.fetchone()[0]

        # Create and add a document for the publication.
        metadata = {
            'title': 'Document Title',
            'summary': 'Document Summary',
            'authors': [{u'id': u'able', u'type': u'cnx-id'}],
            'publishers': [{'id': 'able', 'type': 'cnx-id'}],
            'license_url': VALID_LICENSE_URL,
        }
        content = """
            <body>
            <!-- Invalid references -->
            <img src="../resources/8bef27ba.png"/>
            <a href="/contents/765792e0-5e65-4411-88d3-90df8f48eb3a@55">
              relative reference to internal content that does not exist
            </a>
            <!-- Valid reference -->
            <a href="http://openstaxcnx.org/contents/8bef27ba@55">
              external reference to internal content
            </a>
            <a href="http://cnx.org/contents/8bef27ba@55">
              external reference to internal content
            </a>
             <a href="http://demo.cnx.org/images/logo.png">
              external reference to internal content
            </a>
            <a href="/contents/{}">
              relative reference to internal content
            </a>
            <a href="#hello">anchor link</a>
            <a href="http://example.org/">external link</a>
            </body>""" \
                .format(doc_ident_hash)
        document = self.make_document(content=content, metadata=metadata)

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model, add_pending_model_content
        add_pending_model(cursor, publication_id, document)
        add_pending_model_content(cursor, publication_id, document)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        cursor.execute("""
SELECT ident_hash(uuid, major_version, minor_version)
FROM pending_documents
WHERE publication_id = %s""", (publication_id,))
        expected_ident_hash = cursor.fetchone()[0]
        cursor.execute("""
SELECT "state", "state_messages"
FROM publications
WHERE id = %s""", (publication_id,))
        state, state_messages = cursor.fetchone()

        self.assertEqual(state, 'Failed/Error')
        xpath = u'/body/img'
        ref_value = u'../resources/8bef27ba.png'
        expected_message = u"Invalid reference at '{}'." \
                           .format(xpath)

        expected_state_message = {
            u'code': 20,
            u'publication_id': 1,
            u'epub_filename': None,
            u'pending_document_id': 1,
            u'pending_ident_hash': unicode(expected_ident_hash),
            u'type': u'InvalidReference',
            u'message': expected_message,
            u'xpath': xpath,
            u'value': ref_value,
        }
        self.assertEqual(len(state_messages), 2)
        self.assertEqual(state_messages[-1], expected_state_message)

    @db_connect
    def test_add_pending_binder_w_document_pointers(self, cursor):
        """Add a pending binder with document pointers."""
        publication_id = self.make_publication()
        book_three = use_cases.setup_COMPLEX_BOOK_THREE_in_archive(self, cursor)
        cursor.connection.commit()
        # This Book contains the pages used in book three.
        metadata = book_three.metadata.copy()
        del metadata['cnx-archive-uri']
        binder = cnxepub.Binder(
            id='bacc12fe@draft', metadata=metadata,
            nodes=[
                # Valid, because it points at the 'latest' version of the document.
                cnxepub.DocumentPointer(split_ident_hash(book_three[0].ident_hash)[0]),
                # Invalid, because of the version specified.
                cnxepub.DocumentPointer(
                    join_ident_hash(split_ident_hash(book_three[1].ident_hash)[0], '99')),
                # Invalid, because it points at a binder.
                cnxepub.DocumentPointer(
                    book_three.ident_hash),
            ],
        )

        # Here we are testing the function of add_pending_document.
        from ..db import add_pending_model, add_pending_model_content
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                add_pending_model(cursor, publication_id, binder)
                add_pending_model_content(cursor, publication_id, binder)

        # Confirm the addition by checking for an entry
        # This doesn't seem like much, but we only need to check that
        # the entry was added.
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT ident_hash(uuid, major_version, minor_version)
FROM pending_documents
WHERE publication_id = %s""", (publication_id,))
                expected_ident_hash = cursor.fetchone()[0]
                cursor.execute("""
SELECT "state", "state_messages"
FROM publications
WHERE id = %s""", (publication_id,))
                state, state_messages = cursor.fetchone()
        self.assertEqual(state, 'Failed/Error')

        expected_message = u"Invalid document pointer: {}" \
                           .format(book_three.ident_hash)
        expected_state_message = {
            u'code': 21,
            u'publication_id': 1,
            u'epub_filename': None,
            u'pending_document_id': 1,
            u'pending_ident_hash': unicode(expected_ident_hash),
            u'type': u'InvalidDocumentPointer',
            u'message': expected_message,
            u'ident_hash': unicode(book_three.ident_hash),
            u'exists': True,
            u'is_document': False,
        }
        self.assertEqual(len(state_messages), 2)
        self.assertEqual(state_messages[0], expected_state_message)

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
                        add_pending_model(cursor, publication_id, document)
        # Check ``sys.stderr`` for the inner exception that caused
        # the critical failure.
        stderr.seek(0)
        self.assertTrue(stderr.read().find("*** test exception ***") >= 0)

    def test_add_pending_binder_w_resources(self):
        """Add a pending binder with resources to the database"""
        publication_id = self.make_publication()
        book_three = deepcopy(use_cases.COMPLEX_BOOK_THREE)
        book_three.resources = [
            cnxepub.Resource(
                use_cases.RESOURCE_ONE_FILENAME,
                use_cases._read_file(use_cases.RESOURCE_ONE_FILEPATH, 'rb'),
                'image/png',
                filename='cover.png'),
            cnxepub.Resource(
                '6803daf6246832aa86504f1785fe34deb07c0eb6',
                io.BytesIO('div { move-to: trash }\n'),
                'text/css',
                filename='ruleset.css')]

        from ..db import add_pending_model, add_pending_model_content
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                binder_ident_hash = add_pending_model(
                    cursor, publication_id, book_three)
                add_pending_model_content(cursor, publication_id, book_three)

        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                # Check cover is in pending resources
                cursor.execute("""
SELECT filename FROM pending_resources
WHERE hash = '8d539366a39af1715bdf4154d0907d4a5360ba29'""")
                self.assertEqual(('cover.png',), cursor.fetchone())
                # Check ruleset is in pending resources
                cursor.execute("""
SELECT filename FROM pending_resources
WHERE hash = '6803daf6246832aa86504f1785fe34deb07c0eb6'""")
                self.assertEqual(('ruleset.css',), cursor.fetchone())

                # Check that the resources are linked to the binder
                cursor.execute("""
SELECT filename FROM pending_resources r
JOIN pending_resource_associations a ON a.resource_id = r.id
JOIN pending_documents d ON a.document_id = d.id
WHERE ident_hash(uuid, major_version, minor_version) = %s
ORDER BY filename""",
                               (binder_ident_hash,))
                self.assertEqual([('cover.png',), ('ruleset.css',)],
                                 cursor.fetchall())


class ValidationsTestCase(BaseDatabaseIntegrationTestCase):
    """Verify model validations"""
    # Nameing convension for these tests is:
    #   test_{exception-code}_{point-of-interest}

    _base_metadata = {
    }

    def setUp(self):
        super(ValidationsTestCase, self).setUp()
        self.metadata = self._base_metadata.copy()
        self.addCleanup(delattr, self, 'metadata')

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

    @db_connect
    def test_12_invalid_subjects(self, cursor):
        """Check for raised exception when the given subject is not fit
        for new publications.
        """
        # Create a Document model.
        invalid_subjects = [
            u'Science and Statistics',
            u'Math and Stuph',
        ]
        valid_subjects = [
            u'Humanities',
        ]
        subjects = invalid_subjects + valid_subjects
        metadata = {u'subjects': subjects}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import InvalidMetadata
        from ..db import _validate_subjects as validator
        with self.assertRaises(InvalidMetadata) as caught_exc:
            validator(cursor, model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['value'], invalid_subjects)

    @db_connect
    def test_12_invalid_derived_from_uri(self, cursor):
        """Check for raised exception when the given derived-from is not fit
        for new publications.
        """
        # Create a Document model.
        invalid_derived_from_uri = u"http://example.org/c/3a9b2cef@2"
        metadata = {u'derived_from_uri': invalid_derived_from_uri}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import InvalidMetadata
        from ..db import _validate_derived_from as validator
        with self.assertRaises(InvalidMetadata) as caught_exc:
            validator(cursor, model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['value'], invalid_derived_from_uri)

    @db_connect
    def test_12_valid_derived_from_uri(self, cursor):
        """Check that the derived-from can be found.
        This checks the logic used to validate when the exception
        should not be raised.
        """
        uuid_ = uuid.uuid4()
        # Create a published document with two versions.
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s);
INSERT INTO abstracts (abstractid, abstract) VALUES (1, 'abstract');
INSERT INTO modules
(module_ident, portal_type, moduleid, uuid, name,
 major_version, minor_version,
 created, revised, abstractid, licenseid,
 doctype, submitter, submitlog, stateid, parent, parentauthors,
 language, authors, maintainers, licensors,
 google_analytics, buylink)
VALUES
(1, 'Module', 'm10000', %s, 'v1',
 '1', DEFAULT,
 DEFAULT, DEFAULT, 1, 1,
 0, 'admin', 'log', DEFAULT, NULL, NULL,
 'en', '{admin}', NULL, '{admin}',
 DEFAULT, DEFAULT),
(2, 'Module', 'm10000', %s, 'v2',
 '2', DEFAULT,
 DEFAULT, DEFAULT, 1, 1,
 0, 'admin', 'log', NULL, NULL, NULL,
 'en', '{admin}', NULL, '{admin}',
 DEFAULT, DEFAULT);
        """, (uuid_, uuid_, uuid_,))

        # The following two cases test the query condition that specifies
        # which table to query against: modules or latest_modules.

        # Create a Document model, derived from a latest version.
        derived_from_uri = u"http://cnx.org/contents/{}".format(uuid_)
        metadata = {u'derived_from_uri': derived_from_uri}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..db import _validate_derived_from as validator
        validator(cursor, model)  # Should not raise an error.

        # Create a Document model, derived from a non-latest version.
        derived_from_uri = u"http://cnx.org/contents/{}@1".format(uuid_)
        metadata = {u'derived_from_uri': derived_from_uri}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..db import _validate_derived_from as validator
        validator(cursor, model)  # Should not raise an error.

    @db_connect
    def test_12_derived_from_uri_not_found(self, cursor):
        """Check for raised exception when the given derived-from is not found
        in the archive.
        """
        # Create a Document model.
        invalid_derived_from_uri = \
            u"http://cnx.org/contents/b07fd622-a2f1-4ccb-967c-9b966935961f"
        metadata = {u'derived_from_uri': invalid_derived_from_uri}
        model = self.make_document(metadata=metadata)

        # Call the in-question validator.
        from ..exceptions import InvalidMetadata
        from ..db import _validate_derived_from as validator
        with self.assertRaises(InvalidMetadata) as caught_exc:
            validator(cursor, model)
        exc = caught_exc.exception
        self.assertEqual(exc.__dict__['value'], invalid_derived_from_uri)
        self.assertEqual(exc._original_exception, None)


class ArchiveIntegrationTestCase(BaseDatabaseIntegrationTestCase):
    """Verify database interactions with a *Connexions Archive*
    Most of the minor details for this interaction are handled in the
    publish module tests. These tests bridge those slightly,
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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        cursor.execute("""\
            UPDATE modules SET stateid = 1 WHERE stateid = 5""")
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
        cursor.execute("SELECT tree_to_json(%s, '1.2', FALSE)::json",
                       (shared_binder.id,))
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
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@2',
                      u'shortId': u'LyhY6pM8@2',
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
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@2',
                      u'shortId': u'AUQV3irg@2',
                      u'slug': None,
                      u'title': u'Document Three'},
                     {u'id': u'deadbeef-a927-4652-9a8d-deb2d28fb801@1',
                      u'shortId': u'3q2-76kn@1',
                      u'slug': None,
                      u'title': u'Document Four'}],
                 }],
        }
        self.assertEqual(tree, expected_tree)
        cursor.execute("SELECT tree_to_json(%s, '2.1', FALSE)::json",
                       (binder.id,))
        tree = cursor.fetchone()[0]
        expected_tree = {
            u'id': u'dbb28a6b-cad2-4863-986f-6059da93386b@2.1',
            u'shortId': u'27KKa8rS@2.1',
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
                     {u'id': u'014415de-2ae0-4053-91bc-74c9db2704f5@2',
                      u'shortId': u'AUQV3irg@2',
                      u'slug': None,
                      u'title': u'Document Two'}],
                 },
                {u'id': u'subcol',
                 u'shortId': u'subcol',
                 u'title': u'Part Two',
                 u'slug': None,
                 u'contents': [
                     {u'id': u'2f2858ea-933c-4707-88d2-2e512e27252f@2',
                      u'shortId': u'LyhY6pM8@2',
                      u'slug': None,
                      u'title': u'Document Three'}],
                 }],
        }
        self.assertEqual(tree, expected_tree)

    @db_connect
    def test_publish_binder_w_document_pointers(self, cursor):
        """Ensure publication of binders with document pointers."""
        book_three = use_cases.setup_COMPLEX_BOOK_THREE_in_archive(self, cursor)
        cursor.connection.commit()
        # This book contains the pages used in book three.
        metadata = book_three.metadata.copy()
        del metadata['cnx-archive-uri']
        title = metadata['title'] = 'My copy of "{}"'.format(metadata['title'])
        binder = cnxepub.Binder(
            id='bacc12fe@draft', metadata=metadata,
            title_overrides=['P One', 'P Two'],
            nodes=[
                cnxepub.DocumentPointer(book_three[0].ident_hash),
                cnxepub.DocumentPointer(book_three[1].ident_hash),
            ],
        )

        # * Assemble the publication request.
        publication_id = self.make_publication(publisher='ream')
        for doc in cnxepub.flatten_to_documents(binder):
            self.persist_model(publication_id, doc)
        self.persist_model(publication_id, binder)

        # * Fire the publication request.
        from ..db import publish_pending
        state = publish_pending(cursor, publication_id)
        self.assertEqual(state, 'Done/Success')

        # * Ensure the binder was published with tree references to the existing
        # pages, which we are calling document pointers.
        cursor.execute("""\
SELECT ident_hash(uuid, major_version, minor_version),
       short_ident_hash(uuid, major_version, minor_version)
FROM modules WHERE name = %s""", (title,))
        binder_ident_hash, binder_short_id = cursor.fetchone()

        expected_tree = {
            "id": binder_ident_hash,
            "shortId": binder_short_id,
            "title": title,
            u'slug': None,
            "contents": [
                {"id": book_three[0].ident_hash,
                 "shortId": "MrEezaHC@1",
                 u'slug': None,
                 "title": "P One"},
                {"id": book_three[1].ident_hash,
                 "shortId": "3q2-76kn@1",
                 u'slug': None,
                 "title": "P Two"},
            ]}
        cursor.execute("""\
SELECT tree_to_json(uuid::text, module_version(major_version, minor_version), FALSE)
FROM modules
WHERE portal_type = 'Collection'""")
        tree = json.loads(cursor.fetchone()[0])
        self.assertEqual(expected_tree, tree)

    @db_connect
    def test_publish_binder_w_resources(self, cursor):
        """Ensure publication of binders with resources."""
        binder = deepcopy(use_cases.COMPLEX_BOOK_THREE)
        binder.resources = [
            cnxepub.Resource(
                use_cases.RESOURCE_ONE_FILENAME,
                io.BytesIO(open(use_cases.RESOURCE_ONE_FILEPATH).read()),
                'image/png',
                'cover.png'),
            cnxepub.Resource(
                'ruleset.css',
                io.BytesIO('div { move-to: trash }\n'),
                'text/css',
                'ruleset.css')]

        title = binder.metadata['title']

        # * Assemble the publication request.
        publication_id = self.make_publication(publisher='ream')
        for doc in cnxepub.flatten_to_documents(binder):
            self.persist_model(publication_id, doc)
        self.persist_model(publication_id, binder)

        # * Fire the publication request.
        from ..db import publish_pending
        state = publish_pending(cursor, publication_id)
        self.assertEqual(state, 'Done/Success')

        # * Ensure the binder was published with tree references to the existing
        # pages, which we are calling document pointers.
        cursor.execute("""\
SELECT ident_hash(uuid, major_version, minor_version),
       short_ident_hash(uuid, major_version, minor_version)
FROM modules WHERE name = %s""", (title,))
        binder_ident_hash, binder_short_id = cursor.fetchone()

        cursor.execute("""\
SELECT filename
FROM module_files
NATURAL JOIN files
NATURAL JOIN modules
WHERE ident_hash(uuid, major_version, minor_version) = %s
ORDER BY filename
""", (binder_ident_hash,))
        self.assertEqual([('cover.png',), ('ruleset.css',)],
                         cursor.fetchall())

    @db_connect
    def test_complex_republish(self, cursor):
        """Ensure republication of binders that share two or more documents."""
        # * Set up three collections in the archive. These are used
        # two of the three will be republished as minor versions.
        # The other will be part of the main publication context,
        # who's insertion into archive is outside the scope of this
        # test case.
        book_one = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        book_two = use_cases.setup_COMPLEX_BOOK_TWO_in_archive(self, cursor)
        book_three = use_cases.setup_COMPLEX_BOOK_THREE_in_archive(self, cursor)
        cursor.connection.commit()

        # Post publication worker will change the collection stateid to
        # "current" (1).
        cursor.execute("""\
            UPDATE modules SET stateid = 1 WHERE stateid = 5""")
        cursor.connection.commit()

        # * Make a new publication of book three.
        book_three.metadata['version'] = '2.1'
        book_three[0].metadata['version'] = '2'
        book_three[1].metadata['version'] = '2'
        # Set the ident-hash on the models. Probably not necessary...
        for model in (book_three[0], book_three[1], book_three,):
            model.set_uri('cnx-archive', '/contents/{}'.format(model.ident_hash))

        # * Assemble the publication request.
        publication_id = self.make_publication(publisher='ream')
        for doc in cnxepub.flatten_to_documents(book_three):
            self.persist_model(publication_id, doc)
        self.persist_model(publication_id, book_three)
        cursor.connection.commit()

        # * Invoke the publication request.
        from ..db import publish_pending
        state = publish_pending(cursor, publication_id)
        self.assertEqual(state, 'Done/Success')

        # * Ensure the binder was only published once due to the publication
        # request and the shared binder was republished as a minor revision.
        cursor.execute("SELECT count(*) FROM modules WHERE uuid = %s",
                       (book_three.id,))
        shared_binder_publication_count = cursor.fetchone()[0]
        self.assertEqual(shared_binder_publication_count, 2)
        cursor.connection.commit()

        # Check the shared binders got a minor version bump.
        cursor.execute("""\
SELECT uuid::text, array_agg(module_version(major_version, minor_version))
FROM modules
WHERE portal_type = 'Collection'
GROUP BY uuid
ORDER BY uuid, 2""")
        rows = cursor.fetchall()
        expected_rows = [
            (book_three.id, [book_three.metadata['version'], '1.1'],),
            (book_one.id, ['1.2', '1.1'],),
            (book_two.id, ['1.2', '1.1'],),
        ]
        self.assertEqual(rows, expected_rows)
