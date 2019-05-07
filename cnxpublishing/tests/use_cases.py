# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import hashlib
import json
from copy import deepcopy
from psycopg2 import Binary

import cnxepub

from ..utils import join_ident_hash, split_ident_hash


here = os.path.abspath(os.path.dirname(__file__))
TEST_DATA_DIR = os.path.join(here, 'data')
RESOURCE_ONE_FILENAME = "e3d625fe.png"
RESOURCE_ONE_FILEPATH = os.path.join(TEST_DATA_DIR, RESOURCE_ONE_FILENAME)
RULESET_ONE_FILENAME = "ruleset.css"
RULESET_ONE_FILEPATH = os.path.join(TEST_DATA_DIR, RULESET_ONE_FILENAME)
RECIPE_ONE_FILENAME = "recipe_1.css"
RECIPE_ONE_FILEPATH = os.path.join(TEST_DATA_DIR, RECIPE_ONE_FILENAME)
RECIPE_TWO_FILENAME = "recipe_2.css"
RECIPE_TWO_FILEPATH = os.path.join(TEST_DATA_DIR, RECIPE_TWO_FILENAME)


def _read_file(filepath, mode='rb'):
    with open(filepath, mode) as fb:
        return io.BytesIO(fb.read())


# ############# #
#   Use cases   #
# ############# #


