# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import inspect
try:
    from unittest import mock
except ImportError:
    import mock
from vcr_unittest import VCRMixin

import cnxepub

from . import use_cases
from .testing import db_connect
from .test_db import BaseDatabaseIntegrationTestCase


def flatten_tree(tree):
    """Flatten a tree to a linear sequence of values."""
    yield dict([
        (k, v)
        for k, v in tree.items()
        if k != 'contents'
    ])
    if 'contents' in tree:
        for x in tree['contents']:
            for y in flatten_tree(x):
                yield y


class AmendWithBakeTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.bake import bake
        return bake

    def _get_baked_file(self, cursor, doc, binder):
        cursor.execute("""\
SELECT f.file
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS mparent, modules AS mitem
WHERE
  cfa.context = mparent.module_ident
  AND
  cfa.item = mitem.module_ident
  AND
  ident_hash(mparent.uuid, mparent.major_version, mparent.minor_version) = %s
  AND
  ident_hash(mitem.uuid, mitem.major_version, mitem.minor_version) = %s""",
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
        metadata['created'] = None
        metadata['revised'] = None
        metadata['title'] = "Made up of other things"

        # Add some fake collation objects to the book.
        content = '<body><p>composite</p></body>'
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)
        composite_section = cnxepub.TranslucentBinder(
            nodes=[composite_doc],
            metadata={'title': "Other things"})

        baked_doc_content = '<body><p>collated</p></body>'

        def cnxepub_collate(binder_model, ruleset=None, includes=None):
            binder_model[0][0].content = baked_doc_content
            binder_model.append(composite_section)
            return binder_model

        fake_recipe_id = 1

        with mock.patch('cnxpublishing.bake.collate_models') as mock_collate:
            mock_collate.side_effect = cnxepub_collate
            errors = self.target(binder, fake_recipe_id, publisher, msg)

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
        baked_tree = cursor.fetchone()[0]
        self.assertIn(composite_doc.ident_hash,
                      cnxepub.flatten_tree_to_ident_hashes(baked_tree))
        # ... and with slug values
        slugs = [x['slug'] for x in flatten_tree(baked_tree)]
        expected_slugs = [
            u'book-of-infinity',
            u'part-one',
            u'document-one',
            u'document-two',
            u'part-two',
            u'document-three',
            u'document-four',
            u'other-things',
            u'made-up-of-other-things',
        ]
        self.assertEqual(slugs, expected_slugs)

        # Ensure the changes to a document content were persisted.
        content_to_check = [
            (binder[0][0], baked_doc_content,),
            (composite_doc, content,),
        ]
        for doc, content in content_to_check:
            self.assertIn(content, self._get_baked_file(cursor, doc, binder))


