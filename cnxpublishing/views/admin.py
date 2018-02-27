# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import
from datetime import datetime, timedelta
from uuid import UUID

from celery.result import AsyncResult
from psycopg2.extras import DictCursor
from pyramid import httpexceptions
from pyramid.view import view_config

from ..db import db_connect
from .moderation import get_moderation
from .api_keys import get_api_keys

STATE_ICONS = [
    ("QUEUED", 'fa fa-hourglass-1 state-icon queued'),
    ("STARTED", 'fa fa-hourglass-2 state-icon started'),
    ("RETRY", 'fa fa-repeat state-icon retry'),
    ("FAILURE", 'fa fa-close state-icon failure'),
    ("SUCCESS", 'fa fa-check-square state-icon success'),
    ]
DEFAULT_ICON = 'fa fa-exclamation-triangle state-icon unknown'
SORTS_DICT = {
    "bpsa.created": 'created',
    "m.name": 'name',
    "STATE": 'state'}
ARROW_MATCH = {
    "ASC": 'fa fa-angle-up',
    "DESC": 'fa fa-angle-down'}


@view_config(route_name='admin-index', request_method='GET',
             renderer="cnxpublishing.views:templates/index.html",
             permission='preview')
def admin_index(request):  # pragma: no cover
    return {
        'navigation': [
            {'name': 'Moderation List',
             'uri': request.route_url('admin-moderation'),
             },
            {'name': 'API Keys',
             'uri': request.route_url('admin-api-keys'),
             },
            {'name': 'Post Publication Logs',
             'uri': request.route_url('admin-post-publications'),
             },
            {'name': 'Message Banners',
             'uri': request.route_url('admin-add-site-messages'),
             },
            {'name': 'Content Status',
             'uri': request.route_url('admin-content-status'),
             },
            ],
        }


@view_config(route_name='admin-moderation', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.html",
             permission='moderate')
@view_config(route_name='moderation-rss', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.rss",
             permission='view')
def admin_moderations(request):  # pragma: no cover
    return {'moderations': get_moderation(request)}


@view_config(route_name='admin-api-keys', request_method='GET',
             renderer="cnxpublishing.views:templates/api-keys.html",
             permission='administer')
def admin_api_keys(request):  # pragma: no cover
    # Easter Egg that will invalidate the cache, just hit this page.
    # FIXME Move this logic into the C[R]UD views...
    from ..authnz import lookup_api_key_info
    from ..cache import cache_manager
    cache_manager.invalidate(lookup_api_key_info)

    return {'api_keys': get_api_keys(request)}


@view_config(route_name='admin-post-publications', request_method='GET',
             renderer='cnxpublishing.views:templates/post-publications.html',
             permission='administer')
def admin_post_publications(request):
    states = []
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT ident_hash(m.uuid, m.major_version, m.minor_version),
       m.name, bpsa.created, bpsa.result_id::text
FROM document_baking_result_associations AS bpsa
     INNER JOIN modules AS m USING (module_ident)
ORDER BY bpsa.created DESC LIMIT 100""")
            for row in cursor.fetchall():
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback
                states.append({
                    'ident_hash': row[0],
                    'title': row[1],
                    'created': row[2],
                    'state': result.state,
                    'state_message': message,
                })

    return {'states': states}


@view_config(route_name='admin-add-site-messages', request_method='GET',
             renderer='cnxpublishing.views:templates/site-messages.html',
             permission='administer')
def admin_add_site_message(request):
    banners = []
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                SELECT id, service_state_id, starts, ends, priority, message
                FROM service_state_messages ORDER BY starts DESC;""")
            for row in cursor.fetchall():
                banners.append({
                    'id': row[0],
                    'service_state_id': row[1],
                    'starts': str(row[2]),
                    'ends': str(row[3]),
                    'priority': row[4],
                    'message': row[5],
                })
    today = datetime.today()
    tomorrow = today + timedelta(days=1)
    return {'start_date': today.strftime("%Y-%m-%d"),
            'start_time': today.strftime("%H:%M"),
            'end_date': tomorrow.strftime("%Y-%m-%d"),
            'end_time': tomorrow.strftime("%H:%M"),
            'banners': banners}