BOOK = cnxepub.Binder(
    id='94f4d0f5@draft',
    metadata={
        u'title': u'Book of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': [
            u'Mathematics and Statistics',
            u'Science and Technology',
        ],
        u'authors': [
            {u'id': u'marknewlyn', u'name': u'Mark Horner',
             u'type': u'cnx-id'},
            {u'id': u'charrose', u'name': u'Charmaine St. Rose',
             u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'}],
        u'editors': [
            {u'id': u'impicky', u'name': u'I. M. Picky',
             u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'},
            {u'id': u'rings', u'name': u'Rings', u'type': u'cnx-id'}],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None,
    },
    nodes=[
        cnxepub.TranslucentBinder(
            metadata={u'title': u'Part One'},
            nodes=[
                cnxepub.TranslucentBinder(
                    metadata={u'title': u'Chapter One'},
                    title_overrides=['Document One'],
                    nodes=[
                        cnxepub.Document(
                            id=u'2cf4d7d3@draft',
                            data=u'<body><p class="para">If you finish the book, there will be cake.</p><img src="../resources/{}" /></body>'.format(RESOURCE_ONE_FILENAME),
                            resources=[
                                cnxepub.Resource(RESOURCE_ONE_FILENAME,
                                                 _read_file(RESOURCE_ONE_FILEPATH, 'rb'),
                                                 'image/png',
                                                 filename=RESOURCE_ONE_FILENAME)],
                            metadata={
                                u'title': u'Document One of Infinity',
                                u'created': u'2013/03/19 15:01:16 -0500',
                                u'revised': u'2013/03/19 15:01:16 -0500',
                                u'keywords': [u'South Africa'],
                                u'subjects': [
                                    u'Mathematics and Statistics',
                                ],
                                u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
                                u'language': u'en',
                                u'license_text': u'CC-By 4.0',
                                u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
                                u'authors': [{u'id': u'marknewlyn',
                                              u'name': u'Mark Horner',
                                              u'type': u'cnx-id'},
                                             {u'id': u'charrose',
                                              u'name': u'Charmaine St. Rose',
                                              u'type': u'cnx-id'},
                                             {u'id': u'sarblyth',
                                              u'name': u'Sarah Blyth',
                                              u'type': u'cnx-id'}],
                                u'copyright_holders': [
                                    {u'id': u'ream',
                                     u'name': u'Ream',
                                     u'type': u'cnx-id'}],
                                u'editors': [{u'id': u'impicky',
                                              u'name': u'I. M. Picky',
                                              u'type': u'cnx-id'}],
                                u'illustrators': [{u'id': u'frahablar',
                                                   u'name': u'Francis Hablar',
                                                   u'type': u'cnx-id'}],
                                u'publishers': [{u'id': u'ream',
                                                 u'name': u'Ream',
                                                 u'type': u'cnx-id'},
                                                {u'id': u'rings',
                                                 u'name': u'Rings',
                                                 u'type': u'cnx-id'}],
                                u'translators': [{u'id': u'frahablar',
                                                  u'name': u'Francis Hablar',
                                                  u'type': u'cnx-id'}],
                                u'print_style': u'*print style*',
                            }

                        ),
                    ]),
            ]),
    ])

# EXAMPLE_BOOK is used in README
EXAMPLE_BOOK = deepcopy(BOOK)
# Set the id of the book
EXAMPLE_BOOK.id = '07509e07-3732-45d9-a102-dd9a4dad5456@draft'
# Set the id of the page
EXAMPLE_BOOK[0][0][0].id = 'de73751b-7a14-4e59-acd9-ba66478e4710'
# Make sure the id stay the same when it's published
EXAMPLE_BOOK.metadata['cnx-archive-uri'] = 'http://archive.cnx.org/content/07509e07-3732-45d9-a102-dd9a4dad5456'
EXAMPLE_BOOK[0][0][0].metadata['cnx-archive-uri'] = 'http://archive.cnx.org/content/de73751b-7a14-4e59-acd9-ba66478e4710'

REVISED_BOOK = deepcopy(BOOK)
# Take out a layer of the structure to shuffle the tree.
# This replaces the a translucent binder with it's single document sibling.
REVISED_BOOK[0][0] = REVISED_BOOK[0][0][0]
# Assign identifiers to the persistent models.
REVISED_BOOK.id = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee@draft'
REVISED_BOOK.metadata['cnx-archive-uri'] = 'http://archive.cnx.org/contents/d5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
REVISED_BOOK[0][0].id = '11e2e631-73b5-44da-acae-e97defd9673b@draft'
REVISED_BOOK[0][0].metadata['cnx-archive-uri'] = 'http://archive.cnx.org/contents/11e2e631-73b5-44da-acae-e97defd9673b'
# Retitle the translucent binder.
REVISED_BOOK[0].metadata['title'] = u"Stifled with Good Inténsions"
REVISED_BOOK[0].set_title_for_node(REVISED_BOOK[0][0], u"Infinity Plus")


SPAM = cnxepub.Binder(
    id='94f4d0f5@draft',
    metadata={
        u'title': u'Eat more spam',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': [
            u'Mathematics and Statistics',
            u'Science and Technology',
        ],
        u'authors': [
            {u'id': u'happy', u'name': u'Happy Go Lucky',
             u'type': u'cnx-id'}],
        u'copyright_holders': [],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [
            {u'id': u'happy', u'name': u'Happy Go Lucky',
             u'type': u'cnx-id'}],
        u'translators': [],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None,
    },
    nodes=[
        cnxepub.Document(
            id=u'2cf4d7d3@draft',
            data=u'<body><p class="para">Yummy Yummy SPAM!!!</p></body>',
            resources=[],
            metadata={
                u'title': u'Eat up!',
                u'created': u'2013/03/19 15:01:16 -0500',
                u'revised': u'2013/03/19 15:01:16 -0500',
                u'keywords': [],
                u'subjects': [],
                u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>spam</span>",
                u'language': u'en',
                u'license_text': u'CC-By 4.0',
                u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
                u'authors': [{u'id': u'happy',
                              u'name': u'Happy Go Lucky',
                              u'type': u'cnx-id'}],
                u'copyright_holders': [],
                u'editors': [],
                u'illustrators': [],
                u'publishers': [{u'id': u'happy',
                                 u'name': u'Happy Go Lucky',
                                 u'type': u'cnx-id'}],
                u'translators': [],
                u'print_style': u'*print style*',
            },
        ),
    ])


PAGE_ONE = cnxepub.Document(
    id=u'2cf4d7d3@draft',
    data=u'<body><p class="para">If you finish the book, there will be cake.</p></body>',
    metadata={
        u'title': u'Document One of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [{u'id': u'marknewlyn',
                      u'name': u'Mark Horner',
                      u'type': u'cnx-id'},
                     {u'id': u'charrose',
                      u'name': u'Charmaine St. Rose',
                      u'type': u'cnx-id'},
                     {u'id': u'sarblyth',
                      u'name': u'Sarah Blyth',
                      u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}],
        u'editors': [{u'id': u'impicky',
                      u'name': u'I. M. Picky',
                      u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [{u'id': u'ream',
                         u'name': u'Ream',
                         u'type': u'cnx-id'},
                        {u'id': u'rings',
                         u'name': u'Rings',
                         u'type': u'cnx-id'}],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'print_style': None,
    },

)

PAGE_TWO = cnxepub.Document(
    id=u'c24fe396@draft',
    data=u'<body><p class="para">If you finish the book, there will be cake.</p></body>',
    metadata={
        u'title': u'Document Two of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [{u'id': u'marknewlyn',
                      u'name': u'Mark Horner',
                      u'type': u'cnx-id'},
                     ],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}],
        u'editors': [{u'id': u'impicky',
                      u'name': u'I. M. Picky',
                      u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [{u'id': u'ream',
                         u'name': u'Ream',
                         u'type': u'cnx-id'},
                        {u'id': u'rings',
                         u'name': u'Rings',
                         u'type': u'cnx-id'}],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'print_style': None, },

)

