# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2019, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import
from uuid import UUID

from psycopg2.extras import DictCursor
from pyramid import httpexceptions
from pyramid.view import view_config

from ...db import db_connect


STATE_ICONS = [
    ("QUEUED", 'fa fa-hourglass-1 state-icon queued'),
    ("STARTED", 'fa fa-hourglass-2 state-icon started'),
    ("RETRY", 'fa fa-repeat state-icon retry'),
    ("FAILURE", 'fa fa-close state-icon failure'),
    ("SUCCESS", 'fa fa-check-square state-icon success'),
    ("FALLBACK", 'fa fa-check-square state-icon fallback'),
]
DEFAULT_ICON = 'fa fa-exclamation-triangle state-icon unknown'
SORTS_DICT = {
    "bpsa.created": 'created',
    "m.name": 'name',
    "STATE": 'state'}
ARROW_MATCH = {
    "ASC": 'fa fa-angle-up',
    "DESC": 'fa fa-angle-down'}


__all__ = (
    'admin_content_status',
    'admin_content_status_single',
    'admin_content_status_single_POST',
)


def get_baking_statuses_sql(get_request):
    """ Creates SQL to get info on baking books filtered from GET request.

    All books that have ever attempted to bake will be retured if they
    pass the filters in the GET request.
    If a single book has been requested to bake multiple times there will
    be a row for each of the baking attempts.
    By default the results are sorted in descending order of when they were
    requested to bake.

    N.B. The version reported for a print-style linked recipe will the the
    lowest cnx-recipes release installed that contains the exact recipe
    used to bake that book, regardless of when the book was baked relative
    to recipe releases. E.g. if a book uses the 'physics' recipe, and it is
    identical for versions 1.1, 1.2, 1.3, and 1.4, then it will be reported
    as version 1.1, even if the most recent release is tagged 1.4.
    """
    args = {}
    sort = get_request.get('sort', 'bpsa.created DESC')
    if (len(sort.split(" ")) != 2 or
            sort.split(" ")[0] not in SORTS_DICT.keys() or
            sort.split(" ")[1] not in ARROW_MATCH.keys()):
        raise httpexceptions.HTTPBadRequest(
            'invalid sort: {}'.format(sort))
    if sort == "STATE ASC" or sort == "STATE DESC":
        sort = 'bpsa.created DESC'
    uuid_filter = get_request.get('uuid', '').strip()
    author_filter = get_request.get('author', '').strip()
    latest_filter = get_request.get('latest', False)

    sql_filters = "WHERE"
    if latest_filter:
        sql_filters += """ ARRAY [m.major_version, m.minor_version] = (
         SELECT max(ARRAY[major_version,minor_version]) FROM
                   modules where m.uuid= uuid) AND """
    if uuid_filter != '':
        args['uuid'] = uuid_filter
        sql_filters += " m.uuid=%(uuid)s AND "
    if author_filter != '':
        author_filter = author_filter.decode('utf-8')
        sql_filters += " %(author)s=ANY(m.authors) "
        args["author"] = author_filter

    if sql_filters.endswith("AND "):
        sql_filters = sql_filters[:-4]
    if sql_filters == "WHERE":
        sql_filters = ""

    # FIXME  celery AsyncResult API is soooo sloow that this page takes
    # 2 min. or more to load on production.  As an workaround, this code
    # accesses the celery_taskmeta table directly. Need to remove that access
    # once we track enough state info ourselves. Want to track when queued,
    # started, ended, etc. for future monitoring of baking system performance
    # as well.
    # The 'limit 1' subselect is to ensure the "oldest identical version"
    # for recipes released as part of cnx-recipes (avoids one line per
    # identical recipe file in different releases, for a single baking job)

    statement = """
                       SELECT m.name, m.authors, m.uuid,
                       module_version(m.major_version,m.minor_version)
                          as current_version,
                       m.print_style,
                       CASE WHEN f.sha1 IS NOT NULL
                       THEN coalesce(dps.print_style,'(custom)')
                       ELSE dps.print_style
                       END AS recipe_name,
                       (select tag from print_style_recipes
                            where print_style = m.print_style
                                and fileid = m.recipe
                                order by revised asc limit 1) as recipe_tag,
                       coalesce(dps.fileid, m.recipe) as latest_recipe_id,
                       m.recipe as recipe_id,
                       f.sha1 as recipe,
                       m.module_ident,
                       ident_hash(m.uuid, m.major_version, m.minor_version),
                       bpsa.created, ctm.traceback,
                       CASE WHEN ctm.status = 'SUCCESS'
                           AND ms.statename = 'fallback'
                       THEN 'FALLBACK'
                       ELSE ctm.status
                       END as state
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
                INNER JOIN modulestates as ms USING (stateid)
                LEFT JOIN celery_taskmeta AS ctm
                    ON bpsa.result_id = ctm.task_id::uuid
                LEFT JOIN default_print_style_recipes as dps
                    ON dps.print_style = m.print_style
                LEFT JOIN latest_modules as lm
                    ON lm.uuid=m.uuid
                LEFT JOIN files f on m.recipe = f.fileid
                {}
                ORDER BY {};
                """.format(sql_filters, sort)
    args.update({'sort': sort})
    return statement, args


def format_authors(authors):
    if not authors:
        return ""
    return ', '.join([author.decode('utf-8') for author in authors])


@view_config(route_name='admin-content-status', request_method='GET',
             renderer='cnxpublishing.views:templates/content-status.html',
             permission='view', http_cache=0)
