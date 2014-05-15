# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import json

import cnxepub


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


# ################### #
#   Use case checks   #
# ################### #
# Used to verify the use case within the archive database.
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
            {"id":"subcol",
             "title":"Part One",
             "contents":[
                 {"id":"subcol",
                  "title":"Chapter One",
                  "contents":[
                      {"id": document_ident_hash,
                       "title":"Document One"}]}]}]}
    cursor.execute("""\
SELECT tree_to_json(uuid::text, concat_ws('.',major_version, minor_version))
FROM modules
WHERE portal_type = 'Collection'""")
    tree = json.loads(cursor.fetchone()[0])
    test_case.assertEqual(expected_tree, tree)