PAGE_THREE = cnxepub.Document(
    id=u'e12b72ac@draft',
    data=u'<body><p class="para">If you finish the book, there will be cake.</p></body>',
    metadata={
        u'title': u'Document Three of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [{u'id': u'charrose',
                      u'name': u'Charmaine St. Rose',
                      u'type': u'cnx-id'},
                     {u'id': u'sarblyth',
                      u'name': u'Sarah Blyth',
                      u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}],
        u'editors': [{u'id': u'impicky',
                      u'name': u'I. M. Picky',
                      u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [{u'id': u'ream',
                         u'name': u'Ream',
                         u'type': u'cnx-id'},
                        ],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'print_style': None, },

)

PAGE_FOUR = cnxepub.Document(
    id=u'deadbeef@draft',
    data=u'<body><p class="para">If you finish the böök, there will be cake.</p></body>',
    metadata={
        u'title': u'Document Four of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [{u'id': u'butcher',
                      u'name': u'James Doakes',
                      u'type': u'cnx-id'},
                     ],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [{u'id': u'ream',
                         u'name': u'Ream',
                         u'type': u'cnx-id'},
                        {u'id': u'rings',
                         u'name': u'Rings',
                         u'type': u'cnx-id'}],
        u'translators': [],
        u'print_style': None,
    }
)

PAGE_FIVE = cnxepub.Document(
    id=u'b3627ba5@draft',
    data=u'<body><p class="para">Download big file <a href="../resources/big-file.txt">here</a></p></body>',
    resources=[
        cnxepub.Resource('big-file.txt',
                         # a 2 MB file
                         io.BytesIO('a ' * 1024 * 1024),
                         'text/plain',
                         filename='big-file.txt'),
    ],
    metadata={
        u'title': u'Document Five',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Technology'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>descriptive text</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [{u'id': u'charrose',
                      u'name': u'Charmaine St. Rose',
                      u'type': u'cnx-id'},
                     ],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [{u'id': u'ream',
                         u'name': u'Ream',
                         u'type': u'cnx-id'},
                        {u'id': u'charrose',
                         u'name': u'Charmaine St. Rose',
                         u'type': u'cnx-id'}],
        u'translators': [],
        u'print_style': None,
    }
)

