# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest


class UtilsTests(unittest.TestCase):

    def test_parse_archive_uri(self):
        from ..utils import parse_archive_uri

        faux_ident_hash = 'abc123@4'
        ident_hash = parse_archive_uri('/contents/{}'.format(faux_ident_hash))
        self.assertEqual(ident_hash, faux_ident_hash)

    def test_parse_user_uri(self):
        from ..utils import parse_user_uri

        uid = 'typo'
        user = parse_user_uri(uid, type_='cnx-id')
        self.assertEqual(user, uid)

        invalid_type = 'rice-id'
        with self.assertRaises(ValueError) as caught_exc:
            parse_user_uri(uid, type_=invalid_type)
        self.assertEqual(
            caught_exc.exception.args[0],
            "Can't parse a user uri of type '{}'.".format(invalid_type))
