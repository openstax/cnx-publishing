5# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import cnxepub
import psycopg2
from pyramid import httpexceptions
from pyramid.settings import asbool
from pyramid.view import view_config

from . import config
from .db import (
    add_publication,
    poke_publication_state,
    check_publication_state,
    accept_publication_license,
    accept_publication_role,
    upsert_license_requests,
    remove_license_requests,
    upsert_role_requests,
    remove_role_requests,
    )


# ############## #
#   Publishing   #
# ############## #

@view_config(route_name='publications', request_method='POST', renderer='json',
             permission='publish')
def publish(request):
    """Accept a publication request at form value 'epub'"""
    if 'epub' not in request.POST:
        raise httpexceptions.HTTPBadRequest("Missing EPUB in POST body.")

    is_pre_publication = asbool(request.POST.get('pre-publication'))
    epub_upload = request.POST['epub']
    try:
        epub = cnxepub.EPUB.from_file(epub_upload.file)
    except:
        raise httpexceptions.HTTPBadRequest('Format not recognized.')

    settings = request.registry.settings
    # Make a publication entry in the database for status checking
    # the publication. This also creates publication entries for all
    # of the content in the EPUB.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            publication_id, publications = add_publication(
                cursor, epub, epub_upload.file, is_pre_publication)

    # Poke at the publication & lookup its state.
    state, messages = poke_publication_state(publication_id)

    response_data = {
        'publication': publication_id,
        'mapping': publications,
        'state': state,
        'messages': messages,
        }
    return response_data


@view_config(route_name='get-publication', request_method=['GET', 'HEAD'],
             renderer='json', permission='view')
def get_publication(request):
    """Lookup publication state"""
    publication_id = request.matchdict['id']
    state, messages = check_publication_state(publication_id)
    response_data = {
        'publication': publication_id,
        'state': state,
        'messages': messages,
        }
    return response_data


@view_config(route_name='publication-license-acceptance',
             request_method='GET',
             accept='application/json', renderer='json')
def get_accept_license(request):
    """This produces an HTML form for accepting the license."""
    publication_id = request.matchdict['id']
    user_id = request.matchdict['uid']
    settings = request.registry.settings

    # FIXME Is this an active publication?
    # TODO Verify the accepting user is the one making the request.

    # For each pending document, accept the license.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT
  pd.uuid AS id,
  pd.uuid||'@'||concat_ws('.', pd.major_version, pd.minor_version) AS ident_hash,
  accepted AS is_accepted
FROM
  pending_documents AS pd
  NATURAL JOIN license_acceptances AS la
WHERE pd.publication_id = %s AND user_id = %s
) as combined_rows;""",
                           (publication_id, user_id))
            user_documents = [r[0] for r in cursor.fetchall()]

    return {'publication_id': publication_id,
            'user_id': user_id,
            'documents': user_documents,
            }


@view_config(route_name='publication-license-acceptance',
             request_method='POST', accept='application/json')
def post_accept_license(request):
    """Accept license acceptance requests."""
    publication_id = request.matchdict['id']
    uid = request.matchdict['uid']
    settings = request.registry.settings

    # TODO Verify the accepting user is the one making the request.
    #      They could be authenticated but not be the license acceptor.

    post_data = request.json
    accepted = []
    denied = []
    try:
        documents = post_data['documents']
        for doc_acceptance in documents:
            if doc_acceptance['is_accepted'] is None:
                continue
            elif doc_acceptance['is_accepted']:
                accepted.append(doc_acceptance['id'])
            else:
                denied.append(doc_acceptance['id'])
    except:
        raise httpexception.BadRequest("Posted data is invalid.")

    # For each pending document, accept/deny the license.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            accept_publication_license(cursor, publication_id, uid,
                                       accepted, True)
            accept_publication_license(cursor, publication_id, uid,
                                       denied, False)

    location = request.route_url('license-acceptance',
                                 id=publication_id, uid=uid)
    # Poke publication to change state.
    state = poke_publication_state(publication_id)
    return httpexceptions.HTTPFound(location=location)


@view_config(route_name='publication-role-acceptance', request_method='GET',
             accept='application/json', renderer='json')
def get_accept_role(request):
    """This produces an HTML form for accepting the license."""
    publication_id = request.matchdict['id']
    user_id = request.matchdict['uid']
    settings = request.registry.settings

    # FIXME Is this an active publication?
    # TODO Verify the accepting user is the one making the request.

    # For each pending document, accept/deny the role.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT
  pd.uuid AS id,
  pd.uuid||'@'||concat_ws('.', pd.major_version, pd.minor_version) AS ident_hash,
  accepted AS is_accepted
FROM
  pending_documents AS pd
  JOIN role_acceptances AS ra ON (pd.uuid = ra.uuid)
WHERE
  pd.publication_id = %s
  AND
  user_id = %s
) as combined_rows;""",
                           (publication_id, user_id))
            user_documents = [r[0] for r in cursor.fetchall()]

    return {'publication_id': publication_id,
            'user_id': user_id,
            'documents': user_documents,
            }