class RemoveBakedTestCase(BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.bake import remove_baked
        return remove_baked

    def _get_file_sha1(self, cursor, doc, binder):
        cursor.execute("""\
SELECT f.sha1
FROM collated_file_associations AS cfa NATURAL JOIN files AS f,
     modules AS mparent, modules AS mitem
WHERE
  cfa.context = mparent.module_ident
  AND
  cfa.item = mitem.module_ident
  AND
   ident_hash(mparent.uuid, mparent.major_version, mparent.minor_version) = %s
  AND
   ident_hash(mitem.uuid, mitem.major_version, mitem.minor_version) = %s""",
                       (binder.ident_hash, doc.ident_hash,))
        sha1 = cursor.fetchone()[0]
        return sha1

    @db_connect
    def setUp(self, cursor):
        super(RemoveBakedTestCase, self).setUp()
        binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(self, cursor)
        cursor.connection.commit()
        publisher = 'ream'
        msg = 'part of collated publish'

        # Build some new metadata for the composite document.
        metadata = [x.metadata.copy()
                    for x in cnxepub.flatten_to_documents(binder)][0]
        del metadata['cnx-archive-uri']
        del metadata['version']
        metadata['created'] = None
        metadata['revised'] = None
        metadata['title'] = "Made up of other things"

        # Add some fake collation objects to the book.
        content = '<body><p>composite</p></body>'
        composite_doc = cnxepub.CompositeDocument(None, content, metadata)
        composite_section = cnxepub.TranslucentBinder(
            nodes=[composite_doc],
            metadata={'title': "Other things"})

        baked_doc_content = '<body><p>collated</p></body>'

        def cnxepub_collate(binder_model, ruleset=None, includes=None):
            binder_model[0][0].content = baked_doc_content
            binder_model.append(composite_section)
            return binder_model

        with mock.patch('cnxpublishing.bake.collate_models') as mock_collate:
            mock_collate.side_effect = cnxepub_collate
            from cnxpublishing.bake import bake
            fake_recipe_id = 1
            bake(binder, fake_recipe_id, publisher, msg, cursor=cursor)

        self.ident_hash = binder.ident_hash
        self.composite_ident_hash = composite_doc.ident_hash
        self.baked_doc_sha1 = self._get_file_sha1(cursor,
                                                  binder[0][0], binder)
        self.composite_doc_sha1 = self._get_file_sha1(cursor,
                                                      composite_doc, binder)

    @db_connect
    def test(self, cursor):
        self.target(self.ident_hash, cursor=cursor)
        from cnxpublishing.utils import split_ident_hash
        id, version = split_ident_hash(self.ident_hash)

        # Ensure the original tree is intact.
        cursor.execute("SELECT tree_to_json(%s, %s, FALSE)::json;",
                       (id, version,))
        tree = cursor.fetchone()[0]
        self.assertNotIn(self.composite_ident_hash,
                         cnxepub.flatten_tree_to_ident_hashes(tree))

        # Ensure the tree as been stamped.
        cursor.execute("SELECT tree_to_json(%s, %s, TRUE)::json;",
                       (id, version,))
        baked_tree = cursor.fetchone()[0]
        self.assertEqual(baked_tree, None)

        # Ensure the collated/baked files relationship is removed.
        cursor.execute("SELECT * FROM collated_file_associations AS cfa NATURAL JOIN modules AS m "
                       "WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s", (self.ident_hash,))
        with self.assertRaises(TypeError):
            cursor.fetchone()[0]


class BakedExercisesTestCase(VCRMixin, BaseDatabaseIntegrationTestCase):

    @property
    def target(self):
        from cnxpublishing.bake import bake
        return bake

    # https://github.com/agriffis/vcrpy-unittest/blob/8850debf5928b34a41e2f9f537fb0ba319008ed3/vcr_unittest/testcase.py#L34
    def _get_cassette_library_dir(self):
        testdir = os.path.dirname(inspect.getfile(self.__class__))
        return os.path.join(testdir, 'data', 'cassettes')

    @db_connect
    def test(self, cursor):
        recipes = use_cases.setup_RECIPES_in_archive(self, cursor)
        binder = use_cases.setup_EXERCISES_BOOK_in_archive(self, cursor)
        cursor.connection.commit()
        publisher = 'ream'
        msg = 'part of collated publish'

        # Call bake but store the result of collate_models for later inspection
        collate_results = []
        from cnxpublishing.bake import collate_models

        def cnxepub_collate(binder, ruleset=None, includes=None):
            composite_doc = collate_models(binder, ruleset=ruleset, includes=includes)
            collate_results.append(composite_doc)
            return composite_doc
        with mock.patch('cnxpublishing.bake.collate_models') as mock_collate:
            mock_collate.side_effect = cnxepub_collate
            self.target(binder, recipes[1], publisher, msg, cursor=cursor)
        composite_doc = collate_results[0]

        # Ensure the tree has been stamped.
        cursor.execute("SELECT tree_to_json(%s, %s, TRUE)::json;",
                       (binder.id, binder.metadata['version'],))
        baked_tree = cursor.fetchone()[0]
        self.assertIn(composite_doc.ident_hash,
                      cnxepub.flatten_tree_to_ident_hashes(baked_tree))

        # Ensure the exercises were pulled into the content.
        content = composite_doc[0].content
        self.assertIn('<div>What is kinematics?</div>', content)
        self.assertIn('No, the gravitational force is a field force and does not', content)
        self.assertIn('<div>What kind of physical quantity is force?</div>', content)
        self.assertIn('<li>Both internal and external forces</li>', content)
