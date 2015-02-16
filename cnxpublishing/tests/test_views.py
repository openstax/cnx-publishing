# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import tempfile
import json
import shutil
import unittest
import uuid
import zipfile
from collections import OrderedDict
from copy import deepcopy

import psycopg2
import cnxepub
from cnxarchive import config as archive_config
from cnxarchive.database import initdb as archive_initdb
from cnxarchive.utils import join_ident_hash
from webob import Request
from webtest import TestApp
from webtest import AppError
from webtest.forms import Upload
from pyramid import testing
from pyramid import httpexceptions

from . import use_cases
from .testing import (
    integration_test_settings,
    db_connect, db_connection_factory,
    )


here = os.path.abspath(os.path.dirname(__file__))
TEST_DATA_DIR = os.path.join(here, 'data')


class PublishViewsTestCase(unittest.TestCase):

    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def test_epub_format_exception(self):
        """Test that we have a way to immediately fail if the EPUB
        is a valid EPUB structure. And all the files specified within
        the manifest and OPF documents.
        """
        post_data = {'epub': ('book.epub', b'')}
        request = Request.blank('/publications', POST=post_data)

        from ..views import publish
        with self.assertRaises(httpexceptions.HTTPBadRequest) as caught_exc:
            publish(request)

        exc = caught_exc.exception
        self.assertEqual(exc.args, ('Format not recognized.',))


class EPUBMixInTestCase(object):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir)

    def make_epub(self, binder, publisher, message):
        """Given a cnx-epub model, create an EPUB.
        This returns a temporary file location where the EPUB can be found.
        """
        zip_fd, zip_filepath = tempfile.mkstemp('.epub', dir=self.tmpdir)
        cnxepub.make_publication_epub(binder, publisher, message,
                                      zip_filepath)
        return zip_filepath

    def pack_epub(self, directory):
        """Given an directory containing epub contents,
        pack it up and make return filepath.
        Packed file is remove on test exit.
        """
        zip_fd, zip_filepath = tempfile.mkstemp('.epub', dir=self.tmpdir)
        with zipfile.ZipFile(zip_filepath, 'w') as zippy:
            base_path = os.path.abspath(directory)
            for root, dirs, filenames in os.walk(directory):
                # Strip the absolute path
                archive_path = os.path.abspath(root)[len(base_path):]
                for filename in filenames:
                    filepath = os.path.join(root, filename)
                    archival_filepath = os.path.join(archive_path, filename)
                    zippy.write(filepath, archival_filepath)
        return zip_filepath

    def copy(self, src, dst_name='book'):
        """Convenient method for copying test data directories."""
        dst = os.path.join(self.tmpdir, dst_name)
        shutil.copytree(src, dst)
        return dst


class BaseFunctionalViewTestCase(unittest.TestCase, EPUBMixInTestCase):
    """Request/response client interactions"""


    settings = None
    db_conn_str = None
    db_connect = None

    @property
    def api_keys_by_uid(self):
        """Mapping of uid to api key."""
        attr_name = '_api_keys'
        api_keys = getattr(self, attr_name, None)
        if api_keys is None:
            self.addCleanup(delattr, self, attr_name)
            from ..main import _parse_api_key_lines
            api_keys = _parse_api_key_lines(self.settings)
            setattr(self, attr_name, api_keys)
        return {x[1]:x[0] for x in api_keys}

    def gen_api_key_headers(self, user):
        """Generate authentication headers for the given user."""
        api_key = self.api_keys_by_uid[user]
        api_key_header = [('x-api-key', api_key,)]
        return api_key_header

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())
        cls._app = cls.make_app(cls.settings)

    @staticmethod
    def make_app(settings):
        from ..main import main
        app = main({}, **settings)
        return app

    @property
    def app(self):
        return TestApp(self._app)

    def setUp(self):
        EPUBMixInTestCase.setUp(self)
        config = testing.setUp(settings=self.settings)
        archive_settings = {
            archive_config.CONNECTION_STRING: self.db_conn_str,
            }
        archive_initdb(archive_settings)
        from ..db import initdb
        initdb(self.db_conn_str)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()


