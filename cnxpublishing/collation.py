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
def collate(binder, publisher, message, cursor):
    """Given a `Binder` as `binder`, collate the contents and
    persist those changes alongside the published content.

    """
    collate_models(binder)

    def flatten_filter(model):
        return isinstance(model, cnxepub.CompositeDocument)

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


__all__ = ('collate',)