EXERCISES_PAGE = cnxepub.Document(
    id=u'01234567@draft',
    data=u"""
<body>
    <p class="para">
        <section>
            <div data-type="exercise" class="os-exercise">
                <section>
                    <div data-type="problem">
                        <p><a class="os-embed" href="#ost/api/ex/k12phys-ch04-ex001">[link]</a></p>
                    </div>
                </section>
            </div>
        </section>
        <section>
            <div data-type="exercise" class="os-exercise">
                <section>
                    <div data-type="problem">
                        <p><a class="os-embed" href="#ost/api/ex/k12phys-ch04-ex002">[link]</a></p>
                    </div>
                </section>
            </div>
        </section>
        <section>
            <div data-type="exercise" class="os-exercise">
                <section>
                    <div data-type="problem">
                        <p><a class="os-embed" href="#exercise/some_nickname">[link]</a></p>
                    </div>
                </section>
            </div>
        </section>
        <section>
            <div data-type="exercise" class="os-exercise grasp-check">
                <section>
                    <div data-type="problem">
                        <p><a class="os-embed" href="#exercise/Another Nickname">[link]</a></p>
                    </div>
                </section>
            </div>
        </section>
    </p>
</body>
    """,
    metadata={
        u'title': u'Exercises Page',
        u'created': u'2018/07/26 17:52:00 -0500',
        u'revised': u'2018/07/26 17:52:00 -0500',
        u'keywords': [u'Exercises'],
        u'subjects': [u'Physics'],
        u'summary': u"<span xmlns='http://www.w3.org/1999/xhtml'>A bunch of exercises</span>",
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'authors': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'translators': [],
        u'print_style': None,
    }
)

