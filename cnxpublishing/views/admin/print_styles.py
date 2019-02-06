# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2019, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import

from psycopg2.extras import DictCursor
from pyramid.view import view_config

from ...db import db_connect


__all__ = (
    'admin_print_styles',
    'admin_print_styles_single',
)


@view_config(route_name='admin-print-style', request_method='GET',
             renderer='cnxpublishing.views:templates/print-style.html',
             permission='view', http_cache=0)
def admin_print_styles(request):
    """
    Returns a dictionary of all unique print_styles, and their latest tag,
    revision, and recipe_type.
    """
    styles = []
    # This fetches all recipes that have been used to successfully bake a
    # current book plus all default recipes that have not yet been used
    # as well as "bad" books that are not "current" state, but would otherwise
    # be the latest/current for that book
    with db_connect(cursor_factory=DictCursor) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                WITH latest AS (SELECT print_style, recipe,
                    count(*), count(nullif(stateid, 1)) as bad
                FROM modules m
                WHERE portal_type = 'Collection'
                      AND recipe IS NOT NULL
                      AND (
                          baked IS NOT NULL OR (
                              baked IS NULL AND stateid not in (1,8)
                              )
                          )
                      AND ARRAY [major_version, minor_version] = (
                          SELECT max(ARRAY[major_version,minor_version]) FROM
                              modules where m.uuid= uuid)

                GROUP BY print_style, recipe
                ),
                defaults AS (SELECT print_style, fileid AS recipe
                FROM default_print_style_recipes d
                WHERE not exists (SELECT 1
                                  FROM latest WHERE latest.recipe = d.fileid)
                )
                SELECT coalesce(ps.print_style, '(custom)') as print_style,
                       ps.title, coalesce(ps.recipe_type, 'web') as type,
                       ps.revised, ps.tag, ps.commit_id, la.count, la.bad
                FROM latest la LEFT JOIN print_style_recipes ps ON
                                    la.print_style = ps.print_style AND
                                    la.recipe = ps.fileid
                UNION ALL
                SELECT ps.print_style, ps.title, ps.recipe_type,
                       ps.revised, ps.tag, ps.commit_id, 0 AS count, 0 AS bad
                FROM defaults de JOIN print_style_recipes ps ON
                                    de.print_style = ps.print_style AND
                                    de.recipe = ps.fileid

            ORDER BY revised desc NULLS LAST, print_style

                """)
            for row in cursor.fetchall():
                styles.append({
                    'print_style': row['print_style'],
                    'title': row['title'],
                    'type': row['type'],
                    'revised': row['revised'],
                    'tag': row['tag'],
                    'commit_id': row['commit_id'],
                    'number': row['count'],
                    'bad': row['bad'],
                    'link': request.route_path('admin-print-style-single',
                                               style=row['print_style'])
                })
    return {'styles': styles}


@view_config(route_name='admin-print-style-single', request_method='GET',
             renderer='cnxpublishing.views:templates/print-style-single.html',
             permission='view', http_cache=0)
def admin_print_styles_single(request):
    """ Returns all books with any version of the given print style.

    Returns the print_style, recipe type, num books using the print_style,
    along with a dictionary of the book, author, revision date, recipe,
    tag of the print_style, and a link to the content.
    """
    style = request.matchdict['style']
    # do db search to get file id and other info on the print_style
    with db_connect(cursor_factory=DictCursor) as db_conn:
        with db_conn.cursor() as cursor:

            if style != '(custom)':
                cursor.execute("""
                    SELECT fileid, recipe_type, title
                    FROM default_print_style_recipes
                    WHERE print_style=%s
                    """, vars=(style,))
                info = cursor.fetchall()
                if len(info) < 1:
                    current_recipe = None
                    recipe_type = None
                    status = None

                else:
                    current_recipe = info[0]['fileid']
                    recipe_type = info[0]['recipe_type']
                    status = 'current'

                cursor.execute("""\
                    SELECT name, authors, lm.revised, lm.recipe, psr.tag,
                        f.sha1 as hash, psr.commit_id, uuid,
                        ident_hash(uuid, major_version, minor_version)
                    FROM modules as lm
                    LEFT JOIN print_style_recipes as psr
                    ON (psr.print_style = lm.print_style and
                        psr.fileid = lm.recipe)
                    LEFT JOIN files f ON psr.fileid = f.fileid
                    WHERE lm.print_style=%s
                    AND portal_type='Collection'
                    AND ARRAY [major_version, minor_version] = (
                        SELECT max(ARRAY[major_version,minor_version])
                        FROM modules WHERE lm.uuid = uuid)

                    ORDER BY psr.tag DESC;
                    """, vars=(style,))
            else:
                current_recipe = '(custom)'
                recipe_type = '(custom)'
                cursor.execute("""\
                    SELECT name, authors, lm.revised, lm.recipe, NULL as tag,
                        f.sha1 as hash, NULL as commit_id, uuid,
                        ident_hash(uuid, major_version, minor_version)
                    FROM modules as lm
                    JOIN files f ON lm.recipe = f.fileid
                    WHERE portal_type='Collection'
                    AND NOT EXISTS (
                        SELECT 1 from print_style_recipes psr
                        WHERE psr.fileid = lm.recipe)
                    AND ARRAY [major_version, minor_version] = (
                        SELECT max(ARRAY[major_version,minor_version])
                        FROM modules WHERE lm.uuid = uuid)
                    ORDER BY uuid, recipe, revised DESC;
                    """, vars=(style,))
                status = '(custom)'

            collections = []
            for row in cursor.fetchall():
                recipe = row['recipe']
                if (status != '(custom)' and
                        current_recipe is not None and
                        recipe != current_recipe):
                    status = 'stale'
                collections.append({
                    'title': row['name'].decode('utf-8'),
                    'authors': row['authors'],
                    'revised': row['revised'],
                    'recipe': row['hash'],
                    'recipe_link': request.route_path('get-resource',
                                                      hash=row['hash']),
                    'tag': row['tag'],
                    'ident_hash': row['ident_hash'],
                    'link': request.route_path('get-content',
                                               ident_hash=row['ident_hash']),
                    'status': status,
                    'status_link': request.route_path(
                        'admin-content-status-single', uuid=row['uuid']),

                })
    return {'number': len(collections),
            'collections': collections,
            'print_style': style,
            'recipe_type': recipe_type}
