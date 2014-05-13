# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
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
