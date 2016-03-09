# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest


class ParseArchiveUriTestCase(unittest.TestCase):

    @property
    def target(self):
        from ..utils import parse_archive_uri
        return parse_archive_uri

    def test(self):
        faux_ident_hash = 'abc123@4'
        ident_hash = self.target('/contents/{}'.format(faux_ident_hash))
        self.assertEqual(ident_hash, faux_ident_hash)


class ParseUserUriTestCase(unittest.TestCase):

    @property
    def target(self):
        from ..utils import parse_user_uri
        return parse_user_uri

    def test_success(self):
        uid = 'typo'
        user = self.target(uid, type_='cnx-id')
        self.assertEqual(user, uid)

    def test_invalid_type(self):
        uid = 'typo'
        invalid_type = 'rice-id'
        with self.assertRaises(ValueError) as caught_exc:
            self.target(uid, type_=invalid_type)
        self.assertEqual(
            caught_exc.exception.args[0],
            "Can't parse a user uri of type '{}'.".format(invalid_type))