class UserActionsAPIFunctionalTestCase(BaseFunctionalViewTestCase):
    """User actions API request/response client interactions"""

    @db_connect
    def test_licensors_request(self, cursor):
        """Submit a set of users to initial license acceptance.

        1. Submit the license request.

        2. Verify the request entry.

        3. Submit a deletion request.

        4. Verify the request entry.

        """
        # Set up a document_controls entry to make it appear as if we
        # are working against a true piece of content.
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]
        cursor.connection.commit()

        api_key = self.api_keys_by_uid['some-trust']
        headers = [('x-api-key', api_key,)]

        licensors = [
            {'uid': 'marknewlyn', 'has_accepted': True},
            {'uid': 'charrose', 'has_accepted': True},
            ]
        license_url = u"http://creativecommons.org/licenses/by/4.0/"

        # 1.
        path = "/contents/{}/licensors".format(uuid_)
        data = {'license_url': license_url, 'licensors': licensors}
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # 2.
        expected = {
            u'license_url': license_url,
            u'licensors': [
                {u'uuid': unicode(uuid_), u'uid': u'charrose', u'has_accepted': True},
                {u'uuid': unicode(uuid_), u'uid': u'marknewlyn', u'has_accepted': True},
                ],
            }
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json, expected)

        # 3.
        data = {'licensors': [{'uid': 'marknewlyn'}]}
        resp = self.app.delete_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 200)

        # 4.
        expected = {
            u'license_url': license_url,
            u'licensors': [
                {u'uuid': unicode(uuid_), u'uid': u'charrose', u'has_accepted': True},
                ],
            }
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json, expected)

    @db_connect
    def test_licensors_request_wo_license(self, cursor):
        """Submit a set of users to initial license acceptance.

        1. Submit the license request, without a license.

        """
        # Set up a document_controls entry to make it appear as if we
        # are working against a true piece of content.
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]
        cursor.connection.commit()

        api_key = self.api_keys_by_uid['some-trust']
        headers = [('x-api-key', api_key,)]

        licensors = [
            {'uid': 'marknewlyn', 'has_accepted': True},
            {'uid': 'charrose', 'has_accepted': True},
            ]

        # 1.
        path = "/contents/{}/licensors".format(uuid_)
        data = {'licensors': licensors}
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("400 Bad Request") >= 0)

    @db_connect
    def test_license_request_w_license_change(self, cursor):
        """Submit a license acceptance request to change the license.

        1. Submit the license request, with an invalid license.

        2. Submit the license request, with an invalid publication license.

        3. Submit the license request, with a valid license.

        """
        # Set up a document_controls entry to make it appear as if we
        # are working against a true piece of content.
        cursor.execute("""\
INSERT INTO document_controls (uuid, licenseid) VALUES (DEFAULT, 11) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]
        cursor.connection.commit()

        api_key = self.api_keys_by_uid['some-trust']
        headers = [('x-api-key', api_key,)]

        uids = [{'uid': 'marknewlyn'}, {'uid': 'charrose'}]

        # 1.
        license_url = 'http://example.org/licenses/mine/2.0/'
        path = "/contents/{}/licensors".format(uuid_)
        data = {'license_url': license_url, 'licensors': uids}
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("400 Bad Request") >= 0)

        # 2.
        license_url = 'http://creativecommons.org/licenses/by/2.0/'
        path = "/contents/{}/licensors".format(uuid_)
        data = {'license_url': license_url, 'licensors': uids}
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("400 Bad Request") >= 0)

        # 3.
        license_url = 'http://creativecommons.org/licenses/by/4.0/'
        path = "/contents/{}/licensors".format(uuid_)
        data = {'license_url': license_url, 'licensors': uids}
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

    @db_connect
    def test_roles_request(self, cursor):
        """Submit a set of roles to be accepted.

        1. Submit the roles request.

        2. Verify the request entry.

        3. Submit a deletion request.

        4. Verify the request entry.

        """
        # Set up a document_controls entry to make it appear as if we
        # are working against a true piece of content.
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]
        cursor.connection.commit()

        api_key = self.api_keys_by_uid['some-trust']
        api_key_header = [('x-api-key', api_key,)]
        headers = [('content-type', 'application/json',)]
        headers.extend(api_key_header)

        # 1.
        path = "/contents/{}/roles".format(uuid_)
        data = [
            {'uid': 'charrose', 'role': 'Author', 'has_accepted': True},
            {'uid': 'marknewlyn', 'role': 'Author', 'has_accepted': True},
            {'uid': 'rings', 'role': 'Publisher', 'has_accepted': True},
            ]
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # *. Check for user info persistence. This is an upsert done when
        #    a role is submitted.
        cursor.execute("SELECT username, "
                       "ARRAY[first_name IS NOT NULL, "
                       "      last_name IS NOT NULL, "
                       "      full_name IS NOT NULL] "
                       "FROM users ORDER BY username")
        users = {u:set(b) for u, b in cursor.fetchall()}
        self.assertEqual(users.keys(), sorted([x['uid'] for x in data]))
        for username, null_checks in users.items():
            self.assertNotIn(None, null_checks,
                             '{} has a null value'.format(username))

        # 2.
        expected = [
            {'uuid': str(uuid_), 'uid': 'charrose',
             'role': 'Author', 'has_accepted': True},
            {'uuid': str(uuid_), 'uid': 'marknewlyn',
             'role': 'Author', 'has_accepted': True},
            {'uuid': str(uuid_), 'uid': 'rings',
             'role': 'Publisher', 'has_accepted': True},
            ]
        resp = self.app.get(path, headers=api_key_header)
        self.assertEqual(resp.json, expected)

        # 3.
        data = [
            {'uid': 'marknewlyn', 'role': 'Author', 'has_accepted': True},
            {'uid': 'marknewlyn', 'role': 'Publisher', 'has_accepted': True},
            ]
        resp = self.app.delete_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 200)

        # 4.
        expected = [
            {'uuid': str(uuid_), 'uid': 'charrose',
             'role': 'Author', 'has_accepted': True},
            {'uuid': str(uuid_), 'uid': 'rings',
             'role': 'Publisher', 'has_accepted': True},
            ]
        resp = self.app.get(path, headers=api_key_header)
        self.assertEqual(resp.json, expected)

    @db_connect
    def test_acl_request(self, cursor):
        """Submit a set of access control entries (ACE) to the ACL

        1. Submit the acl request.

        2. Verify the request entry.

        3. Submit a deletion request.

        4. Verify the request entry.

        """
        # Set up a document_controls entry to make it appear as if we
        # are working against a true piece of content.
        cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid""")
        uuid_ = cursor.fetchone()[0]
        cursor.connection.commit()

        api_key = self.api_keys_by_uid['some-trust']
        api_key_header = [('x-api-key', api_key,)]
        headers = [('content-type', 'application/json',)]
        headers.extend(api_key_header)

        # 1.
        path = "/contents/{}/permissions".format(uuid_)
        data = [
            {'uid': 'ream', 'permission': 'publish'},
            {'uid': 'rings', 'permission': 'publish'},
            ]
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # 2.
        expected = [
            {'uuid': str(uuid_), 'uid': 'ream', 'permission': 'publish'},
            {'uuid': str(uuid_), 'uid': 'rings', 'permission': 'publish'},
            ]
        resp = self.app.get(path, headers=api_key_header)
        self.assertEqual(resp.json, expected)

        # 3.
        data = [
            {'uid': 'rings', 'permission': 'publish'},
            ]
        resp = self.app.delete_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 200)

        # 4.
        expected = [
            {'uuid': str(uuid_), 'uid': 'ream', 'permission': 'publish'},
            ]
        resp = self.app.get(path, headers=api_key_header)
        self.assertEqual(resp.json, expected)

    def test_create_identifier_on_licensors_request(self):
        """Submit a set of users to initial license acceptance.
        This tests whether a trusted publisher has the permission
        to create an identifer where one previously didn't exist.

        1. Submit the license request (as *untrusted* app user).

        2. Submit the license request (as *trusted* app user).

        3. Verify the request entry.

        """
        uuid_ = uuid.uuid4()

        license_url = u"http://creativecommons.org/licenses/by/4.0/"
        licensors = [
            {'uid': 'marknewlyn', 'has_accepted': True},
            {'uid': 'charrose', 'has_accepted': True},
            ]

        path = "/contents/{}/licensors".format(uuid_)
        data = {
            'license_url': license_url,
            'licensors': licensors,
            }

        # 1.
        headers = self.gen_api_key_headers('no-trust')
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("403 Forbidden") >= 0)

        # 2.
        headers = self.gen_api_key_headers('some-trust')
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # 3.
        expected = {
            u'license_url': license_url,
            u'licensors': [
                {u'uuid': unicode(uuid_), u'uid': u'charrose',
                 u'has_accepted': True},
                {u'uuid': unicode(uuid_), u'uid': u'marknewlyn',
                 u'has_accepted': True},
                ],
            }
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json, expected)

    def test_create_identifier_on_roles_request(self):
        """Submit a set of roles to be accepted.
        This tests whether a trusted publisher has the permission
        to create an identifer where one previously didn't exist.

        1. Submit the roles request.

        2. Submit the license request (as *trusted* app user).

        3. Verify the request entry.

        """
        uuid_ = uuid.uuid4()
        base_headers = [('content-type', 'application/json',)]

        path = "/contents/{}/roles".format(uuid_)
        data = [
            {'uid': 'charrose', 'role': 'Author'},
            {'uid': 'marknewlyn', 'role': 'Author', 'has_accepted': False},
            {'uid': 'rings', 'role': 'Publisher', 'has_accepted': True},
            ]

        # 1.
        headers = self.gen_api_key_headers('no-trust')
        headers.extend(base_headers)
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("403 Forbidden") >= 0)

        # 2.
        headers = self.gen_api_key_headers('some-trust')
        headers.extend(base_headers)
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # 3.
        expected = [
            {'uuid': str(uuid_), 'uid': 'charrose',
             'role': 'Author', 'has_accepted': None},
            {'uuid': str(uuid_), 'uid': 'marknewlyn',
             'role': 'Author', 'has_accepted': False},
            {'uuid': str(uuid_), 'uid': 'rings',
             'role': 'Publisher', 'has_accepted': True},
            ]
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json, expected)

    def test_create_identifier_on_acl_request(self):
        """Submit a set of access control entries (ACE) to the ACL
        This tests whether a trusted publisher has the permission
        to create an identifer where one previously didn't exist.

        1. Submit the acl request.

        2. Submit the license request (as *trusted* app user).

        3. Verify the request entry.

        """
        uuid_ = uuid.uuid4()
        base_headers = [('content-type', 'application/json',)]

        path = "/contents/{}/permissions".format(uuid_)
        data = [
            {'uid': 'ream', 'permission': 'publish'},
            {'uid': 'rings', 'permission': 'publish'},
            ]

        # 1.
        headers = self.gen_api_key_headers('no-trust')
        headers.extend(base_headers)
        with self.assertRaises(AppError) as caught_exception:
            resp = self.app.post_json(path, data, headers=headers)
        exception = caught_exception.exception
        self.assertTrue(exception.args[0].find("403 Forbidden") >= 0)

        # 2.
        headers = self.gen_api_key_headers('some-trust')
        headers.extend(base_headers)
        resp = self.app.post_json(path, data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # 3.
        expected = [
            {'uuid': str(uuid_), 'uid': 'ream', 'permission': 'publish'},
            {'uuid': str(uuid_), 'uid': 'rings', 'permission': 'publish'},
            ]
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json, expected)


    def test_create_identifier_for_all_routes(self):
        """Tests that creating an identifier result in non-404
        on other routes. See also,
        https://github.com/Connexions/cnx-publishing/issues/52
        """
        # POST a permission set
        data = [{'uid': 'ream', 'permission': 'publish'}]
        uuid_ = uuid.uuid4()
        path = '/contents/{}/permissions'
        headers = self.gen_api_key_headers('some-trust')
        resp = self.app.post_json(path.format(uuid_), data, headers=headers)
        self.assertEqual(resp.status_int, 202)

        # Also, check that we still get 404 for non-existent controls.
        other_uuid = uuid.uuid4()

        # Check the response...
        resp = self.app.get(path.format(uuid_))
        data[0]['uuid'] = str(uuid_)
        self.assertEqual(resp.json, data)
        with self.assertRaises(AppError) as caught_exc:
            self.app.get(path.format(other_uuid))
        self.assertIn('404', caught_exc.exception.message)

        # And check the other two routes at least result in 200 OK
        path = '/contents/{}/licensors'
        licensors_resp = self.app.get(path.format(uuid_))
        self.assertEqual(licensors_resp.status_int, 200)
        with self.assertRaises(AppError) as caught_exc:
            self.app.get(path.format(other_uuid))
        self.assertIn('404', caught_exc.exception.message)

        path = '/contents/{}/roles'
        roles_resp = self.app.get(path.format(uuid_))
        self.assertEqual(roles_resp.status_int, 200)
        with self.assertRaises(AppError) as caught_exc:
            self.app.get(path.format(other_uuid))
        self.assertIn('404', caught_exc.exception.message)

        # And check the contents...
        self.assertEqual(licensors_resp.json,
                         {'license_url': None, 'licensors': []})
        self.assertEqual(roles_resp.json, [])


