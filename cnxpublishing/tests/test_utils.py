# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2015, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest

from cnxpublishing.utils import amend_tree_with_slugs


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


def test_amend_tree_with_slugs():
    # This tree struct only contains the required parts,
    # where id, shortid, etc. are ignored.
    tree = {
        'title': 'Book of Origin',
        'contents': [
            {'title': '<span class="os-text">Preface</span>'},
            {'title': (
                '<span class="os-number">1</span>'
                '<span class="os-divider"> </span>'
                '<span class="os-text">Chapter One</span>'),
             'contents': [
                 {'title': (
                     '<span class="os-number">1.1</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Apple</span>')},
                 {'title': (
                     '<span class="os-number">1.2</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Banana</span>')},
                 {'title': (
                     '<span class="os-text">'
                     'Problems &amp; Exercises'
                     '</span>')}],
             },
            {'title': (
                '<span class="os-number">2</span>'
                '<span class="os-divider"> </span>'
                '<span class="os-text">Chapter One</span>'),
             'contents': [
                 {'title': (
                     '<span class="os-number">1.1</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Apple</span>')},
                 {'title': (
                     '<span class="os-number">1.2</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Banana</span>')},
                 {'title': (
                     '<span class="os-text">'
                     'Key Terms'
                     '</span>')}],
             },
            {'title': '<span class="os-text">Index</span>'},
        ],
    }

    # Call the target
    amend_tree_with_slugs(tree)

    expected_tree = {
        'title': 'Book of Origin',
        'slug': 'book-of-origin',
        'contents': [
            {'slug': 'preface',
             'title': '<span class="os-text">Preface</span>'},
            {'title': (
                '<span class="os-number">1</span>'
                '<span class="os-divider"> </span>'
                '<span class="os-text">Chapter One</span>'
            ),
                'slug': '1-chapter-one',
                'contents': [
                {'slug': '1-1-apple',
                 'title': (
                     '<span class="os-number">1.1</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Apple</span>'
                 )},
                {'slug': '1-2-banana',
                 'title': (
                     '<span class="os-number">1.2</span>'
                     '<span class="os-divider"> </span>'
                     '<span class="os-text">Banana</span>'
                 )},
                {'slug': '1-problems-exercises',
                 'title': (
                     '<span class="os-text">'
                     'Problems &amp; Exercises'
                     '</span>'
                 )}]
            },
            {'title': (
                '<span class="os-number">2</span>'
                '<span class="os-divider"> </span>'
                '<span class="os-text">Chapter One</span>'),
             'slug': '2-chapter-one',
             'contents': [
                 {'slug': '1-1-apple',
                  'title': (
                      '<span class="os-number">1.1</span>'
                      '<span class="os-divider"> </span>'
                      '<span class="os-text">Apple</span>'
                  )},
                 {'slug': '1-2-banana',
                  'title': (
                      '<span class="os-number">1.2</span>'
                      '<span class="os-divider"> </span>'
                      '<span class="os-text">Banana</span>'
                  )},
                 {'slug': '2-key-terms',
                  'title': '<span class="os-text">Key Terms</span>'}],
             },
            {'slug': 'index',
             'title': '<span class="os-text">Index</span>'},
        ],
    }

    assert tree == expected_tree
