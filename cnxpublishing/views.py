# -*- coding: utf-8 -*-
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
from pyramid.view import forbidden_view_config, view_config

from . import config
from .exceptions import (
    UserFetchError,
    )
from .db import (
    add_publication,
    poke_publication_state,
    check_publication_state,
    accept_publication_license,
    accept_publication_role,
    upsert_acl, remove_acl,
    upsert_license_requests, remove_license_requests,
    upsert_role_requests, remove_role_requests,
    upsert_users,
    )


@forbidden_view_config()
def forbidden(request):
    if request.path.startswith('/a/'):
        path = request.route_path('login', _query={'redirect': '/a/'})
        return httpexceptions.HTTPFound(location=path)
    return httpexceptions.HTTPForbidden()


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
    epub_upload = request.POST['epub'].file
    try:
        epub = cnxepub.EPUB.from_file(epub_upload)
    except:
        raise httpexceptions.HTTPBadRequest('Format not recognized.')

    settings = request.registry.settings
    # Make a publication entry in the database for status checking
    # the publication. This also creates publication entries for all
    # of the content in the EPUB.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
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
    """This produces JSON data for a user (at ``uid``) to view the license(s)
    they have accepted or will need to accept for a publication (at ``id``).
    """
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
  pd.uuid||'@'||concat_ws('.', pd.major_version, pd.minor_version) \
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
             request_method='POST', accept='application/json')
def post_accept_license(request):
    """Allows the user (at ``uid``) to accept the license(s) for
    a publication (at ``id``).
    """
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

    location = request.route_url('publication-license-acceptance',
                                 id=publication_id, uid=uid)
    # Poke publication to change state.
    state = poke_publication_state(publication_id)
    return httpexceptions.HTTPFound(location=location)


@view_config(route_name='publication-role-acceptance', request_method='GET',
             accept='application/json', renderer='json')
def get_accept_role(request):
    """This produces JSON data for a user (at ``uid``) to view the role(s)
    they have accepted or will need to accept for a publication (at ``id``).
    """
    publication_id = request.matchdict['id']
    user_id = request.matchdict['uid']
    settings = request.registry.settings

    # TODO Verify the accepting user is the one making the request.
    # FIXME Is this an active publication?

    # For each pending document, accept/deny the role.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""
SELECT row_to_json(combined_rows) FROM (
SELECT
  pd.uuid AS id,
  pd.uuid||'@'||concat_ws('.', pd.major_version, pd.minor_version) \
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
             accept='application/json')
def post_accept_role(request):
    """Allows the user (at ``uid``) to accept the role(s) for
    a publication (at ``id``).
    """
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

    location = request.route_url('publication-license-acceptance',
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
            cursor.execute("""\
SELECT l.url
FROM licenses AS l
RIGHT JOIN document_controls AS dc ON (dc.licenseid = l.licenseid)
WHERE dc.uuid = %s""", (uuid_,))
            try:
                license_url = cursor.fetchone()[0]
            except TypeError:  # None value
                # The document_controls record does not exist.
                raise httpexceptions.HTTPNotFound()
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
SELECT uuid, user_id AS uid, accepted AS has_accepted
FROM license_acceptances AS la
WHERE uuid = %s {}
ORDER BY user_id ASC
) as combined_rows""".format(fmt_conditional), args)
            acceptances = [r[0] for r in cursor.fetchall()]

    if user_id is not None:
        acceptances = acceptances[0]
    resp_value = {
        'license_url': license_url,
        'licensors': acceptances,
        }
    return resp_value


@view_config(route_name='license-request',
             permission='publish.assign-acceptance',
             request_method='POST', accept='application/json')
def post_license_request(request):
    """Submission to create a license acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_data = request.json
    license_url = posted_data.get('license_url')
    licensors = posted_data.get('licensors', [])
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE, l.url
FROM document_controls AS dc
LEFT JOIN licenses AS l ON (dc.licenseid = l.licenseid)
WHERE uuid = %s::UUID""", (uuid_,))
            try:
                exists, existing_license_url = cursor.fetchone()
            except TypeError:
                if request.has_permission('publish.create-identifier'):
                    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (uuid_,))
                    exists, existing_license_url = True, None
                else:
                    raise httpexceptions.HTTPNotFound()
            if existing_license_url is None and license_url is None:
                raise httpexceptions.HTTPBadRequest("license_url is required")
            elif (license_url != existing_license_url or
                  existing_license_url is None):
                cursor.execute("""\