class PublishingAPIFunctionalTestCase(BaseFunctionalViewTestCase):
    """Publishing API request/response client interactions"""

    def _setup_to_archive(self, use_case):
        """Used to setup a content set in the archive.
        This is most useful when publishing revisions.
        """
        setup_mapping = {
            use_cases.BOOK: use_cases.setup_BOOK_in_archive,
            }
        try:
            setup = setup_mapping[use_case]
        except:
            raise ValueError("Unknown use-case. See code comments.")
        # If the above ValueError is raised, then you need to add
        # a setup method to the setup mapping.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                setup(self, cursor)

    def _check_published_to_archive(self, use_case):
        checker_mapping = {
            use_cases.BOOK: use_cases.check_BOOK_in_archive,
            use_cases.REVISED_BOOK: use_cases.check_REVISED_BOOK_in_archive,
            }
        try:
            checker = checker_mapping[use_case]
        except:
            raise ValueError("Unknown use-case. See code comments.")
        # If the above ValueError is raised, then you need to add
        # a checker mapping to a checker callable.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                checker(self, cursor)

    # #################### #
    #   Web app test API   #
    # #################### #
    # - ``app_check*`` methods are self contained checks on a process
    #   or series of processes. These methods return ``None``.
    # - ``app_(get|put|post|delete)*`` methods call against the
    #   application and return the response.

    def app_check_state(self, publication_id, expected_state,
                        headers=[]):
        path = "/publications/{}".format(publication_id)
        resp = self.app.get(path, headers=headers)
        self.assertEqual(resp.json['state'], expected_state)

    def app_post_publication(self, epub_filepath, is_pre_publication=False,
                             headers=[], status=None):
        with open(epub_filepath, 'rb') as epub:
            params = OrderedDict(
                [('pre-publication', str(is_pre_publication),),
                 ('epub', Upload('book.epub', content=epub.read()),)])
        resp = self.app.post('/publications', params=params,
                             headers=headers, status=status)
        return resp

    def app_get_license_acceptance(self, publication_id, uid, headers=[]):
        """User at ``uid`` lookups up the HTML page for license acceptance."""
        path = '/publications/{}/license-acceptances/{}' \
            .format(publication_id, uid)
        return self.app.get(path, headers=headers)

    def app_post_json_license_acceptance(self, publication_id, uid,
                                         data, headers=[]):
        """User at ``uid`` accepts the license for publication at
        ``publication_id either for or against as ``accept``.
        The ``data`` value is expected to be a python type that
        this method will marshal to JSON.
        """
        path = '/publications/{}/license-acceptances/{}' \
            .format(publication_id, uid)
        resp = self.app.post_json(path, data, headers=headers)

    def app_get_role_acceptance(self, publication_id, uid, headers=[]):
        """User at ``uid`` lookups up the HTML page for role acceptance."""
        path = '/publications/{}/role-acceptances/{}' \
            .format(publication_id, uid)
        return self.app.get(path, headers=headers)

    def app_post_json_role_acceptance(self, publication_id, uid,
                                      data, headers=[]):
        """User at ``uid`` accepts the attributed role for publication at
        ``publication_id either for or against as ``accept``.
        The ``data`` value is expected to be a python type that
        this method will marshal to JSON.
        """
        path = '/publications/{}/role-acceptances/{}' \
            .format(publication_id, uid)
        resp = self.app.post_json(path, data, headers=headers)

    def app_post_acl(self, uuid_, data, headers=[]):
        """Submission of ACL information for content at ``uuid``.
        The ``data`` value is expected to be a python type that this method
        will marshal to JSON.
        """
        path = '/contents/{}/permissions'.format(uuid_)
        resp = self.app.post_json(path, data, headers=headers)

    # ######### #
    #   Tests   #
    # ######### #
    # - the contents of the publication contents are of lesser
    #   important to that of the process itself.
    # - the tests are firstly divided into trusted and untrusted cases.
    # - the tests are secondly divided into new, existing and mixed
    #   document/binder content publications.

    def test_new_to_publication(self):
        """\
        Publish *new* documents.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. For each *attributed role*...

           - As the publisher, accept the license.
           - As the copyright-holder, accept the license.
           - As [other attributed roles], accept the license.

        3. For each *attributed role*...

           - As [an attributed role], accept my attribution
             on these documents/binders in this publication.

        4. Verify documents are in the archive. [HACKED]

        """
        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['no-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)
        # -.-  Check that users have been notified.
        #      We can check this using the stub memory writer,
        #      which has been configured for the application.
        # TODO temporarily commented out, see 31ddc32
#        from openstax_accounts.stub import IStubMessageWriter
#        registry = self._app.registry
#        accounts_stub_writer = registry.getUtility(IStubMessageWriter)
#        with self.db_connect() as db_conn:
#            with db_conn.cursor() as cursor:
#                cursor.execute("SELECT count(*) FROM license_acceptances "
#                               "WHERE notified IS NOT NULL")
#                self.assertEqual(cursor.fetchone()[0], 13)
#                cursor.execute("SELECT count(*) FROM role_acceptances "
#                               "WHERE notified IS NOT NULL")
#                self.assertEqual(cursor.fetchone()[0], 15)

        # 2. --
        # TODO This uses the JSON get/post parts; revision publications
        #      should attempt to use the HTML form.
        #      Check the form contains for the correct documents and default
        #      values. This is going to be easier to look
        #      at and verify in a revision publication, where we can depend
        #      on known uuid values.
        uids = (
            'charrose', 'frahablar', 'impicky', 'marknewlyn', 'ream',
            'rings', 'sarblyth',
            )
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_license_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_license_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM license_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "the licenses.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. Check for user info persistence. This is an upsert done when
        #    a role is submitted.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT username, "
                               "ARRAY[first_name IS NOT NULL, "
                               "      last_name IS NOT NULL, "
                               "      full_name IS NOT NULL] "
                               "FROM users ORDER BY username")
                users = {u:set(b) for u, b in cursor.fetchall()}
        self.assertEqual(sorted(users.keys()), sorted(uids))
        for username, null_checks in users.items():
            self.assertNotIn(None, null_checks,
                             '{} has a null value'.format(username))

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 3. --
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_role_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_role_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM role_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "role attribution.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        self._check_published_to_archive(use_cases.BOOK)

    def test_new_to_pre_publication(self):
        """\
        Publish *new* documents for pre-publication.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. For each *attributed role*...

           - As the publisher, accept the license.
           - As the copyright-holder, accept the license.
           - As [other attributed roles], accept the license.

        3. For each *attributed role*...

           - As [an attributed role], accept my attribution
             on these documents/binders in this publication.

        4. Verify documents are *not* in the archive.
           Verify documents have been given an identifier.
           Verify permissions have been set. [HACKED]

        """
        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['no-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         is_pre_publication=True,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 2. --
        # TODO This uses the JSON get/post parts; revision publications
        #      should attempt to use the HTML form.
        #      Check the form contains for the correct documents and default
        #      values. This is going to be easier to look
        #      at and verify in a revision publication, where we can depend
        #      on known uuid values.
        uids = (
            'charrose', 'frahablar', 'impicky', 'marknewlyn', 'ream',
            'rings', 'sarblyth',
            )
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_license_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_license_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM license_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "the licenses.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 3. --
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_role_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_role_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM role_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "role attribution.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM modules")
                module_count = cursor.fetchone()[0]
                self.assertEqual(module_count, 0)
                cursor.execute("SELECT count(*) FROM document_controls")
                controls_count = cursor.fetchone()[0]
                self.assertEqual(controls_count, 2)

    def test_revision(self):
        """\
        Publish *revised* documents.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. For each *attributed role*...

           - As the publisher, accept the license.
           - As the copyright-holder, accept the license.
           - As [other attributed roles], accept the license.

        3. For each *attributed role*...

           - As [an attributed role], accept my attribution
             on these documents/binders in this publication.

        4. Verify documents are in the archive. [HACKED]

        """
        # Insert the BOOK use-case in order to make a revision of it.
        self._setup_to_archive(use_cases.BOOK)

        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['no-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 2. --
        # TODO This uses the JSON get/post parts; revision publications
        #      should attempt to use the HTML form.
        #      Check the form contains for the correct documents and default
        #      values. This is going to be easier to look
        #      at and verify in a revision publication, where we can depend
        #      on known uuid values.
        uids = (
            'charrose', 'frahablar', 'impicky', 'marknewlyn', 'ream',
            'rings', 'sarblyth',
            )
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_license_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_license_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM license_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "the licenses.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 3. --
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_role_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_role_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM role_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "role attribution.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        self._check_published_to_archive(use_cases.REVISED_BOOK)

    def test_revision_pre_publication(self):
        """\
        Publish *revised* documents for pre-publication.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. For each *attributed role*...

           - As the publisher, accept the license.
           - As the copyright-holder, accept the license.
           - As [other attributed roles], accept the license.

        3. For each *attributed role*...

           - As [an attributed role], accept my attribution
             on these documents/binders in this publication.

        4. Verify documents are in the archive. [HACKED]

        """
        # Insert the BOOK use-case in order to make a revision of it.
        self._setup_to_archive(use_cases.BOOK)

        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['no-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         is_pre_publication=True,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 2. --
        # TODO This uses the JSON get/post parts; revision publications
        #      should attempt to use the HTML form.
        #      Check the form contains for the correct documents and default
        #      values. This is going to be easier to look
        #      at and verify in a revision publication, where we can depend
        #      on known uuid values.
        uids = (
            'charrose', 'frahablar', 'impicky', 'marknewlyn', 'ream',
            'rings', 'sarblyth',
            )
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_license_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_license_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM license_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "the licenses.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        self.app_check_state(publication_id, 'Waiting for acceptance',
                             headers=api_key_headers)

        # 3. --
        for uid in uids:
            # -- Check the form has the correct values.
            resp = self.app_get_role_acceptance(
                publication_id, uid,
                headers=[('Accept', 'application/json',)])
            acceptance_data = resp.json
            document_acceptance_data = [e for e in acceptance_data['documents']]
            for doc_record in document_acceptance_data:
                doc_record[u'is_accepted'] = True
            acceptance_data['documents'] = document_acceptance_data
            resp = self.app_post_json_role_acceptance(
                publication_id, uid, acceptance_data)
        # -- (manual) Check the records for acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM role_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "role attribution.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        # Checks ``latest_modules`` by virtue of the ``tree_to_json``
        # plsql function. If REVISED_BOOK was not in published,
        # checking for the previous revision should be correct.
        self._check_published_to_archive(use_cases.BOOK)

    def test_identifier_creation_to_publication(self):
        """\
        Publish documents for that have been identifier created.
        This includes application and user interactions with publishing.

        This is the workflow that would typically be used by cnx-authoring.

        *. After each step, check the state of the publication.

        1. Submit content identifiers as ACL assignement requests.
           And submit roles for license and role assignment requests.

        2. For each *attributed role*...

           - As the publisher, accept the license.
           - As the copyright-holder, accept the license.
           - As [other attributed roles], accept the license.

        3. For each *attributed role*...

           - As [an attributed role], accept my attribution
             on these documents/binders in this publication.

        4. Submit an EPUB containing a book of documents.

        5. Verify documents are in the archive. [HACKED]

        """
        publisher = u'ream'
        # We use the REVISED_BOOK here, because it contains fixed identifiers.
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        from cnxarchive.utils import split_ident_hash
        ids = [
            split_ident_hash(use_cases.REVISED_BOOK.id)[0],
            split_ident_hash(use_cases.REVISED_BOOK[0][0].id)[0],
            ]
        for id in ids:
            resp = self.app_post_acl(
                id, [{'uid': publisher, 'permission': 'publish'}],
                headers=api_key_headers)

        # 2. & 3. --
        attr_role_key_to_db_role = {
            'publishers': 'Publisher', 'copyright_holders': 'Copyright Holder',
            'editors': 'Editor', 'illustrators': 'Illustrator',
            'translators': 'Translator', 'authors': 'Author',
            }
        for model in (use_cases.REVISED_BOOK, use_cases.REVISED_BOOK[0][0],):
            id = split_ident_hash(model.id)[0]
            attributed_roles = []
            roles = []
            for role_key in cnxepub.ATTRIBUTED_ROLE_KEYS:
                for role in model.metadata.get(role_key, []):
                    role_name = attr_role_key_to_db_role[role_key]
                    attributed_roles.append({'uid': role['id'],
                                             'role': role_name,
                                             'has_accepted': True})
                    if role['id'] not in [r['uid'] for r in roles]:
                        roles.append({'uid': role['id'], 'has_accepted': True})
            # Post the accepted attributed roles.
            path = "/contents/{}/roles".format(id)
            self.app.post_json(path, attributed_roles,
                               headers=api_key_headers)
            # Post the accepted licensors.
            path = "/contents/{}/licensors".format(id)
            data = {'license_url': 'http://creativecommons.org/licenses/by/4.0/',
                    'licensors': roles,
                    }
            self.app.post_json(path, data, headers=api_key_headers)

        # -- (manual) Check the records for license acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM license_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "the licenses.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # -- (manual) Check the records for role acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""
SELECT user_id, accepted
FROM role_acceptances
GROUP BY user_id, accepted
""")
                acceptance_records = cursor.fetchall()
                for user_id, has_accepted in acceptance_records:
                    failure_message = "{} has not accepted " \
                                      "role attribution.".format(user_id)
                    self.assertTrue(has_accepted, failure_message)

        # 4. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Done/Success')
        publication_id = resp.json['publication']

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 5. (manual)
        # Checks ``latest_modules`` by virtue of the ``tree_to_json``
        # plsql function.
        binder = use_cases.REVISED_BOOK
        document = use_cases.REVISED_BOOK[0][0]
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                # Check the module records...
                cursor.execute("""\
SELECT uuid, moduleid, major_version, minor_version, version
FROM modules ORDER BY major_version ASC""")
                records = {}
                key_sep = '--'
                for row in cursor.fetchall():
                    key = key_sep.join([str(x) for x in row[:2]])
                    value = list(row[2:])
                    if key not in records:
                        records[key] = []
                    records[key].append(value)
                binder_uuid = split_ident_hash(binder.id)[0]
                document_uuid = split_ident_hash(document.id)[0]
                expected_records = {
                    # [uuid, moduleid]: [[major_version, minor_version, version], ...]
                    key_sep.join([binder_uuid, 'col10000']): [
                        [1, 1, '1.1'],  # REVISED_BOOK
                        ],
                    key_sep.join([document_uuid, 'm10000']): [
                        [1, None, '1.1'],
                        ],
                    }
                self.assertEqual(expected_records, records)

                # Check the tree...
                # This also proves that the REVISED_BOOK is in latest_modules
                # by virtual of using the tree_to_json function.
                binder_ident_hash = join_ident_hash(
                    split_ident_hash(binder.id)[0], (1, 1,))
                document_ident_hash = join_ident_hash(
                    split_ident_hash(document.id)[0], (1, None,))
                expected_tree = {
                    u"id": unicode(binder_ident_hash),
                    u"title": u"Book of Infinity",
                    u"contents": [
                        {u"id": u"subcol",
                         u"title": use_cases.REVISED_BOOK[0].metadata['title'],
                         u"contents": [
                             {u"id": unicode(document_ident_hash),
                              u"title": use_cases.REVISED_BOOK[0].get_title_for_node(document)}]}]}
                cursor.execute("""\
SELECT tree_to_json(uuid::text, concat_ws('.', major_version, minor_version))
FROM latest_modules
WHERE portal_type = 'Collection'""")
                tree = json.loads(cursor.fetchone()[0])
                self.assertEqual(expected_tree, tree)

    def test_new_to_publication_w_exceptions(self):
        """\
        Publish *new* *invalid* documents from an *trusted* application.
        This proves that the publication creates identifiers for
        the failing content and provides an exception gob in the response.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. Verify the failure messages exist and the content entries
           have been created.

        """
        publisher = u'ream'
        use_case = deepcopy(use_cases.BOOK)
        # Set the 'license_url' to something invalid.
        use_case.metadata['license_url'] = 'http://example.com/public-domain'
        # Set an author value to an invalid type.
        authors = use_case[0][0][0].metadata['authors']
        authors[0]['type'] = 'diaspora-id'
        epub_filepath = self.make_epub(use_case, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Failed/Error')
        publication_id = resp.json['publication']
        messages = resp.json['messages']
        codes = sorted([(m['code'], m['type'],) for m in messages])
        self.assertEqual(codes,
                         [(10, u'InvalidLicense'), (11, u'InvalidRole')])

        # *. --
        self.app_check_state(publication_id, 'Failed/Error',
                             headers=api_key_headers)

    def test_new_to_publication_size_limit_exceeded(self):
        publisher = u'ream'
        use_case = deepcopy(use_cases.BOOK)
        use_case.append(use_cases.PAGE_FIVE)
        epub_filepath = self.make_epub(use_case, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        resp = self.app_post_publication(epub_filepath, headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Failed/Error')
        publication_id = resp.json['publication']
        self.maxDiff = None
        error_messages = resp.json['messages']
        self.assertEqual(len(error_messages), 1)
        self.assertEqual(error_messages[0]['code'], 22)
        self.assertEqual(
                error_messages[0]['message'],
                'Resource files cannot be bigger than 1MB (big-file.txt)')

        self.app_check_state(publication_id, 'Failed/Error',
                             headers=api_key_headers)

    def test_new_to_publication_epub_stored(self):
        """\
        Publish a new document from a trusted application, verify the epub
        is stored in the database
        """
        publisher = u'ream'
        use_case = deepcopy(use_cases.BOOK)
        epub_filepath = self.make_epub(
            use_case, publisher, u'publishing this book')

        # upload to publishing
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        publication_id = resp.json['publication']

        # Check that the epub file is stored in the database
        with open(epub_filepath, 'r') as f:
            epub_content = f.read()
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute('SELECT epub FROM publications'
                               '  WHERE id = %s', (publication_id,))
                epub_in_db = cursor.fetchone()[0][:]

        self.assertEqual(len(epub_content), len(epub_in_db))
        self.assertEqual(epub_content, epub_in_db)

    def test_new_to_publication_license_not_accepted(self):
        """Publish documents only after all users have accepted the license"""
        publisher = u'ream'
        # We use the REVISED_BOOK here, because it contains fixed identifiers.
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # Give publisher permission to publish
        from cnxarchive.utils import split_ident_hash
        ids = [
            split_ident_hash(use_cases.REVISED_BOOK.id)[0],
            split_ident_hash(use_cases.REVISED_BOOK[0][0].id)[0],
            ]
        for id in ids:
            resp = self.app_post_acl(
                id, [{'uid': publisher, 'permission': 'publish'}],
                headers=api_key_headers)

        attr_role_key_to_db_role = {
            'publishers': 'Publisher', 'copyright_holders': 'Copyright Holder',
            'editors': 'Editor', 'illustrators': 'Illustrator',
            'translators': 'Translator', 'authors': 'Author',
            }
        for model in (use_cases.REVISED_BOOK, use_cases.REVISED_BOOK[0][0],):
            id = split_ident_hash(model.id)[0]
            attributed_roles = []
            roles = []
            for role_key in cnxepub.ATTRIBUTED_ROLE_KEYS:
                for role in model.metadata.get(role_key, []):
                    role_name = attr_role_key_to_db_role[role_key]
                    attributed_roles.append({'uid': role['id'],
                                             'role': role_name,
                                             'has_accepted': True})
                    if role['id'] not in [r['uid'] for r in roles]:
                        roles.append({'uid': role['id'], 'has_accepted': True})
            # Post the accepted attributed roles.
            path = "/contents/{}/roles".format(id)
            self.app.post_json(path, attributed_roles,
                               headers=api_key_headers)
            # Post the accepted licensors. (everyone except one)
            path = "/contents/{}/licensors".format(id)
            data = {'license_url': 'http://creativecommons.org/licenses/by/4.0/',
                    'licensors': roles[:-1],
                    }
            self.app.post_json(path, data, headers=api_key_headers)

        # Check publication state
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # Post the last accepted licensor.
        for model in (use_cases.REVISED_BOOK, use_cases.REVISED_BOOK[0][0],):
            id = split_ident_hash(model.id)[0]
            path = "/contents/{}/licensors".format(id)
            data = {'license_url': 'http://creativecommons.org/licenses/by/4.0/',
                    'licensors': [roles[-1]],
                    }
            self.app.post_json(path, data, headers=api_key_headers)

        # Check publication state
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Done/Success')
        publication_id = resp.json['publication']

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)