@view_config(route_name='publication-role-acceptance', request_method='POST',
             accept='application/json')
def post_accept_role(request):
    """Accept license acceptance requests."""
    publication_id = request.matchdict['id']
    uid = request.matchdict['uid']
    settings = request.registry.settings

    # TODO Verify the accepting user is the one making the request.
    #      They could be authenticated but not be the license acceptor.

    post_data = request.json
    accepted = []
    denied = []
    try:
        documents = post_data['documents']
        for doc_acceptance in documents:
            if doc_acceptance['is_accepted'] is None:
                continue
            elif doc_acceptance['is_accepted']:
                accepted.append(doc_acceptance['id'])
            else:
                denied.append(doc_acceptance['id'])
    except:
        raise httpexception.BadRequest("Posted data is invalid.")

    # For each pending document, accept/deny the license.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            accept_publication_role(cursor, publication_id, uid,
                                       accepted, True)
            accept_publication_role(cursor, publication_id, uid,
                                       denied, False)

    location = request.route_url('license-acceptance',
                                 id=publication_id, uid=uid)
    # Poke publication to change state.
    state = poke_publication_state(publication_id)
    return httpexceptions.HTTPFound(location=location)


# ################ #
#   User Actions   #
# ################ #

@view_config(route_name='license-request',
             request_method='GET',
             accept='application/json', renderer='json')
def get_license_request(request):
    """Returns a list of those accepting the license."""
    uuid_ = request.matchdict['uuid']
    user_id = request.matchdict.get('uid')
    settings = request.registry.settings

    args = [uuid_]
    if user_id is not None:
        fmt_conditional = "AND user_id = %s"
        args.append(user_id)
    else:
        fmt_conditional = ""

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT uuid, user_id AS uid, accepted AS has_accepted
FROM license_acceptances AS la
WHERE uuid = %s {}
ORDER BY user_id ASC
) as combined_rows""".format(fmt_conditional), args)
            acceptances = [r[0] for r in cursor.fetchall()]

    if not acceptances:
        raise httpexceptions.HTTPNotFound()

    resp_value = acceptances
    if user_id is not None:
        resp_value = acceptances[0]
    return resp_value


@view_config(route_name='license-request',
             request_method='POST', accept='application/json')
def post_license_request(request):
    """Submission to create a license acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_uids = request.json
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            upsert_license_requests(cursor, uuid_, posted_uids)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='license-request',
             request_method='DELETE', accept='application/json')
def delete_license_request(request):
    """Submission to remove a license acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_uids = request.json
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            remove_license_requests(cursor, uuid_, posted_uids)

    resp = request.response
    resp.status_int = 200
    return resp


@view_config(route_name='roles-request',
             request_method='GET',
             accept='application/json', renderer='json')
def get_roles_request(request):
    """Returns a list of accepting roles."""
    uuid_ = request.matchdict['uuid']
    user_id = request.matchdict.get('uid')
    settings = request.registry.settings

    args = [uuid_]
    if user_id is not None:
        fmt_conditional = "AND user_id = %s"
        args.append(user_id)
    else:
        fmt_conditional = ""

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT uuid, user_id AS uid, role_type AS role, accepted AS has_accepted
FROM role_acceptances AS la
WHERE uuid = %s {}
ORDER BY user_id ASC, role_type ASC
) as combined_rows""".format(fmt_conditional), args)
            acceptances = [r[0] for r in cursor.fetchall()]

    if not acceptances:
        raise httpexceptions.HTTPNotFound()

    resp_value = acceptances
    if user_id is not None:
        resp_value = acceptances[0]
    return resp_value


@view_config(route_name='roles-request',
             request_method='POST', accept='application/json')
def post_roles_request(request):
    """Submission to create a role acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_roles = request.json
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            upsert_role_requests(cursor, uuid_, posted_roles)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='roles-request',
             request_method='DELETE', accept='application/json')
def delete_roles_request(request):
    """Submission to remove a role acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_roles = request.json
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            remove_role_requests(cursor, uuid_, posted_roles)

    resp = request.response
    resp.status_int = 200
    return resp
