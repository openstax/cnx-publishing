# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""Provides a means of collating a binder and persisting it to the archive."""
import cnxepub
from cnxepub.collation import collate as collate_models

from .db import with_db_cursor
from .publish import (
    publish_collated_document,
    publish_collated_tree,
    publish_composite_model,
    )


@with_db_cursor
def collate(binder, publisher, message, cursor, includes=None):
    """Given a `Binder` as `binder`, collate the contents and
    persist those changes alongside the published content.

    """

    binder = collate_models(binder, ruleset="ruleset.css", includes=includes)

    def flatten_filter(model):
        return (isinstance(model, cnxepub.CompositeDocument) or
                (isinstance(model, cnxepub.Binder) and
                 model.metadata.get('type') == 'composite-chapter'))

    def only_documents_filter(model):
        return isinstance(model, cnxepub.Document) \
               and not isinstance(model, cnxepub.CompositeDocument)

    for doc in cnxepub.flatten_to(binder, flatten_filter):
        publish_composite_model(cursor, doc, binder, publisher, message)

    for doc in cnxepub.flatten_to(binder, only_documents_filter):
        publish_collated_document(cursor, doc, binder)

    tree = cnxepub.model_to_tree(binder)
    publish_collated_tree(cursor, tree)

    return []


@with_db_cursor
def remove_collation(binder_ident_hash, cursor):
    """Given a binder's ident_hash, remove the collated results."""
    # Remove the collated tree.
    cursor.execute("""\
    WITH RECURSIVE t(node, path, is_collated) AS (
    SELECT nodeid, ARRAY[nodeid], is_collated
    FROM trees AS tr, modules AS m
    WHERE ident_hash(m.uuid, m.major_version, m.minor_version) = %s AND
      tr.documentid = m.module_ident AND
      tr.parent_id IS NULL AND
      tr.is_collated = TRUE
UNION ALL
    SELECT c1.nodeid, t.path || ARRAY[c1.nodeid], c1.is_collated
    FROM trees AS c1 JOIN t ON (c1.parent_id = t.node)
    WHERE not nodeid = any (t.path) AND t.is_collated = c1.is_collated
)
delete from trees where nodeid in (select node FROM t)
    """, (binder_ident_hash,))

    # Remove the collation associations and composite-modules entries.
    cursor.execute("""\
    DELETE FROM collated_file_associations AS cfa
    USING modules AS m
    WHERE
      (ident_hash(m.uuid, m.major_version, m.minor_version) = %s
       )
      AND
      cfa.context = m.module_ident
    RETURNING item, fileid""", (binder_ident_hash,))
    # FIXME (11-May-2016) This can create orphan `files` & `modules` entries,
    #       but since it's not intended to be used in production
    #       this is not a major concern.


__all__ = ('collate', 'remove_collation',)
