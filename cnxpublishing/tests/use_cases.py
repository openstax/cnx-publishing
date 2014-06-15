# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import json
from copy import deepcopy

import cnxepub
from cnxarchive.utils import join_ident_hash, split_ident_hash


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
        u'summary': "<span>Book summary</span>",
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
                            data=u'<p class="para">If you finish the book, there will be cake.</p>',
                            metadata={
                                u'title': u'Document One of Infinity',
                                u'created': u'2013/03/19 15:01:16 -0500',
                                u'revised': u'2013/03/19 15:01:16 -0500',
                                u'keywords': [u'South Africa'],
                                u'subjects': [u'Science and Mathematics'],
                                u'summary': u'<span>descriptive text</span>',
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
                                                  u'type': u'cnx-id'}]},
                            ),
                    ]),
                ]),
        ])
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


PAGE_ONE = cnxepub.Document(
    id=u'2cf4d7d3@draft',
    data=u'<p class="para">If you finish the book, there will be cake.</p>',
    metadata={
        u'title': u'Document One of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u'<span>descriptive text</span>',
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
                          u'type': u'cnx-id'}]}
    )

PAGE_TWO = cnxepub.Document(
    id=u'c24fe396@draft',
    data=u'<p class="para">If you finish the book, there will be cake.</p>',
    metadata={
        u'title': u'Document Two of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u'<span>descriptive text</span>',
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
                          u'type': u'cnx-id'}]}
    )

PAGE_THREE = cnxepub.Document(
    id=u'e12b72ac@draft',
    data=u'<p class="para">If you finish the book, there will be cake.</p>',
    metadata={
        u'title': u'Document Three of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u'<span>descriptive text</span>',
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
                          u'type': u'cnx-id'}]}
    )

PAGE_FOUR = cnxepub.Document(
    id=u'deadbeef@draft',
    data=u'<p class="para">If you finish the book, there will be cake.</p>',
    metadata={
        u'title': u'Document Four of Infinity',
        u'created': u'2013/03/19 15:01:16 -0500',
        u'revised': u'2013/03/19 15:01:16 -0500',
        u'keywords': [u'South Africa'],
        u'subjects': [u'Science and Mathematics'],
        u'summary': u'<span>descriptive text</span>',
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
        u'translators': []
        }
    )

COMPLEX_BOOK_ONE = cnxepub.Binder(
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
        u'summary': "<span>Book summary</span>",
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
        u'summary': "<span>Book summary</span>",
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
        u'summary': "<span>Book summary</span>",
        },
    title_overrides=['D One', 'D Two'],
    nodes=[PAGE_TWO, PAGE_FOUR],
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
SELECT portal_type, uuid||'@'||concat_ws('.',major_version,minor_version)
FROM modules""")
    items = dict(cursor.fetchall())
    document_ident_hash = items['Module']
    binder_ident_hash = items['Collection']

    expected_tree = {
        "id": binder_ident_hash,
        "title": "Book of Infinity",
        "contents": [
            {"id": "subcol",
             "title": "Part One",
             "contents": [
                 {"id": "subcol",
                  "title": "Chapter One",
                  "contents": [
                      {"id": document_ident_hash,
                       "title": "Document One"}]}]}]}
    cursor.execute("""\
SELECT tree_to_json(uuid::text, concat_ws('.',major_version, minor_version))
FROM modules
WHERE portal_type = 'Collection'""")
    tree = json.loads(cursor.fetchone()[0])
    test_case.assertEqual(expected_tree, tree)


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
        u"title": u"Book of Infinity",
        u"contents": [
            {u"id": u"subcol",
             u"title": REVISED_BOOK[0].metadata['title'],
             u"contents": [
                 {u"id": unicode(document_ident_hash),
                  u"title": REVISED_BOOK[0].get_title_for_node(document)}]}]}
    cursor.execute("""\
SELECT tree_to_json(uuid::text, concat_ws('.', major_version, minor_version))
FROM latest_modules
WHERE portal_type = 'Collection'""")
    tree = json.loads(cursor.fetchone()[0])
    test_case.assertEqual(expected_tree, tree)


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
WHERE uuid||'@'||concat_ws('.', major_version, minor_version) = %s""",
                   (ident_hash,))
    try:
        ident = cursor.fetchone()[0]
    except TypeError:
        return False
    return True


def _set_uri(model):
    """Set the system uri on the model."""
    uri = "https://cnx.org/contents/{}".format(model.ident_hash)
    model.set_uri('cnx-archive', uri)


def _insert_control_id(uuid_, cursor):
    """Inserts a UUID value into the ``document_controls`` table."""
    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s::UUID) RETURNING uuid""",
                   (uuid_,))
    return cursor.fetchone()[0]


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
    publish_model(cursor, document, publisher, publication_message)
    _set_uri(document)
    _insert_control_id(binder.id, cursor)
    publish_model(cursor, binder, publisher, publication_message)
    _set_uri(binder)
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
        publish_model(cursor, model, publisher, publication_message)
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
        publish_model(cursor, model, publisher, publication_message)
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
        publish_model(cursor, model, publisher, publication_message)
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
        publish_model(cursor, model, publisher, publication_message)
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
        publish_model(cursor, model, publisher, publication_message)
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
        publish_model(cursor, model, publisher, publication_message)
    _set_uri(model)
    return model