def admin_content_status(request):
    """
    Returns a dictionary with the states and info of baking books,
    and the filters from the GET request to pre-populate the form.
    """
    statement, sql_args = get_baking_statuses_sql(request.GET)

    states = []
    status_filters = request.params.getall('status_filter') or []
    state_icons = dict(STATE_ICONS)
    with db_connect(cursor_factory=DictCursor) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute(statement, vars=sql_args)
            for row in cursor.fetchall():
                message = ''
                state = row['state'] or 'PENDING'
                if status_filters and state not in status_filters:
                    continue
                if state == 'FAILURE':  # pragma: no cover
                    if row['traceback'] is not None:
                        message = row['traceback'].split("\n")[-2]
                latest_recipe = row['latest_recipe_id']
                current_recipe = row['recipe_id']
                if (current_recipe is not None and
                        current_recipe != latest_recipe):
                    state += ' stale_recipe'
                state_icon = state
                if state[:7] == "SUCCESS" and len(state) > 7:
                    state_icon = 'unknown'
                states.append({
                    'title': row['name'].decode('utf-8'),
                    'authors': format_authors(row['authors']),
                    'uuid': row['uuid'],
                    'print_style': row['print_style'],
                    'print_style_link': request.route_path(
                        'admin-print-style-single', style=row['print_style']),
                    'recipe': row['recipe'],
                    'recipe_name': row['recipe_name'],
                    'recipe_tag': row['recipe_tag'],
                    'recipe_link': request.route_path(
                        'get-resource', hash=row['recipe']),
                    'created': row['created'],
                    'state': state,
                    'state_message': message,
                    'state_icon': state_icons.get(
                        state_icon, DEFAULT_ICON),
                    'status_link': request.route_path(
                        'admin-content-status-single', uuid=row['uuid']),
                    'content_link': request.route_path(
                        'get-content', ident_hash=row['ident_hash'])
                })
    sort = request.params.get('sort', 'bpsa.created DESC')
    sort_match = SORTS_DICT[sort.split(' ')[0]]
    sort_arrow = ARROW_MATCH[sort.split(' ')[1]]
    if sort == "STATE ASC":
        states.sort(key=lambda x: x['state'])
    if sort == "STATE DESC":
        states.sort(key=lambda x: x['state'], reverse=True)

    num_entries = request.params.get('number', 100) or 100
    page = request.params.get('page', 1) or 1
    try:
        page = int(page)
        num_entries = int(num_entries)
        start_entry = (page - 1) * num_entries
    except ValueError:
        raise httpexceptions.HTTPBadRequest(
            'invalid page({}) or entries per page({})'.
            format(page, num_entries))
    total_entries = len(states)
    states = states[start_entry: start_entry + num_entries]

    returns = sql_args
    returns.update({'start_entry': start_entry,
                    'num_entries': num_entries,
                    'page': page,
                    'total_entries': total_entries,
                    'states': states,
                    'sort_' + sort_match: sort_arrow,
                    'sort': sort,
                    'domain': request.host,
                    'latest_only': request.GET.get('latest', False),
                    'STATE_ICONS': STATE_ICONS,
                    'status_filters': status_filters or [
                        i[0] for i in STATE_ICONS]})
    return returns


@view_config(route_name='admin-content-status-single', request_method='GET',
             renderer='cnxpublishing.views:'
                      'templates/content-status-single.html',
             permission='view', http_cache=0)
def admin_content_status_single(request):
    """
    Returns a dictionary with all the past baking statuses of a single book.
    """
    uuid = request.matchdict['uuid']
    try:
        UUID(uuid)
    except ValueError:
        raise httpexceptions.HTTPBadRequest(
            '{} is not a valid uuid'.format(uuid))

    statement, sql_args = get_baking_statuses_sql({'uuid': uuid})
    with db_connect(cursor_factory=DictCursor) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute(statement, sql_args)
            modules = cursor.fetchall()
            if len(modules) == 0:
                raise httpexceptions.HTTPBadRequest(
                    '{} is not a book'.format(uuid))

            states = []
            collection_info = modules[0]

            for row in modules:
                message = ''
                state = row['state'] or 'PENDING'
                if state == 'FAILURE':  # pragma: no cover
                    if row['traceback'] is not None:
                        message = row['traceback']
                latest_recipe = row['latest_recipe_id']
                current_recipe = row['recipe_id']
                if (latest_recipe is not None and
                        current_recipe != latest_recipe):
                    state += ' stale_recipe'
                states.append({
                    'version': row['current_version'],
                    'recipe': row['recipe'],
                    'created': str(row['created']),
                    'state': state,
                    'state_message': message,
                })

    return {'uuid': str(collection_info['uuid']),
            'title': collection_info['name'].decode('utf-8'),
            'authors': format_authors(collection_info['authors']),
            'print_style': collection_info['print_style'],
            'current_recipe': collection_info['recipe_id'],
            'current_ident': collection_info['module_ident'],
            'current_state': states[0]['state'],
            'states': states}


@view_config(route_name='admin-content-status-single', request_method='POST',
             renderer='cnxpublishing.views:'
                      'templates/content-status-single.html',
             permission='administer', http_cache=0)
def admin_content_status_single_POST(request):
    """ Retriggers baking for a given book. """
    args = admin_content_status_single(request)
    title = args['title']
    if args['current_state'] == 'SUCCESS':
        args['response'] = title + ' is not stale, no need to bake'
        return args

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT stateid FROM modules WHERE module_ident=%s",
                           vars=(args['current_ident'],))
            data = cursor.fetchall()
            if len(data) == 0:
                raise httpexceptions.HTTPBadRequest(
                    'invalid module_ident: {}'.format(args['current_ident']))
            if data[0][0] == 5 or data[0][0] == 6:
                args['response'] = title + ' is already baking/set to bake'
                return args

            cursor.execute("""UPDATE modules SET stateid=5
                           WHERE module_ident=%s""",
                           vars=(args['current_ident'],))

            args['response'] = title + " set to bake!"

    return args
