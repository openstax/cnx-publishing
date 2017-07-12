# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import
from datetime import datetime, timedelta
from re import compile, match

import psycopg2
from celery.result import AsyncResult
from pyramid import httpexceptions
from pyramid.view import view_config

from cnxarchive.utils.ident_hash import IdentHashError
from .. import config
from .moderation import get_moderation
from .api_keys import get_api_keys

STATE_ICONS = {
    "SUCCESS": {'class': 'fa fa-check-square',
                'style': 'font-size:20px;color:limeGreen'},
    "STARTED": {'class': 'fa fa-exclamation-triangle',
                'style': 'font-size:20px;color:gold'},
    "PENDING": {'class': 'fa fa-exclamation-triangle',
                'style': 'font-size:20px;color:gold'},
    "RETRY": {'class': 'a fa-close',
              'style': 'font-size:20px;color:red'},
    "FAILURE": {'class': 'fa fa-close',
                'style': 'font-size:20px;color:red'}}
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
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    states = []
    with psycopg2.connect(db_conn_str) as db_conn:
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
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    banners = []
    with psycopg2.connect(db_conn_str) as db_conn:
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

    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

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
    with psycopg2.connect(db_conn_str) as db_conn:
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
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    message_id = request.body.split("=")[1]
    with psycopg2.connect(db_conn_str) as db_conn:
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

    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    with psycopg2.connect(db_conn_str) as db_conn:
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

    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]

    with psycopg2.connect(db_conn_str) as db_conn:
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


def get_baking_statuses_sql(request):
    args = {}
    sort = request.GET.get('sort', 'bpsa.created DESC')
    if (len(sort.split(" ")) != 2 or
            sort.split(" ")[0] not in SORTS_DICT.keys() or
            sort.split(" ")[1] not in ARROW_MATCH.keys()):
        raise httpexceptions.HTTPBadRequest(
            'invalid sort: {}'.format(sort))
    if sort == "STATE ASC" or sort == "STATE DESC":
        sort = 'bpsa.created DESC'
    uuid_filter = request.GET.get('uuid', '')
    author_filter = request.GET.get('author', '')

    sql_filters = "WHERE"
    if uuid_filter != '':
        args['uuid'] = uuid_filter
        sql_filters += " m.uuid=%(uuid)s AND "
    if author_filter != '':
        author_filter = author_filter.decode('utf-8')
        sql_filters += "%(author)s=ANY(m.authors) "
        args["author"] = author_filter

    if sql_filters.endswith("AND "):
        sql_filters = sql_filters[:-4]
    if sql_filters == "WHERE":
        sql_filters = ""

    statement = """
                SELECT m.name, m.authors, m.uuid, m.print_style,
                       ps.fileid as latest_recepie,  m.recipe,
                       lm.version as latest_version, m.version,
                       bpsa.created, bpsa.result_id::text
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
                LEFT JOIN print_style_recipes as ps
                    ON ps.print_style=m.print_style
                LEFT JOIN latest_modules as lm
                    ON lm.uuid=m.uuid
                {}
                ORDER BY {};
                """.format(sql_filters, sort)
    args.update({'sort': sort})
    return statement, args


def format_autors(authors):
    if len(authors) == 0:
        return ""
    return_str = ""
    for author in authors:
        return_str += author.decode('utf-8') + ", "
    return return_str[:-2]


@view_config(route_name='admin-content-status', request_method='GET',
             renderer='cnxpublishing.views:templates/content-status.html',
             permission='administer')
