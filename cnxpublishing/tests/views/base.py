# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import tempfile
import shutil
import unittest
import zipfile

import cnxepub
from webtest import TestApp
from pyramid import testing

from ..testing import (
    integration_test_settings,
    db_connection_factory,
    init_db,
)


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
    def api_keys_by_name(self):
        """Mapping of uid to api key."""
        attr_name = '_api_keys'
        api_keys = getattr(self, attr_name, None)

        def get_info():
            from cnxpublishing.authnz import lookup_api_key_info
            with self.db_connect() as db_conn:
                with db_conn.cursor():
                    return lookup_api_key_info()

        if api_keys is None:
            self.addCleanup(delattr, self, attr_name)
            api_keys = {}
            for key, value in get_info().items():
                api_keys[value['name']] = key
            setattr(self, attr_name, api_keys)
        return api_keys

    def gen_api_key_headers(self, name):
        """Generate authentication headers for the given user."""
        api_key = self.api_keys_by_name[name]
        api_key_header = [('x-api-key', api_key,)]
        return api_key_header

    def set_up_api_keys(self):
        # key_info_keys = ['key', 'name', 'groups']
        key_info = (
            # [key, name, groups]
            ['4e8', 'no-trust', None],
            ['b07', 'some-trust', ['g:trusted-publishers']],
            ['dev', 'developer', ['g:trusted-publishers']],
        )
        # key_info = [dict(zip(key_info_keys, value)) for value in key_info]
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.executemany("INSERT INTO api_keys (key, name, groups) "
                                   "VALUES (%s, %s, %s)", key_info)
        self.addCleanup(self.tear_down_api_keys)

    def tear_down_api_keys(self):
        # Invalidate the api_key lookup cache
        from cnxpublishing import authnz
        authnz.cache_manager.invalidate(authnz.lookup_api_key_info)

    @classmethod
    def setUpClass(cls):
        cls.settings = integration_test_settings()
        from cnxpublishing.config import CONNECTION_STRING
        cls.db_conn_str = cls.settings[CONNECTION_STRING]
        cls.db_connect = staticmethod(db_connection_factory())
        cls._app = cls.make_app(cls.settings)

    @staticmethod
    def make_app(settings):
        from cnxpublishing.main import make_wsgi_app
        app = make_wsgi_app({}, **settings)
        return app

    @property
    def app(self):
        return TestApp(self._app)

    def setUp(self):
        EPUBMixInTestCase.setUp(self)
        testing.setUp(settings=self.settings)
        init_db(self.db_conn_str)

        # Assign API keys for testing
        self.set_up_api_keys()

    def tearDown(self):
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("DROP SCHEMA public CASCADE")
                cursor.execute("CREATE SCHEMA public")
        testing.tearDown()
