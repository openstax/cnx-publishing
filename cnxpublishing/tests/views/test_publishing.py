# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import json
import unittest
from collections import OrderedDict
from copy import deepcopy
import uuid
try:
    from unittest import mock
except ImportError:
    import mock

import cnxepub
from pyramid import httpexceptions
from pyramid import testing
from webob import Request
from webtest.forms import Upload

from .. import use_cases
from ..testing import db_connect
from .base import BaseFunctionalViewTestCase
from ...bake import bake


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

        from cnxpublishing.views.publishing import publish
        with self.assertRaises(httpexceptions.HTTPBadRequest) as caught_exc:
            publish(request)

        exc = caught_exc.exception
        self.assertEqual(exc.args, ('Format not recognized.',))


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
        except:  # noqa: E722
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
        except:  # noqa: E722
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
        self.app.post_json(path, data, headers=headers)

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
        self.app.post_json(path, data, headers=headers)

    def app_post_acl(self, uuid_, data, headers=[]):
        """Submission of ACL information for content at ``uuid``.
        The ``data`` value is expected to be a python type that this method
        will marshal to JSON.
        """
        path = '/contents/{}/permissions'.format(uuid_)
        self.app.post_json(path, data, headers=headers)

    def app_get_moderation(self, headers=[]):
        """Gets a list of the publication that are currently being moderated.
        """
        path = '/moderations'
        resp = self.app.get(path, headers=headers)
        return resp

    def app_post_moderation(self, publication_id, data, headers=[]):
        """Moderate the publication by sending an accept/reject state."""
        path = '/moderations/{}'.format(publication_id)
        resp = self.app.post_json(path, data, headers=headers)
        return resp

    def app_login(self, username, password):
        """Logins in to the app using (a stub) accounts."""
        path = '/stub-login-form'
        data = {
            'username': username,
            'password': password,
        }
        resp = self.app.post(path, data)
        return resp

    def app_logout(self):
        """Logout of the app."""
        path = '/logout'
        resp = self.app.get(path)
        return resp

    def _extract_cookie_header(self, resp):
        """Extracts the cookie header from a login response."""
        cookie = resp.headers['set-cookie']
        return [('cookie', cookie,)]

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

        4. Wait for moderation acceptance from a moderator.

        5. Verify documents are in the archive. [HACKED]

        """
        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.BOOK, publisher,
                                       u'públishing this book')
        api_key_headers = self.gen_api_key_headers('no-trust')

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
                users = {u: set(b) for u, b in cursor.fetchall()}
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

        # 4. (manual)
        # Check that our publication is in the moderation list.
        resp = self.app_login('direwolf', 'direwolf')
        headers = self._extract_cookie_header(resp)
        resp = self.app_get_moderation(headers=headers)
        self.assertIn(publication_id, [p['id'] for p in resp.json])
        # Now post the moderation approval.
        resp = self.app_post_moderation(publication_id,
                                        {'is_accepted': True},
                                        headers=headers)

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 5. (manual)
        self._check_published_to_archive(use_cases.BOOK)

    def test_publishing_spam(self):
        """\
        Publish *new* documents.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        *. Accept the roles and license.

        2. Wait for moderation acceptance from a moderator.

        3. Verify rejection. [HACKED]

        """
        publisher = u'happy'
        epub_filepath = self.make_epub(use_cases.SPAM, publisher,
                                       u'please publish my spam')
        api_key_headers = self.gen_api_key_headers('no-trust')

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Waiting for acceptance')
        publication_id = resp.json['publication']

        # *. --
        # Assume this person as passed through approval by virtue
        #   of being the creating user (from the cnx-authoring perspective).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT uuid from pending_documents WHERE publication_id = %s""",
                               (publication_id,))
                uuids = [x[0] for x in cursor.fetchall()]
                cursor.execute("""\
UPDATE role_acceptances SET (accepted) = ('t');
UPDATE license_acceptances SET (accepted) = ('t');""")

        # Poke the publication into moderation.
        from cnxpublishing.db import poke_publication_state
        poke_publication_state(publication_id)

        # *. --
        self.app_check_state(publication_id, 'Waiting for moderation',
                             headers=api_key_headers)

        # 2. (manual)
        # Check that our publication is in the moderation list.
        resp = self.app_login('direwolf', 'direwolf')
        headers = self._extract_cookie_header(resp)
        resp = self.app_get_moderation(headers=headers)
        self.assertIn(publication_id, [p['id'] for p in resp.json])
        # Now post the moderation rejection.
        resp = self.app_post_moderation(publication_id,
                                        {'is_accepted': False},
                                        headers=headers)

        # *. --
        # This is publication completion.
        self.app_check_state(publication_id, 'Rejected',
                             headers=api_key_headers)

        # 5. (manual)
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
SELECT 'eek' FROM modules WHERE uuid = ANY (%s)""", (uuids,))
                self.assertIsNone(cursor.fetchone())

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
        api_key_headers = self.gen_api_key_headers('no-trust')

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

        Note, the original publication was done by the user, 'rings',
        while this one is done by 'ream'. 'reams' has vouched for 'rings',
        which means moderation won't be necessary.

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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid = 1 WHERE stateid = 5""")

        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key_headers = self.gen_api_key_headers('no-trust')

        # Moderation is not required, because the publisher is already
        #   vetted by having previously been attributed on one or more
        #   published documents.

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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid = 1 WHERE stateid = 5""")

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        self._check_published_to_archive(use_cases.REVISED_BOOK)

    def test_revision_w_new_vetted_publisher(self):
        """\
        Publish *revised* documents as a *new publisher*.
        This includes application and user interactions with publishing.

        Note, the original publication was done by the user, 'rings',
        while this one is done by 'ream'. The moderation of this
        publication has been done by 'reams'.

        The new publisher 'able' is not a member of any published content.
        Therefore, 'able' has not been *moderated* for publications.
        However, by virtue of being added as a publisher to this content
        'able' has been vetted by someone on the content. This only
        works if one or more of the published documents are a revision.

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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid = 1 WHERE stateid = 5""")

        publisher = u'able'
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key_headers = self.gen_api_key_headers('no-trust')

        # Moderation is not required, because the publisher is
        #   vetted by virtue of being added by a another vetted user.

        # Add this publisher to the ACL.
        from cnxpublishing.utils import split_ident_hash
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                book = use_cases.REVISED_BOOK
                ident_hashs = [book.id]
                ident_hashs.extend(
                    [d.id for d in cnxepub.flatten_to_documents(book)])
                for ident_hash in ident_hashs:
                    id, _ = split_ident_hash(ident_hash)
                    cursor.execute("""\
