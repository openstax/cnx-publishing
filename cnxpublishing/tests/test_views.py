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
import zipfile
from copy import deepcopy

import psycopg2
import cnxepub
from webob import Request
from webtest import TestApp
from pyramid import testing
from pyramid import httpexceptions

from . import use_cases
from .testing import (
    integration_test_settings,
    db_connection_factory,
    )


here = os.path.abspath(os.path.dirname(__file__))
TEST_DATA_DIR = os.path.join(here, 'data')


class PublishViewTestCase(unittest.TestCase):

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


class FunctionalViewTestCase(unittest.TestCase, EPUBMixInTestCase):
    """Request/response client interaction"""

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
        from cnxarchive.database import initdb
        initdb({'db-connection-string': self.db_conn_str})
        from ..db import initdb
        initdb(self.db_conn_str)

    def tearDown(self):
        with psycopg2.connect(self.db_conn_str) as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()

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

    def app_post_publication(self, epub_filepath, headers=[]):
        upload_files = [('epub', epub_filepath,)]
        resp = self.app.post('/publications', upload_files=upload_files,
                             headers=headers)
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

    # ######### #
    #   Tests   #
    # ######### #
    # - the contents of the publication contents are of lesser
    #   important to that of the process itself.
    # - the tests are firstly divided into trusted and untrusted cases.
    # - the tests are secondly divided into new, existing and mixed
    #   document/binder content publications.

    def test_new_trusted_to_publication(self):
        """\
        Publish *new* documents from an *trusted* application.
        This includes application and user interactions with publishing.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. Verify documents are in the archive. [HACKED]

        """
        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.BOOK, publisher,
                                       u'públishing this book')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Done/Success')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        self._check_published_to_archive(use_cases.BOOK)

    def test_trusted_revision(self):
        """\
        Publish document revisions from a *trusted* application.
        This includes application and user interactions with
        the revision publishing process.

        *. After each step, check the state of the publication.

        1. Submit an EPUB containing a book of documents.

        2. Verify documents are in the archive. [HACKED]

        """
        # Insert the BOOK use-case in order to make a revision of it.
        self._setup_to_archive(use_cases.BOOK)

        publisher = u'ream'
        epub_filepath = self.make_epub(use_cases.REVISED_BOOK, publisher,
                                       u'públishing a revision')
        api_key = self.api_keys_by_uid['some-trust']
        api_key_headers = [('x-api-key', api_key,)]

        # 1. --
        resp = self.app_post_publication(epub_filepath,
                                         headers=api_key_headers)
        self.assertEqual(resp.json['state'], 'Done/Success')
        publication_id = resp.json['publication']

        # *. --
        self.app_check_state(publication_id, 'Done/Success',
                             headers=api_key_headers)

        # 4. (manual)
        self._check_published_to_archive(use_cases.REVISED_BOOK)

    def test_new_untrusted_to_publication(self):
        """\
        Publish *new* documents from an *untrusted* application.
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
SELECT user_id, acceptance
FROM publications_license_acceptance
GROUP BY user_id, acceptance
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
SELECT user_id, acceptance
FROM publications_role_acceptance
GROUP BY user_id, acceptance
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

    def test_new_trusted_to_publication_w_exceptions(self):
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