UPDATE document_controls AS dc
SET licenseid = l.licenseid FROM licenses AS l
WHERE url = %s and is_valid_for_publication = 't'
RETURNING dc.licenseid""",
                               (license_url,))
                try:
                    valid_licenseid = cursor.fetchone()[0]
                except TypeError:  # None returned
                    raise httpexceptions.HTTPBadRequest("invalid license_url")
            upsert_license_requests(cursor, uuid_, licensors)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='license-request',
             permission='publish.remove-acceptance',
             request_method='DELETE', accept='application/json')
def delete_license_request(request):
    """Submission to remove a license acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_uids = [x['uid'] for x in request.json.get('licensors', [])]
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
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
SELECT uuid, user_id AS uid, role_type AS role, accepted AS has_accepted
FROM role_acceptances AS la
WHERE uuid = %s {}
ORDER BY user_id ASC, role_type ASC
) as combined_rows""".format(fmt_conditional), args)
            acceptances = [r[0] for r in cursor.fetchall()]

            if not acceptances:
                if user_id is not None:
                    raise httpexceptions.HTTPNotFound()
                else:
                    cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s""", (uuid_,))
                    try:
                        cursor.fetchone()[0]
                    except TypeError:  # NoneType
                        raise httpexceptions.HTTPNotFound()

    resp_value = acceptances
    if user_id is not None:
        resp_value = acceptances[0]
    return resp_value


@view_config(route_name='roles-request',
             permission='publish.assign-acceptance',
             request_method='POST', accept='application/json')
def post_roles_request(request):
    """Submission to create a role acceptance request."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted_roles = request.json
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s::UUID""", (uuid_,))
            try:
                exists = cursor.fetchone()[0]
            except TypeError:
                if request.has_permission('publish.create-identifier'):
                    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (uuid_,))
                else:
                    raise httpexceptions.HTTPNotFound()
            try:
                upsert_users(cursor, [r['uid'] for r in posted_roles])
            except UserFetchError as exc:
                raise httpexceptions.HTTPBadRequest(exc.message)
            upsert_role_requests(cursor, uuid_, posted_roles)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='roles-request',
             permission='publish.remove-acceptance',
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


@view_config(route_name='acl-request',
             request_method='GET',
             accept='application/json', renderer='json')
def get_acl(request):
    """Returns the ACL for the given content identified by ``uuid``."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s""", (uuid_,))
            try:
                exists = cursor.fetchone()[0]
            except TypeError:
                raise httpexceptions.HTTPNotFound()
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
SELECT uuid, user_id AS uid, permission
FROM document_acl AS acl
WHERE uuid = %s
ORDER BY user_id ASC, permission ASC
) as combined_rows""", (uuid_,))
            acl = [r[0] for r in cursor.fetchall()]

    return acl


@view_config(route_name='acl-request',
             permission='publish.assign-acl',
             request_method='POST', accept='application/json')
def post_acl_request(request):
    """Submission to create an ACL."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted = request.json
    permissions = [(x['uid'], x['permission'],) for x in posted]
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s::UUID""", (uuid_,))
            try:
                exists = cursor.fetchone()[0]
            except TypeError:
                if request.has_permission('publish.create-identifier'):
                    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (uuid_,))
                else:
                    raise httpexceptions.HTTPNotFound()
            upsert_acl(cursor, uuid_, permissions)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='acl-request',
             permission='publish.remove-acl',
             request_method='DELETE', accept='application/json')
def delete_acl_request(request):
    """Submission to remove an ACL."""
    uuid_ = request.matchdict['uuid']
    settings = request.registry.settings

    posted = request.json
    permissions = [(x['uid'], x['permission'],) for x in posted]
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            remove_acl(cursor, uuid_, permissions)

    resp = request.response
    resp.status_int = 200
    return resp


# ############## #
#   Moderation   #
# ############## #

@view_config(route_name='moderation', request_method='GET',
             accept="application/json",
             renderer='json', permission='moderate')
def get_moderation(request):
    """Return the list of publications that need moderation."""
    settings = request.registry.settings

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
  SELECT id, created, publisher, publication_message,
         (select array_agg(row_to_json(pd))
          from pending_documents as pd
          where pd.publication_id = p.id) AS models
  FROM publications AS p
  WHERE state = 'Waiting for moderation') AS combined_rows""")
            moderations = [x[0] for x in cursor.fetchall()]

    return moderations


