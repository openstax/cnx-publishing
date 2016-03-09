# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###

import doctest
import os
import subprocess
import time

from ..db import upsert_acl
from .testing import config_uri
from .views.base import BaseFunctionalViewTestCase


class DocTestTestCase(BaseFunctionalViewTestCase):
    """Run all the examples"""

    def test_readme(self):
        # Start server
        if os.path.exists('./bin/pserve'):
            pserve = './bin/pserve'
        else:
            pserve = 'pserve'
        server = subprocess.Popen([pserve, config_uri()])
        time.sleep(5)

        self.addCleanup(server.terminate)

        # In order for the uuids to always be the same in the examples in
        # README, we need to add cnx-archive-uri in tests/use_cases.py and
        # assign initial acl and acceptance (manually insert data into
        # document_controls, document_acl and licenses).
        uuids = ['07509e07-3732-45d9-a102-dd9a4dad5456',
                 'de73751b-7a14-4e59-acd9-ba66478e4710']
        permissions = [('ream', 'publish')]
        with self.db_connect() as db_conn:
            with db_conn.cursor() as cursor:
                for uuid_ in uuids:
                    cursor.execute(
                        'INSERT INTO document_controls (uuid) VALUES (%s)',
                        (uuid_,))
                    upsert_acl(cursor, uuid_, permissions)
                    cursor.execute("""
UPDATE document_controls AS dc
SET licenseid = l.licenseid FROM licenses AS l WHERE url = %s and is_valid_for_publication = 't'
RETURNING dc.licenseid""", ('http://creativecommons.org/licenses/by/4.0/',))

        results = doctest.testfile(
            '../../README.rst',
            optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)

        if results.failed:
            self.fail('DocTest failed: {}'.format(results))
