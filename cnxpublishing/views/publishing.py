# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import cnxepub
from cnxdb.ident_hash import IdentHashError
from pyramid import httpexceptions
from pyramid.settings import asbool
from pyramid.view import view_config

from ..db import (
    accept_publication_license,
    accept_publication_role,
    add_publication,
    check_publication_state,
    poke_publication_state,
    db_connect,
)
from ..utils import split_ident_hash


@view_config(route_name='publications', request_method='POST', renderer='json',
             permission='publish', http_cache=0)
def publish(request):
    """Accept a publication request at form value 'epub'"""
    if 'epub' not in request.POST:
        raise httpexceptions.HTTPBadRequest("Missing EPUB in POST body.")

    is_pre_publication = asbool(request.POST.get('pre-publication'))
    epub_upload = request.POST['epub'].file
    try:
        epub = cnxepub.EPUB.from_file(epub_upload)
    except:  # noqa: E722
        raise httpexceptions.HTTPBadRequest('Format not recognized.')

    # Make a publication entry in the database for status checking
    # the publication. This also creates publication entries for all
    # of the content in the EPUB.
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            epub_upload.seek(0)
            publication_id, publications = add_publication(
                cursor, epub, epub_upload, is_pre_publication)

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
             renderer='json', permission='view', http_cache=0)
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
             accept='application/json', renderer='json', http_cache=0)
def get_accept_license(request):
    """This produces JSON data for a user (at ``uid``) to view the license(s)
    they have accepted or will need to accept for a publication (at ``id``).
    """
    publication_id = request.matchdict['id']
    user_id = request.matchdict['uid']

    # FIXME Is this an active publication?
    # TODO Verify the accepting user is the one making the request.

    # For each pending document, accept the license.
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT
  pd.uuid AS id,
  ident_hash(pd.uuid, pd.major_version, pd.minor_version) \
    AS ident_hash,
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
             request_method='POST', accept='application/json', http_cache=0)
def post_accept_license(request):
    """Allows the user (at ``uid``) to accept the license(s) for
    a publication (at ``id``).
    """
    publication_id = request.matchdict['id']
    uid = request.matchdict['uid']

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
    except KeyError:
        raise httpexceptions.BadRequest("Posted data is invalid.")

    # For each pending document, accept/deny the license.
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            accept_publication_license(cursor, publication_id, uid,
                                       accepted, True)
            accept_publication_license(cursor, publication_id, uid,
                                       denied, False)

    location = request.route_url('publication-license-acceptance',
                                 id=publication_id, uid=uid)
    # Poke publication to change state.
    poke_publication_state(publication_id)
    return httpexceptions.HTTPFound(location=location)


@view_config(route_name='publication-role-acceptance', request_method='GET',
             accept='application/json', renderer='json', http_cache=0)
def get_accept_role(request):
    """This produces JSON data for a user (at ``uid``) to view the role(s)
    they have accepted or will need to accept for a publication (at ``id``).
    """
    publication_id = request.matchdict['id']
    user_id = request.matchdict['uid']

    # TODO Verify the accepting user is the one making the request.
    # FIXME Is this an active publication?

    # For each pending document, accept/deny the role.
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT
  pd.uuid AS id,
  ident_hash(pd.uuid, pd.major_version, pd.minor_version) \
    AS ident_hash,
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
             accept='application/json', http_cache=0)
def post_accept_role(request):
    """Allows the user (at ``uid``) to accept the role(s) for
    a publication (at ``id``).
    """
    publication_id = request.matchdict['id']
    uid = request.matchdict['uid']

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
    except KeyError:
        raise httpexceptions.BadRequest("Posted data is invalid.")

    # For each pending document, accept/deny the license.
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            accept_publication_role(cursor, publication_id, uid,
                                    accepted, True)
            accept_publication_role(cursor, publication_id, uid,
                                    denied, False)

    location = request.route_url('publication-license-acceptance',
                                 id=publication_id, uid=uid)
    # Poke publication to change state.
    poke_publication_state(publication_id)
    return httpexceptions.HTTPFound(location=location)


@view_config(route_name='collate-content', request_method='POST',
             renderer='json', permission='publish', http_cache=0)
@view_config(route_name='bake-content', request_method='POST',
             renderer='json', permission='publish', http_cache=0)
def bake_content(request):
    """Invoke the baking process - trigger post-publication"""
    ident_hash = request.matchdict['ident_hash']
    try:
        id, version = split_ident_hash(ident_hash)
    except IdentHashError:
        raise httpexceptions.HTTPNotFound()

    if not version:
        raise httpexceptions.HTTPBadRequest('must specify the version')

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT bool(portal_type = 'Collection'), stateid, module_ident
FROM modules
WHERE ident_hash(uuid, major_version, minor_version) = %s
""", (ident_hash,))
            try:
                is_binder, stateid, module_ident = cursor.fetchone()
            except TypeError:
                raise httpexceptions.HTTPNotFound()
            if not is_binder:
                raise httpexceptions.HTTPBadRequest(
                    '{} is not a book'.format(ident_hash))

            if stateid == 5:
                cursor.execute("""\
SELECT pg_notify('post_publication',
'{"module_ident": '||%s||',
  "ident_hash": "'||%s||'",
  "timestamp": "'||CURRENT_TIMESTAMP||'"}')
""", (module_ident, ident_hash))
            else:
                cursor.execute("""\
UPDATE modules SET stateid = 5
WHERE ident_hash(uuid, major_version, minor_version) = %s
""", (ident_hash,))
