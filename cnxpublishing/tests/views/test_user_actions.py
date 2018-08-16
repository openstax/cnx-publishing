# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import uuid

from webtest import AppError

from ..testing import db_connect
from .base import BaseFunctionalViewTestCase


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

        headers = self.gen_api_key_headers('some-trust')

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

        headers = self.gen_api_key_headers('some-trust')

        licensors = [
            {'uid': 'marknewlyn', 'has_accepted': True},
            {'uid': 'charrose', 'has_accepted': True},
        ]

        # 1.
        path = "/contents/{}/licensors".format(uuid_)
        data = {'licensors': licensors}
        with self.assertRaises(AppError) as caught_exception:
            self.app.post_json(path, data, headers=headers)
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

        headers = self.gen_api_key_headers('some-trust')

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

        api_key_header = self.gen_api_key_headers('some-trust')
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
        users = {u: set(b) for u, b in cursor.fetchall()}
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

        api_key_header = self.gen_api_key_headers('some-trust')
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