@view_config(route_name='moderate', request_method='POST',
             accept="application/json", permission='moderate')
def post_moderation(request):
    settings = request.registry.settings
    db_conn_str = settings[config.CONNECTION_STRING]
    publication_id = request.matchdict['id']
    posted = request.json
    if 'is_accepted' not in posted \
       or not isinstance(posted.get('is_accepted'), bool):
        raise httpexceptions.HTTPBadRequest(
            "Missing or invalid 'is_accepted' value.")
    is_accepted = posted['is_accepted']

    with psycopg2.connect(db_conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            if is_accepted:
                # Give the publisher moderation approval.
                cursor.execute("""\
UPDATE users SET (is_moderated) = ('t')
WHERE username = (SELECT publisher FROM publications
                  WHERE id = %s and state = 'Waiting for moderation')""",
                               (publication_id,))
                # Poke the publication into a state change.
                poke_publication_state(publication_id, cursor)
            else:
                # Reject! And Vacuum properties of the publication
                #   record to /dev/null.
                cursor.execute("""\
UPDATE users SET (is_moderated) = ('f')
WHERE username = (SELECT publisher FROM publications
                  WHERE id = %sand state = 'Waiting for moderation')""",
                               (publication_id,))
                cursor.execute("""\
UPDATE publications SET (epub, state) = (null, 'Rejected')
WHERE id = %s""", (publication_id,))

    return httpexceptions.HTTPAccepted()


# ############ #
#   API Keys   #
# ############ #

@view_config(route_name='api-keys', request_method='GET',
             accept="application/json",
             renderer='json', permission='administer')
def get_api_keys(request):
    """Return the list of API keys."""
    settings = request.registry.settings

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
  SELECT id, key, name, groups FROM api_keys
) AS combined_rows""")
            api_keys = [x[0] for x in cursor.fetchall()]

    return api_keys

# TODO Add CRUD views for API Keys...


# ################### #
#   Admin Interface   #
# ################### #

@view_config(route_name='admin-index', request_method='GET',
             renderer="cnxpublishing:templates/index.html",
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
            ],
        }


@view_config(route_name='admin-moderation', request_method='GET',
             renderer="cnxpublishing:templates/moderations.html",
             permission='moderate')
@view_config(route_name='moderation-rss', request_method='GET',
             renderer="cnxpublishing:templates/moderations.rss",
             permission='view')
def admin_moderations(request):  # pragma: no cover
    return {'moderations': get_moderation(request)}


@view_config(route_name='admin-api-keys', request_method='GET',
             renderer="cnxpublishing:templates/api-keys.html",
             permission='administer')
def admin_api_keys(request):  # pragma: no cover
    # Easter Egg that will invalidate the cache, just hit this page.
    # FIXME Move this logic into the C[R]UD views...
    from .authnz import lookup_api_key_info
    from .main import cache
    cache.invalidate(lookup_api_key_info)

    return {'api_keys': get_api_keys(request)}