COMPLEX_BOOK_ONE = cnxepub.Binder(
    id='94f4d0f5@draft',
    resources=[
        cnxepub.Resource(RULESET_ONE_FILENAME,
                         _read_file(RULESET_ONE_FILEPATH, 'rb'),
                         'text/css',
                         filename=RULESET_ONE_FILENAME)],
    metadata={
        u'title': u'Book of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': [u'Science and Mathematics'],
        u'authors': [
            {u'id': u'marknewlyn', u'name': u'Mark Horner',
             u'type': u'cnx-id'},
            {u'id': u'charrose', u'name': u'Charmaine St. Rose',
             u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'}],
        u'editors': [
            {u'id': u'impicky', u'name': u'I. M. Picky',
             u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'},
            {u'id': u'rings', u'name': u'Rings', u'type': u'cnx-id'}],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None,
    },
    nodes=[
        cnxepub.TranslucentBinder(
            metadata={u'title': u'Part One'},
            title_overrides=['Document One', 'Document Two'],
            nodes=[PAGE_ONE, PAGE_TWO],
        ),
        cnxepub.TranslucentBinder(
            metadata={u'title': u'Part Two'},
            title_overrides=['Document Three', 'Document Four'],
            nodes=[PAGE_THREE, PAGE_FOUR],
        ),
    ])

COMPLEX_BOOK_TWO = cnxepub.Binder(
    id='94f4d0f5@draft',
    metadata={
        u'title': u'Book of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': [u'Science and Mathematics'],
        u'authors': [
            {u'id': u'marknewlyn', u'name': u'Mark Horner',
             u'type': u'cnx-id'},
            {u'id': u'charrose', u'name': u'Charmaine St. Rose',
             u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'}],
        u'editors': [
            {u'id': u'impicky', u'name': u'I. M. Picky',
             u'type': u'cnx-id'}],
        u'illustrators': [{u'id': u'frahablar',
                           u'name': u'Francis Hablar',
                           u'type': u'cnx-id'}],
        u'publishers': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'},
            {u'id': u'rings', u'name': u'Rings', u'type': u'cnx-id'}],
        u'translators': [{u'id': u'frahablar',
                          u'name': u'Francis Hablar',
                          u'type': u'cnx-id'}],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None
    },
    nodes=[
        cnxepub.TranslucentBinder(
            metadata={u'title': u'Part One'},
            title_overrides=['Document One', 'Document Two'],
            nodes=[PAGE_TWO, PAGE_THREE],
        ),
        cnxepub.TranslucentBinder(
            metadata={u'title': u'Part Two'},
            title_overrides=['Document Three'],
            nodes=[PAGE_ONE],
        ),
    ])

COMPLEX_BOOK_THREE = cnxepub.Binder(
    id='defc01ef@draft',
    metadata={
        u'title': u'Book of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': [],
        u'authors': [
            {u'id': u'charrose', u'name': u'Charmaine St. Rose',
             u'type': u'cnx-id'}],
        u'copyright_holders': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'}],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [
            {u'id': u'ream', u'name': u'Ream', u'type': u'cnx-id'}],
        u'translators': [],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None
    },
    title_overrides=['D One', 'D Two'],
    nodes=[PAGE_TWO, PAGE_FOUR],
)

EXERCISES_BOOK = cnxepub.Binder(
    id='89abcdef@draft',
    metadata={
        u'title': u'Book of Exercises',
        u'created': u'2018/07/26 17:52:00 -0500',
        u'revised': u'2018/07/26 17:52:00 -0500',
        u'keywords': ['Physics'],
        u'language': u'en',
        u'license_text': u'CC-By 4.0',
        u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
        u'subjects': ['Biology'],
        u'authors': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'copyright_holders': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'editors': [],
        u'illustrators': [],
        u'publishers': [
            {u'id': u'ream',
             u'name': u'Ream',
             u'type': u'cnx-id'}
        ],
        u'translators': [],
        u'summary': "<span xmlns='http://www.w3.org/1999/xhtml'>Book summary</span>",
        u'print_style': None
    },
    title_overrides=['E Only'],
    nodes=[EXERCISES_PAGE],
)


# ################### #
#   Use case checks   #
# ################### #
# Used to verify a use case within the archive database.
# These use a naming convension check_<use-case-name>_in_archive.
# All checker callables should have positional arguments for
# the test case (to allow for unittest.TestCase assertion methods)
# and a database cursor object.
#
#   def check_<use-case-name>_in_archive(test_case, cursor):
#       ...

def check_BOOK_in_archive(test_case, cursor):
    """This checker assumes that the only content in the database
    is the content within this use case.
    """
    cursor.execute("SELECT name FROM modules ORDER BY name ASC")
    names = [row[0] for row in cursor.fetchall()]
    test_case.assertEqual(
        ['Book of Infinity', 'Document One of Infinity'],
        names)

    cursor.execute("""\
SELECT portal_type, ident_hash(uuid,major_version,minor_version)
FROM modules""")
    items = dict(cursor.fetchall())
    document_ident_hash = items['Module']
    binder_ident_hash = items['Collection']

    cursor.execute("""\
SELECT portal_type,
       short_ident_hash(uuid, major_version, minor_version)
FROM modules""")
    items = dict(cursor.fetchall())
    document_short_id = items['Module']
    binder_short_id = items['Collection']

    expected_tree = {
        "id": binder_ident_hash,
        "shortId": binder_short_id,
        "title": "Book of Infinity",
        'slug': None,
        "contents": [
            {"id": "subcol",
             "shortId": "subcol",
             "title": "Part One",
             'slug': None,
             "contents": [
                 {"id": "subcol",
                  "shortId": "subcol",
                  "title": "Chapter One",
                  'slug': None,
                  "contents": [
                      {"id": document_ident_hash,
                       "shortId": document_short_id,
                       'slug': None,
                       "title": "Document One"}]}]}]}
    cursor.execute("""\
 SELECT tree_to_json(uuid::text, module_version(major_version, minor_version), FALSE)
FROM modules
WHERE portal_type = 'Collection'""")
    tree = json.loads(cursor.fetchone()[0])
    test_case.assertEqual(expected_tree, tree)

    hashlib.new(
        cnxepub.RESOURCE_HASH_TYPE,
        _read_file(RESOURCE_ONE_FILEPATH).read()
    ).hexdigest()
    # FIXME Remove and change assertion after cnx-archive switches to
    # ``cnxepub.RESOURCE_HASH_TYPE`` as hash. Use ``resource_hash`` in the
    # check instead of ``file_md5``.
    file_md5 = hashlib.new('md5',
                           _read_file(RESOURCE_ONE_FILEPATH).read()) \
        .hexdigest()
    cursor.execute("""\
SELECT f.file, f.media_type,
        ident_hash(m.uuid,m.major_version,m.minor_version)
FROM files as f natural join module_files as mf, latest_modules as m
WHERE
  mf.module_ident = m.module_ident
  AND
  f.md5 = %s""", (file_md5,))
    file, mime_type, ident_hash = cursor.fetchone()
    test_case.assertEqual(mime_type, 'image/png')
    test_case.assertEqual(ident_hash, document_ident_hash)
    test_case.assertEqual(file[:], _read_file(RESOURCE_ONE_FILEPATH).read())


def check_REVISED_BOOK_in_archive(test_case, cursor):
    """This checker assumes that the only content in the database
    is the content within the BOOK and REVISED_BOOK use cases.
    """
    binder = REVISED_BOOK
    document = REVISED_BOOK[0][0]

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
            [1, 1, '1.1'],  # BOOK
            [2, 1, '1.2'],  # REVISED_BOOK
        ],
        key_sep.join([document_uuid, 'm10000']): [
            [1, None, '1.1'],
            [2, None, '1.2'],
        ],
    }
    test_case.assertEqual(expected_records, records)

    # Check the tree...
    # This also proves that the REVISED_BOOK is in latest_modules
    # by virtual of using the tree_to_json function.
    binder_ident_hash = join_ident_hash(split_ident_hash(binder.id)[0],
                                        (2, 1,))
    document_ident_hash = join_ident_hash(split_ident_hash(document.id)[0],
                                          (2, None,))
    expected_tree = {
        u"id": unicode(binder_ident_hash),
        u"shortId": u"1du9jtE3@2.1",
        u"title": u"Book of Infinity",
        u'slug': None,
        u"contents": [
            {u"id": u"subcol",
             u"shortId": u"subcol",
             u"title": REVISED_BOOK[0].metadata['title'],
             u'slug': None,
             u"contents": [
                 {u"id": unicode(document_ident_hash),
                  u"shortId": u"EeLmMXO1@2",
                  u'slug': None,
                  u"title": REVISED_BOOK[0].get_title_for_node(document)}]}]}
    cursor.execute("""\
SELECT tree_to_json(uuid::text, module_version(major_version, minor_version), FALSE)
FROM latest_modules
WHERE portal_type = 'Collection'""")
    tree = json.loads(cursor.fetchone()[0])
    test_case.assertEqual(expected_tree, tree)

    hashlib.new(
        cnxepub.RESOURCE_HASH_TYPE,
        _read_file(RESOURCE_ONE_FILEPATH).read()
    ).hexdigest()
    # FIXME Remove and change assertion after cnx-archive switches to
    # ``cnxepub.RESOURCE_HASH_TYPE`` as hash. Use ``resource_hash`` in the
    # check instead of ``file_md5``.
    file_md5 = hashlib.new('md5',
                           _read_file(RESOURCE_ONE_FILEPATH).read()) \
        .hexdigest()
    cursor.execute("""\
SELECT f.file, f.media_type,
        ident_hash(m.uuid,m.major_version,m.minor_version)
FROM files as f natural join module_files as mf, latest_modules as m
WHERE
  mf.module_ident = m.module_ident
  AND
  f.md5 = %s""", (file_md5,))
    file, mime_type, ident_hash = cursor.fetchone()
    test_case.assertEqual(mime_type, 'image/png')
    test_case.assertEqual(ident_hash, document_ident_hash)
    test_case.assertEqual(file[:], _read_file(RESOURCE_ONE_FILEPATH).read())


# ################### #
#   Use case setups   #
# ################### #
# Used to setup a use case within the archive database.
# For example, the BOOK use case needs setup in archive, before
# one tries to make a revision publication for it.
# These use a naming convension setup_<use-case-name>_in_archive.
# All checker callables should have positional arguments for
# the test case and a database cursor object.
#
#   def setup_<use-case-name>_in_archive(test_case, cursor):
#       ...
#
# These assume that the identifiers for the respective REVISED_* use case
# are used when inputting the model in the archive database.
# This assumption is made because the use cases are meant to work together.


def _is_published(ident_hash, cursor):
    cursor.execute("""\
SELECT module_ident
FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                   (ident_hash,))
    try:
        cursor.fetchone()[0]
    except TypeError:
        return False
    return True


def _set_uri(model):
    """Set the model's cnx-archive-uri to the model's ident_hash."""
    # Even though the field ends in -uri, we use the ident_hash here
    # Baking fails if the full uri is stored here
    # because this field is overwrites the module id in collate_models
    model.set_uri('cnx-archive', model.ident_hash)


def _insert_control_id(uuid_, cursor):
    """Inserts a UUID value into the ``document_controls`` table."""
    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s::UUID) RETURNING uuid""",
                   (uuid_,))
    return cursor.fetchone()[0]


def _insert_acl_for_model(model, cursor):
    """Insert the access control list for the given model."""
    uuid_ = model.id
    permission = 'publish'
    for person_struct in model.metadata['publishers']:
        user_id = person_struct['id']
        cursor.execute("""\
INSERT INTO document_acl (uuid, user_id, permission)
VALUES (%s, %s, %s)""", (uuid_, user_id, permission,))


def _insert_user_info(model, cursor):
    """Insert the user shadow table info."""
    user_ids = set([])
    for role_attr in cnxepub.ATTRIBUTED_ROLE_KEYS:
        for role in model.metadata.get(role_attr, []):
            user_ids.add(role['id'])

    # Check for existing records to update.
    cursor.execute("SELECT username from users where username = ANY (%s)",
                   (list(user_ids),))
    try:
        existing_user_ids = [x[0] for x in cursor.fetchall()]
    except TypeError:
        existing_user_ids = []
    new_user_ids = [u for u in user_ids if u not in existing_user_ids]

    # At this time, we don't need to store the actual user details.
    # So, making an entry that contains only a username should be enough.

    # Insert new records.
    for user_id in new_user_ids:
        cursor.execute("""\
INSERT INTO users (username, is_moderated)
VALUES (%s, 't')""", (user_id,))


def _insert_file(file_bytes, media_type, cursor):
    """Insert a file, with media_type, into the files table. Returns fileid"""
    cursor.execute('INSERT INTO files (file, media_type)'
                   ' VALUES (%s, %s)'
                   ' RETURNING fileid',
                   (Binary(file_bytes), media_type))
    return cursor.fetchone()[0]


def setup_RECIPES_in_archive(test_case, cursor):
    """Setup RECIPES"""
    recipe_ids = (
        _insert_file(_read_file(RECIPE_ONE_FILEPATH).read(),
                     'text/css', cursor),
        _insert_file(_read_file(RECIPE_TWO_FILEPATH).read(),
                     'text/css', cursor)
    )
    cursor.execute("INSERT INTO print_style_recipes "
                   "(print_style, tag, fileid)"
                   " VALUES (%s, 'v1.0', %s), (%s, 'v1.0', %s)",
                   ('style_with_recipe_one', recipe_ids[0],
                    'style_with_recipe_two', recipe_ids[1]))
    return recipe_ids


def setup_BOOK_in_archive(test_case, cursor):
    """Set up BOOK"""
    binder = deepcopy(BOOK)
    # FIXME Use the REVISED_BOOK id when it exists.
    binder.id = 'd5dbbd8e-d137-4f89-9d0a-3ac8db53d8ee'
    binder.metadata['version'] = '1.1'
    document = binder[0][0][0]
    # FIXME Use the REVISED_BOOK id when it exists.
    document.id = '11e2e631-73b5-44da-acae-e97defd9673b'
    document.metadata['version'] = '1'

    publisher = 'ream'
    publication_message = 'published via test setup'

    from ..publish import publish_model
    _insert_control_id(document.id, cursor)
    _insert_user_info(document, cursor)
    publish_model(cursor, document, publisher, publication_message)
    _set_uri(document)
    _insert_acl_for_model(document, cursor)
    _insert_control_id(binder.id, cursor)
    _insert_user_info(binder, cursor)
    publish_model(cursor, binder, publisher, publication_message)
    _set_uri(binder)
    _insert_acl_for_model(binder, cursor)
    return binder


def setup_PAGE_ONE_in_archive(test_case, cursor):
    """Set up PAGE_ONE"""
    model = deepcopy(PAGE_ONE)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = '2f2858ea-933c-4707-88d2-2e512e27252f'
    model.metadata['version'] = '1'

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_PAGE_TWO_in_archive(test_case, cursor):
    """Set up PAGE_TWO"""
    model = deepcopy(PAGE_TWO)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = '32b11ecd-a1c2-4141-95f4-7c27f8c71dff'
    model.metadata['version'] = '1'

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_PAGE_THREE_in_archive(test_case, cursor):
    """Set up PAGE_THREE"""
    model = deepcopy(PAGE_THREE)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = '014415de-2ae0-4053-91bc-74c9db2704f5'
    model.metadata['version'] = '1'

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_PAGE_FOUR_in_archive(test_case, cursor):
    """Set up PAGE_FOUR"""
    model = deepcopy(PAGE_FOUR)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'deadbeef-a927-4652-9a8d-deb2d28fb801'
    model.metadata['version'] = '1'

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_EXERCISES_PAGE_in_archive(test_case, cursor):
    """Set up EXERCISES_PAGE"""
    model = deepcopy(EXERCISES_PAGE)

    publisher = 'someone'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = '3602af96-7f0d-4ce0-828d-cc0a1bcfab59'
    model.metadata['version'] = '1'

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_COMPLEX_BOOK_ONE_in_archive(test_case, cursor):
    """Set up COMPLEX_BOOK_ONE"""
    model = deepcopy(COMPLEX_BOOK_ONE)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408'
    model.metadata['version'] = '1.1'

    doc = setup_PAGE_ONE_in_archive(test_case, cursor)
    model[0][0] = doc
    doc = setup_PAGE_TWO_in_archive(test_case, cursor)
    model[0][1] = doc
    doc = setup_PAGE_THREE_in_archive(test_case, cursor)
    model[1][0] = doc
    doc = setup_PAGE_FOUR_in_archive(test_case, cursor)
    model[1][1] = doc

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_COMPLEX_BOOK_ONE_v2_in_archive(test_case, cursor):
    """Set up COMPLEX_BOOK_ONE v2"""
    model = deepcopy(COMPLEX_BOOK_ONE)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'c3bb4bfb-3b53-41a9-bb03-583cf9ce3408'
    model.metadata['version'] = '2.1'

    doc = setup_PAGE_ONE_in_archive(test_case, cursor)
    model[0][0] = doc
    doc = setup_PAGE_TWO_in_archive(test_case, cursor)
    model[0][1] = doc
    doc = setup_PAGE_THREE_in_archive(test_case, cursor)
    model[1][0] = doc
    del model[1][1]

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        publish_model(cursor, model, publisher, publication_message)
    _set_uri(model)
    return model


def setup_COMPLEX_BOOK_TWO_in_archive(test_case, cursor):
    """Set up COMPLEX_BOOK_ONE"""
    model = deepcopy(COMPLEX_BOOK_TWO)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'dbb28a6b-cad2-4863-986f-6059da93386b'
    model.metadata['version'] = '1.1'

    doc = setup_PAGE_TWO_in_archive(test_case, cursor)
    model[0][0] = doc
    doc = setup_PAGE_THREE_in_archive(test_case, cursor)
    model[0][1] = doc
    doc = setup_PAGE_ONE_in_archive(test_case, cursor)
    model[1][0] = doc

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_COMPLEX_BOOK_THREE_in_archive(test_case, cursor):
    """Set up COMPLEX_BOOK_THREE"""
    model = deepcopy(COMPLEX_BOOK_THREE)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'afe84d4c-61e2-404a-bca7-2e7899d21f47'
    model.metadata['version'] = '1.1'

    doc = setup_PAGE_TWO_in_archive(test_case, cursor)
    model[0] = doc
    doc = setup_PAGE_FOUR_in_archive(test_case, cursor)
    model[1] = doc

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model


def setup_EXERCISES_BOOK_in_archive(test_case, cursor):
    """Set up EXERCISES_BOOK"""
    model = deepcopy(EXERCISES_BOOK)

    publisher = 'ream'
    publication_message = 'published via test setup'
    # FIXME Use the REVISED_* id when it exists.
    model.id = 'c7cef66f-2715-47ef-afb1-16e9a07212f1'
    model.metadata['version'] = '1.1'

    doc = setup_EXERCISES_PAGE_in_archive(test_case, cursor)
    model[0] = doc

    from ..publish import publish_model
    if not _is_published(model.ident_hash, cursor):
        _insert_control_id(model.id, cursor)
        _insert_user_info(model, cursor)
        publish_model(cursor, model, publisher, publication_message)
        _insert_acl_for_model(model, cursor)
    _set_uri(model)
    return model
