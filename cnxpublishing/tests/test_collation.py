# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import unittest
try:
    from unittest import mock
except ImportError:
    import mock

import cnxepub

from . import use_cases
from .testing import db_connect
from .test_db import BaseDatabaseIntegrationTestCase


class AmendWithCollationTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.collation import collate
        return collate

    def _get_collated_file(self, cursor, doc, binder):
        cursor.execute("""\
SELECT f.file
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS mparent, modules AS mitem
WHERE
  cfa.context = mparent.module_ident
  AND
  cfa.item = mitem.module_ident
  AND
  mparent.uuid || '@' || concat_ws('.', mparent.major_version, mparent.minor_version) = %s
  AND
  mitem.uuid || '@' || concat_ws('.', mitem.major_version, mitem.minor_version) = %s""",
                       (binder.ident_hash, doc.ident_hash,))
        file = cursor.fetchone()[0]
        return file[:]

    @db_connect
    def test(self, cursor):
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()
        publisher = 'ream'
        msg = 'part of collated publish'

        # Build some new metadata for the composite document.
        metadata = [x.metadata.copy()
                    for x in cnxepub.flatten_to_documents(binder)][0]
        del metadata['cnx-archive-uri']
        del metadata['version']
        metadata['title'] = "Made up of other things"

        # Add some fake collation objects to the book.
        content = '<p>composite</p>'
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)
        composite_section = cnxepub.TranslucentBinder(
            nodes=[composite_doc],
            metadata={'title': "Other things"})

        collated_doc_content = '<p>collated</p>'

        def collate(binder_model):
            binder_model[0][0].content = collated_doc_content
            binder_model.append(composite_section)

        with mock.patch('cnxpublishing.collation.collate_models') as mock_collate:
            mock_collate.side_effect = collate
            errors = self.target(binder, publisher, msg)

        # Ensure the output of the errors.
        self.assertEqual(errors, [])

        # Ensure the original tree is intact.
        cursor.execute("SELECT tree_to_json(%s, %s, FALSE)::json;",
                       (binder.id, binder.metadata['version'],))
        tree = cursor.fetchone()[0]
        self.assertNotIn(composite_doc.ident_hash,
                         cnxepub.flatten_tree_to_ident_hashes(tree))

        # Ensure the tree as been stamped.
        cursor.execute("SELECT tree_to_json(%s, %s, TRUE)::json;",
                       (binder.id, binder.metadata['version'],))
        collated_tree = cursor.fetchone()[0]
        self.assertIn(composite_doc.ident_hash,
                      cnxepub.flatten_tree_to_ident_hashes(collated_tree))

        # Ensure the changes to a document content were persisted.
        content_to_check = [
            (binder[0][0], collated_doc_content,),
            (composite_doc, content,),
            ]
        for doc, content in content_to_check:
            self.assertIn(content, self._get_collated_file(cursor, doc, binder))