def parse_message_args(request):
    args = {}
    args['message'] = request.POST.get('message', 'Warning')
    args['priority'] = request.POST.get('priority', 1)
    args['type'] = request.POST.get('type', 1)

    today = datetime.today()
    tomorrow = today + timedelta(days=1)
    start_date = datetime.strptime(
        request.POST.get('start_date', today.strftime("%Y-%m-%d")),
        '%Y-%m-%d').date()
    start_time = datetime.strptime(
        request.POST.get('start_time', today.strftime("%H:%M")),
        '%H:%M').time()
    end_date = datetime.strptime(
        request.POST.get('end_date', tomorrow.strftime("%Y-%m-%d")),
        '%Y-%m-%d').date()
    end_time = datetime.strptime(
        request.POST.get('end_time', tomorrow.strftime("%H:%M")),
        '%H:%M').time()
    start = datetime.combine(start_date, start_time)
    end = datetime.combine(end_date, end_time)
    args.update({'starts': start, 'ends': end})
    return args


@view_config(route_name='admin-add-site-messages-POST', request_method='POST',
             renderer='templates/site-messages.html',
             permission='administer')
def admin_add_site_message_POST(request):
    # # If it was a post request to delete
    # if 'delete' in request.POST.keys():
    #     message_id = request.POST.get('delete', -1)
    #     with psycopg2.connect(db_conn_str) as db_conn:
    #         with db_conn.cursor() as cursor:
    #             cursor.execute("""\
    #                 DELETE FROM service_state_messages WHERE id=%s;
    #                 """, vars=(message_id, ))
    #     return_args = admin_add_site_message(request)
    #     return_args['response'] = "Message id ({}) successfully removed".\
    #                               format(message_id)
    #     return return_args

    # otherwise it was an post request to add an message banner
    args = parse_message_args(request)
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                INSERT INTO service_state_messages
                    (service_state_id, starts, ends, priority, message)
                VALUES (%(type)s, %(starts)s, %(ends)s,
                        %(priority)s, %(message)s);
                """, args)

    return_args = admin_add_site_message(request)
    return_args['response'] = "Message successfully added"
    return return_args


@view_config(route_name='admin-delete-site-messages', request_method='DELETE',
             renderer='templates/site-messages.html',
             permission='administer')
def admin_delete_site_message(request):
    message_id = request.body.split("=")[1]
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                DELETE FROM service_state_messages WHERE id=%s;
                """, vars=(message_id, ))
    return_args = admin_add_site_message(request)
    return_args['response'] = "Message id ({}) successfully removed".\
                              format(message_id)
    return return_args


@view_config(route_name='admin-edit-site-message', request_method='GET',
             renderer='templates/site-message-edit.html',
             permission='administer')
def admin_edit_site_message(request):
    message_id = request.matchdict['id']
    args = {'id': message_id}

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                SELECT id, service_state_id, starts, ends, priority, message
                FROM service_state_messages WHERE id=%s;
                """, vars=(message_id, ))
            results = cursor.fetchall()
            if len(results) != 1:
                raise httpexceptions.HTTPBadRequest(
                    '{} is not a valid id'.format(message_id))

            TYPE_MAP = {1: 'maintenance', 2: 'notice', None: 'maintenance'}
            PRIORITY_MAP = {1: 'danger', 2: 'warning', 3: 'success',
                            None: 'danger'}
            args[TYPE_MAP[results[0][1]]] = 'selected'
            args[PRIORITY_MAP[results[0][4]]] = 'selected'
            args['message'] = results[0][5]

            args['start_date'] = results[0][2].strftime("%Y-%m-%d")
            args['start_time'] = results[0][2].strftime("%H:%M")
            args['end_date'] = results[0][3].strftime("%Y-%m-%d")
            args['end_time'] = results[0][3].strftime("%H:%M")
    return args


@view_config(route_name='admin-edit-site-message-POST', request_method='POST',
             renderer='templates/site-message-edit.html',
             permission='administer')
def admin_edit_site_message_POST(request):
    message_id = request.matchdict['id']
    args = parse_message_args(request)
    args['id'] = message_id

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                UPDATE service_state_messages
                SET service_state_id=%(type)s,
                    starts=%(starts)s,
                    ends=%(ends)s,
                    priority=%(priority)s,
                    message=%(message)s
                WHERE id=%(id)s;
                """, args)

    args = admin_edit_site_message(request)
    args['response'] = "Message successfully Updated"
    return args


@view_config(route_name='admin-print-style', request_method='GET',
             renderer='cnxpublishing.views:templates/print-style.html',
             permission='view')
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
             permission='view')
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
                       bpsa.created, ctm.status as state, ctm.traceback
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
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
             permission='view')
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
             renderer='templates/content-status-single.html',
             permission='view')
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
             renderer='templates/content-status-single.html',
             permission='administer')
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
