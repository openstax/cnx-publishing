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
from cnxarchive.utils import join_ident_hash


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
    for row in cursor.fetchall():
        key = row[:1]
        value = row[2:]
        if key not in records:
            records[key] = []
        records[key].append(value)
    expected_records = {
        # [uuid, moduleid]: [[major_version, minor_version, version], ...]
        [binder.id, 'col10000']: [
            ['1', '1', '1.1'],
            ['2', '1', '2.1'],
            ],
        [document.id, 'm10000']: [
            ['1', None, '1.1'],
            ['2', None, '2.1'],
            ],
        }
    test_case.assertEqual(expected_records, records)

    # Check the tree...
    binder_ident_hash = join_ident_hash(binder.id, (2, 1,))
    document_ident_hash = join_ident_hash(document.id, (2, None,))
    expected_tree = {
        "id": binder_ident_hash,
        "title": "Book of Infinity",
        "contents": [
            {"id": "subcol",
             "title": REVISED_BOOK[0].metadata['title'],
             "contents": [
                 {"id": document_ident_hash,
                  "title": REVISED_BOOK[0].get_title_for_node(document)}]}]}
    cursor.execute("""\
SELECT tree_to_json(uuid::text, concat_ws('.',major_version, minor_version))
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

def setup_BOOK_in_archive(test_case, cursor):
    """This assumes that the identifiers used within REVISED_BOOK
    are used while inputting this into the database. This assumption
    is made because the two use cases are meant to work together.
    """
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
    publish_model(cursor, document, publisher, publication_message)
    publish_model(cursor, binder, publisher, publication_message)