INSERT INTO document_acl (uuid, user_id, permission)
VALUES (%s, %s, 'publish')""", (id, publisher,))

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

        # Post publication worker will change the collection stateid to
        # "current" (1).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid = 1 WHERE stateid = 5""")

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
        api_key_headers = self.gen_api_key_headers('no-trust')

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

        5. Moderate the publication.

        6. Verify documents are in the archive. [HACKED]

        """
        publisher = u'ream'
        # We use the REVISED_BOOK here, because it contains fixed identifiers.
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing this book')
        api_key_headers = self.gen_api_key_headers('some-trust')

        # 1. --
        from cnxpublishing.utils import split_ident_hash
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
        self.assertEqual(resp.json['state'], 'Waiting for moderation')
        publication_id = resp.json['publication']

        # 5. (manual)
        # Check that our publication is in the moderation list.
        resp = self.app_login('direwolf', 'direwolf')
        headers = self._extract_cookie_header(resp)
        resp = self.app_get_moderation(headers=headers)
        self.assertIn(publication_id, [p['id'] for p in resp.json])
        # Now post the moderation approval.
        resp = self.app_post_moderation(publication_id,
                                        {'is_accepted': True},
                                        headers=headers)

        # Post publication worker will change the collection stateid to
        # "current" (1).
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
                    UPDATE modules SET stateid = 1 WHERE stateid = 5""")

        # *. --
        # This is publication completion,
        # because all licenses and roles have been accepted.
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 6. (manual)
        # Checks ``latest_modules`` by virtue of the ``tree_to_json``
        # plsql function.
        from cnxpublishing.utils import join_ident_hash
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
                    u"shortId": u"1du9jtE3@1.1",
                    u"title": u"Book of Infinity",
                    u'slug': None,
                    u"contents": [
                        {u"id": u"subcol",
                         u"shortId": u"subcol",
                         u"title": use_cases.REVISED_BOOK[0].metadata['title'],
                         u'slug': None,
                         u"contents": [
                             {u"id": unicode(document_ident_hash),
                              u"shortId": u"EeLmMXO1@1",
                              u'slug': None,
                              u"title": use_cases.REVISED_BOOK[0].get_title_for_node(document)}]}]}
                cursor.execute("""\
SELECT tree_to_json(uuid::text, module_version( major_version, minor_version), FALSE)
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
        api_key_headers = self.gen_api_key_headers('some-trust')

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
        api_key_headers = self.gen_api_key_headers('some-trust')

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
        api_key_headers = self.gen_api_key_headers('some-trust')

        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        publication_id = resp.json['publication']

        # Check that the epub file is stored in the database
        with open(epub_filepath, 'r') as f:
            epub_content = f.read()
        with self.db_connect() as db_conn:
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
        api_key_headers = self.gen_api_key_headers('some-trust')

        # Give publisher permission to publish
        from cnxpublishing.utils import split_ident_hash
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

        # Assume moderation acceptance.
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("""\
UPDATE users SET (is_moderated) = ('t')
WHERE username = %s""", (publisher,))

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


class BakeContentTestCase(BaseFunctionalViewTestCase):
    def app_post_collate_content(self, ident_hash, headers=None, status=None,
                                 **kwargs):
        path = '/contents/{}/collate-content'.format(ident_hash)
        return self.app.post(path, headers=headers, status=status, **kwargs)

    def app_post_bake(self, ident_hash, headers=None, status=None,
                      **kwargs):
        path = '/contents/{}/baked'.format(ident_hash)
        return self.app.post(path, headers=headers, status=status, **kwargs)

    @db_connect
    def test_not_book(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()
        api_key_headers = self.gen_api_key_headers('some-trust')
        self.app_post_bake(binder[0][0].ident_hash,
                           headers=api_key_headers,
                           status=400)

    def test_not_found(self):
        random_ident_hash = '{}@1'.format(uuid.uuid4())
        api_key_headers = self.gen_api_key_headers('some-trust')
        self.app_post_bake(random_ident_hash,
                           headers=api_key_headers,
                           status=404)

    def make_one(self, binder, content):
        """Given a binder and content, make a composite document for that
        binder. Returns publisher, message and CompositeDocument instance.

        """
        # Build some new metadata for the composite document.
        metadata = [x.metadata.copy()
                    for x in cnxepub.flatten_to_documents(binder)][0]
        del metadata['cnx-archive-uri']
        del metadata['version']
        metadata['title'] = "Made up of other things"

        publisher = [p['id'] for p in metadata['publishers']][0]
        message = "Composite addition"

        # Add some fake collation objects to the book.
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)
        return publisher, message, composite_doc

    @db_connect
    def test(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()
        api_key_headers = self.gen_api_key_headers('some-trust')

        # FIXME use collate with real ruleset when it is available

        # Add some fake collation objects to the book.
        content = '<body><p>compösite</p></body>'
        publisher, message, composite_doc = self.make_one(binder, content)
        composite_section = cnxepub.TranslucentBinder(
            nodes=[composite_doc],
            metadata={'title': "Other things"})
        collated_doc_content = '<body><p>cöllated</p></body>'

        def _collate(binder_model, ruleset=None, includes=None):
            binder_model[0][0].content = collated_doc_content
            binder_model.append(composite_section)
            return binder_model

        cursor.execute('LISTEN post_publication')
        cursor.connection.commit()

        self.app_post_bake(binder.ident_hash,
                           headers=api_key_headers)

        cursor.connection.commit()
        cursor.connection.poll()
        # FIXME https://github.com/Connexions/cnx-publishing/issues/219
        # self.assertEqual(1, len(cursor.connection.notifies))

        with mock.patch('cnxpublishing.bake.collate_models') as mock_collate:
            mock_collate.side_effect = _collate
            fake_recipe_id = 1
            bake(binder, fake_recipe_id, publisher, message, cursor=cursor)
            self.assertEqual(1, mock_collate.call_count)

        # Ensure the tree as been stamped.
        cursor.execute("SELECT tree_to_json(%s, %s, TRUE)::json;",
                       (binder.id, binder.metadata['version'],))
        collated_tree = cursor.fetchone()[0]

        self.assertIn(composite_doc.ident_hash,
                      cnxepub.flatten_tree_to_ident_hashes(collated_tree))

    @db_connect
    def test_rerun(self, cursor):
        api_key_headers = self.gen_api_key_headers('some-trust')
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()

        content = '<body><p class="para">composite</p></body>'
        publisher, message, composite_doc = self.make_one(binder, content)
        collated_doc_content = '<body><p>collated</p></body>'

        def _collate(binder_model, ruleset=None, includes=None):
            binder_model[0][0].content = collated_doc_content
            binder_model.append(composite_doc)
            return binder_model

        cursor.execute('LISTEN post_publication')
        cursor.connection.commit()

        self.app_post_bake(binder.ident_hash,
                           headers=api_key_headers)
        # Run it again to mimic a rerun behavior.
        self.app_post_bake(binder.ident_hash,
                           headers=api_key_headers)

        cursor.connection.commit()
        cursor.connection.poll()
        cursor.connection.poll()
        # FIXME https://github.com/Connexions/cnx-publishing/issues/219
        # self.assertEqual(2, len(cursor.connection.notifies))

    @db_connect
    def test_missing_version(self, cursor):
        api_key_headers = self.gen_api_key_headers('some-trust')
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()

        content = '<body><p class="para">composite</p></body>'
        publisher, message, composite_doc = self.make_one(binder, content)

        ident_hash = binder.ident_hash
        ident_hash = ident_hash.split('@')[0]

        resp = self.app_post_bake(ident_hash, headers=api_key_headers,
                                  expect_errors=True)
        self.assertEquals(resp.status_int, 400)
        self.assertIn('must specify the version', resp.body)

    @db_connect
    def test_bad_ident_hash(self, cursor):
        api_key_headers = self.gen_api_key_headers('some-trust')
        ident_hash = 'f00ba7@1.1'

        resp = self.app_post_bake(ident_hash, headers=api_key_headers,
                                  expect_errors=True)
        self.assertEquals(resp.status_int, 404)