def admin_content_status(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]
    statement, args = get_baking_statuses_sql(request)
    states = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute(statement, vars=args)
            for row in cursor.fetchall():
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback.split("\n")[-2]
                latest_recepie = row[4]
                current_recepie = row[5]
                latest_version = row[6]
                current_version = row[7]
                state = str(result.state)
                if current_version != latest_version:
                    state += ' stale_content'
                if current_recepie != latest_recepie:
                    state += ' stale_recipie'
                state_icon = result.state
                if state[:7] == "SUCCESS" and len(state) > 7:
                    state_icon = 'PENDING'
                states.append({
                    'title': row[0].decode('utf-8'),
                    'authors': format_autors(row[1]),
                    'uuid': row[2],
                    'print_style': row[3],
                    'recipe': row[4],
                    'created': row[-2],
                    'state': state,
                    'state_message': message,
                    'state_icon': STATE_ICONS[state_icon]['class'],
                    'state_icon_style': STATE_ICONS[state_icon]['style']
                })
    status_filters = [request.GET.get('pending_filter', ''),
                      request.GET.get('started_filter', ''),
                      request.GET.get('retry_filter', ''),
                      request.GET.get('failure_filter', ''),
                      request.GET.get('success_filter', '')]
    status_filters = [x for x in status_filters if x != '']
    if status_filters == []:
        status_filters = ["PENDING", "STARTED", "RETRY", "FAILURE", "SUCCESS"]
    for f in (status_filters):
        args[f] = "checked"
    final_states = []
    for state in states:
        if state['state'].split(' ')[0] in status_filters:
            final_states.append(state)

    sort = request.GET.get('sort', 'bpsa.created DESC')
    sort_match = SORTS_DICT[sort.split(' ')[0]]
    args['sort_' + sort_match] = ARROW_MATCH[sort.split(' ')[1]]
    args['sort'] = sort
    if sort == "STATE ASC":
        final_states = sorted(final_states, key=lambda x: x['state'])
    if sort == "STATE DESC":
        final_states = sorted(final_states,
                              key=lambda x: x['state'], reverse=True)

    num_entries = request.GET.get('number', 100)
    page = request.GET.get('page', 1)
    try:
        page = int(page)
        num_entries = int(num_entries)
        start_entry = (page - 1) * num_entries
    except ValueError:
        raise httpexceptions.HTTPBadRequest(
            'invalid page({}) or entries per page({})'.
            format(page, num_entries))
    final_states = final_states[start_entry: start_entry + num_entries]
    args.update({'start_entry': start_entry,
                 'num_entries': num_entries,
                 'page': page,
                 'total_entries': len(final_states)})

    args.update({'states': final_states})
    return args


@view_config(route_name='admin-content-status-single', request_method='GET',
             renderer='templates/content-status-single.html',
             permission='administer')
def admin_content_status_single(request):
    uuid = request.matchdict['uuid']
    pat = ("[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}$")
    if not compile(pat).match(uuid):
        raise httpexceptions.HTTPBadRequest(
            '{} is not a valid uuid'.format(uuid))

    settings = request.registry.settings
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT m.name, m.authors, m.uuid, m.print_style,
                       ps.fileid as latest_recepie,  m.recipe,
                       lm.version as latest_version, m.version,
                       m.module_ident,
                       bpsa.created, bpsa.result_id::text
                FROM document_baking_result_associations AS bpsa
                INNER JOIN modules AS m USING (module_ident)
                LEFT JOIN print_style_recipes as ps
                    ON ps.print_style=m.print_style
                LEFT JOIN latest_modules as lm
                ON lm.uuid=m.uuid
                WHERE m.uuid=%s ORDER BY bpsa.created DESC;
                """, vars=(uuid,))
            modules = cursor.fetchall()
            if len(modules) == 0:
                raise httpexceptions.HTTPBadRequest(
                    '{} is not a book'.format(uuid))

            states = []
            row = modules[0]
            args = {'uuid': str(row[2]),
                    'title': row[0].decode('utf-8'),
                    'authors': format_autors(row[1]),
                    'print_style': row[3],
                    'current_recipie': row[4],
                    'current_ident': row[8]}

            for row in modules:
                message = ''
                result_id = row[-1]
                result = AsyncResult(id=result_id)
                if result.failed():  # pragma: no cover
                    message = result.traceback
                latest_recepie = row[4]
                current_recepie = row[5]
                latest_version = row[6]
                current_version = row[7]
                state = result.state
                if current_recepie != latest_recepie:
                    state += ' stale_recipie'
                if current_version != latest_version:
                    state += ' stale_content'
                states.append({
                    'version': row[7],
                    'recipe': row[5],
                    'created': str(row[-2]),
                    'state': state,
                    'state_message': message,
                })
            args['current_state'] = states[0]['state']
            args['states'] = states
            return args


@view_config(route_name='admin-content-status-single-POST',
             request_method='POST',
             renderer='templates/content-status-single.html',
             permission='administer')
def admin_content_status_single_POST(request):
    args = admin_content_status_single(request)
    title = args['title']
    if args['current_state'] == 'SUCCESS':
        args['response'] = title + ' is not stale, no need to bake'
        return args

    settings = request.registry.settings
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("SELECT stateid FROM modules WHERE module_ident=%s",
                           vars=(args['current_ident'],))
            data = cursor.fetchall()
            if len(data) == 0:
                raise httpexceptions.HTTPBadRequest(
                    'invalid module_ident: {}'.format(args['current_ident']))
            if data[0][0] == 5:
                args['response'] = title + ' is already baking/set to bake'
                return args

            cursor.execute("""UPDATE modules SET stateid=5
                           WHERE module_ident=%s""",
                           vars=(args['current_ident'],))

            args['response'] = title + " set to bake!"

    return args
