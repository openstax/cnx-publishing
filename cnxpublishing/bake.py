# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2016-2017, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""Provides a means of baking a binder and persisting it to the archive."""
import cnxepub
import memcache
from cnxepub.collation import collate as collate_models
from cnxepub.formatters import exercise_callback_factory
from pyramid.threadlocal import get_current_registry
from pyramid.settings import aslist

from .db import with_db_cursor
from .publish import (
    publish_collated_document,
    publish_collated_tree,
    publish_composite_model,
)
from .utils import amend_tree_with_slugs


def _formatter_callback_factory():  # pragma: no cover
    """Returns a list of includes to be given to `cnxepub.collation.collate`.

    """
    includes = []
    exercise_url_template = '{baseUrl}/api/exercises?q={field}:"{{itemCode}}"'
    settings = get_current_registry().settings
    exercise_base_url = settings.get('embeddables.exercise.base_url', None)
    exercise_matches = [match.split(',', 1) for match in aslist(
        settings.get('embeddables.exercise.match', ''), flatten=False)]
    exercise_token = settings.get('embeddables.exercise.token', None)
    mathml_url = settings.get('mathmlcloud.url', None)
    memcache_servers = settings.get('memcache_servers')
    if memcache_servers:
        memcache_servers = memcache_servers.split()
    else:
        memcache_servers = None

    if exercise_base_url and exercise_matches:
        mc_client = None
        if memcache_servers:
            mc_client = memcache.Client(memcache_servers, debug=0)
        for (exercise_match, exercise_field) in exercise_matches:
            template = exercise_url_template.format(
                baseUrl=exercise_base_url, field=exercise_field)
            includes.append(exercise_callback_factory(exercise_match,
                                                      template,
                                                      mc_client,
                                                      exercise_token,
                                                      mathml_url))
    return includes


def _get_recipe(recipe_id, cursor):
    """Returns recipe as a unicode string"""

    cursor.execute("""SELECT convert_from(file, 'utf-8') FROM files
                      WHERE fileid = %s""", (recipe_id,))
    return cursor.fetchone()[0]


@with_db_cursor
def bake(binder, recipe_id, publisher, message, cursor):
    """Given a `Binder` as `binder`, bake the contents and
    persist those changes alongside the published content.

    """
    recipe = _get_recipe(recipe_id, cursor)
    includes = _formatter_callback_factory()
    binder = collate_models(binder, ruleset=recipe, includes=includes)

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
    amend_tree_with_slugs(tree)
    publish_collated_tree(cursor, tree)

    return []


@with_db_cursor
def remove_baked(binder_ident_hash, cursor):
    """Given a binder's ident_hash, remove the baked results."""
    # Remove the baked tree.
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

    # Remove the baked/collation associations and composite-modules entries.
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


__all__ = ('bake', 'remove_baked',)
