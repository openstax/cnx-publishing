# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import absolute_import

from datetime import datetime, timedelta

import psycopg2
from celery.result import AsyncResult
from pyramid import httpexceptions
from pyramid.view import view_config

from .. import config
from .moderation import get_moderation
from .api_keys import get_api_keys


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
            {'name': 'Print Styles',
             'uri': request.route_url('admin-print-style'),
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


@view_config(route_name='admin-print-style', request_method='GET',
             renderer='cnxpublishing.views:templates/print-style.html',
             permission='administer')
def admin_print_styles(request):
    """
    Returns a dictionary of all unique print_styles, and their latest tag,
    revision, and recipe_type.
    """
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]
    styles = []
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
                SELECT print_style, max(recipe_type),
                    max(revised), max(tag),
                    (SELECT count (*) from latest_modules as lm
                        where lm.print_style=ps.print_style
                            and lm.portal_type='Collection')
                FROM print_style_recipes as ps
                GROUP BY print_style;""")
            for row in cursor.fetchall():
                styles.append({
                    'print_style': row[0],
                    'type': row[1],
                    'revised': row[2],
                    'tag': row[3],
                    'number': row[4],
                    'link': request.route_path('admin-print-style-single',
                                               style=row[0])
                })
    return {'styles': styles}


@view_config(route_name='admin-print-style-single', request_method='GET',
             renderer='cnxpublishing.views:templates/print-style-single.html',
             permission='administer')
def admin_print_styles_single(request):
    """ Returns all books with any version of the given print style.

    Returns the print_style, recipe type, num books using the print_style,
    along with a dictionary of the book, author, revision date, recipie,
    tag of the print_style, and a link to the content.
    """
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]
    style = request.matchdict['style']
    args = {}
    # do db search to get file id and other info on the print_style
    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
                SELECT fileid, recipe_type
                FROM print_style_recipes
                WHERE print_style=%s
                ORDER BY revised DESC;
                """, vars=(style,))
            info = cursor.fetchall()
            if len(info) < 1:
                raise httpexceptions.HTTPNotFound(
                    'Invalid Print Style: {}'.format(style))
            current_recipe = info[0][0]
            recipe_type = info[0][1]

            collections = []
            cursor.execute("""\
                SELECT name, authors, lm.revised, lm.recipe, psr.tag,
                    ident_hash(uuid, major_version, minor_version)
                FROM latest_modules as lm
                JOIN print_style_recipes as psr
                ON (psr.print_style = lm.print_style and
                    psr.fileid = lm.recipe)
                WHERE lm.print_style=%s
                AND portal_type='Collection'
                ORDER BY psr.tag DESC;
                """, vars=(style,))
            for row in cursor.fetchall():
                recipe = row[3]
                status = 'current'
                if recipe != current_recipe:
                    status = 'stale'
                collections.append({
                    'title': row[0].decode('utf-8'),
                    'authors': row[1],
                    'revised': row[2],
                    'recipe': row[3],
                    'tag': row[4],
                    'ident_hash': row[-1],
                    'link': request.route_path('get-content',
                                               ident_hash=row[-1]),
                    'status': status,

                })
    return {'number': len(collections),
            'collections': collections,
            'print_style': style,
            'recipe_type': recipe_type}
