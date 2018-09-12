# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
# ################ #
#   User Actions   #
# ################ #
from pyramid import httpexceptions
from pyramid.view import view_config

from ..exceptions import (
    UserFetchError,
)
from ..db import (
    db_connect,
    remove_acl,
    remove_license_requests,
    remove_role_requests,
    upsert_acl,
    upsert_license_requests,
    upsert_role_requests,
    upsert_users,
)


@view_config(route_name='license-request',
             request_method='GET',
             accept='application/json', renderer='json', http_cache=0)
def get_license_request(request):
    """Returns a list of those accepting the license."""
    uuid_ = request.matchdict['uuid']
    user_id = request.matchdict.get('uid')

    args = [uuid_]
    if user_id is not None:
        fmt_conditional = "AND user_id = %s"
        args.append(user_id)
    else:
        fmt_conditional = ""

    with db_connect() as db_conn:
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
             request_method='POST', accept='application/json', http_cache=0)
def post_license_request(request):
    """Submission to create a license acceptance request."""
    uuid_ = request.matchdict['uuid']

    posted_data = request.json
    license_url = posted_data.get('license_url')
    licensors = posted_data.get('licensors', [])
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT l.url
FROM document_controls AS dc
LEFT JOIN licenses AS l ON (dc.licenseid = l.licenseid)
WHERE uuid = %s::UUID""", (uuid_,))
            try:
                # Check that the license exists
                existing_license_url = cursor.fetchone()[0]
            except TypeError:  # NoneType
                if request.has_permission('publish.create-identifier'):
                    cursor.execute("""\
INSERT INTO document_controls (uuid) VALUES (%s)""", (uuid_,))
                    existing_license_url = None
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
                    # Check that it is a valid license id
                    cursor.fetchone()[0]
                except TypeError:  # None returned
                    raise httpexceptions.HTTPBadRequest("invalid license_url")
            upsert_license_requests(cursor, uuid_, licensors)

    resp = request.response
    resp.status_int = 202
    return resp


@view_config(route_name='license-request',
             permission='publish.remove-acceptance',
             request_method='DELETE', accept='application/json', http_cache=0)
def delete_license_request(request):
    """Submission to remove a license acceptance request."""
    uuid_ = request.matchdict['uuid']

    posted_uids = [x['uid'] for x in request.json.get('licensors', [])]
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            remove_license_requests(cursor, uuid_, posted_uids)

    resp = request.response
    resp.status_int = 200
    return resp


@view_config(route_name='roles-request',
             request_method='GET',
             accept='application/json', renderer='json', http_cache=0)
def get_roles_request(request):
    """Returns a list of accepting roles."""
    uuid_ = request.matchdict['uuid']
    user_id = request.matchdict.get('uid')

    args = [uuid_]
    if user_id is not None:
        fmt_conditional = "AND user_id = %s"
        args.append(user_id)
    else:
        fmt_conditional = ""

    with db_connect() as db_conn:
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
             request_method='POST', accept='application/json', http_cache=0)
def post_roles_request(request):
    """Submission to create a role acceptance request."""
    uuid_ = request.matchdict['uuid']

    posted_roles = request.json
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s::UUID""", (uuid_,))
            try:
                # Check that it exists
                cursor.fetchone()[0]
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
             request_method='DELETE', accept='application/json', http_cache=0)
def delete_roles_request(request):
    """Submission to remove a role acceptance request."""
    uuid_ = request.matchdict['uuid']

    posted_roles = request.json
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            remove_role_requests(cursor, uuid_, posted_roles)

    resp = request.response
    resp.status_int = 200
    return resp


@view_config(route_name='acl-request',
             request_method='GET',
             accept='application/json', renderer='json', http_cache=0)
def get_acl(request):
    """Returns the ACL for the given content identified by ``uuid``."""
    uuid_ = request.matchdict['uuid']

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s""", (uuid_,))
            try:
                # Check that it exists
                cursor.fetchone()[0]
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
             request_method='POST', accept='application/json', http_cache=0)
def post_acl_request(request):
    """Submission to create an ACL."""
    uuid_ = request.matchdict['uuid']

    posted = request.json
    permissions = [(x['uid'], x['permission'],) for x in posted]
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT TRUE FROM document_controls WHERE uuid = %s::UUID""", (uuid_,))
            try:
                # Check that it exists
                cursor.fetchone()[0]
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
             request_method='DELETE', accept='application/json', http_cache=0)
def delete_acl_request(request):
    """Submission to remove an ACL."""
    uuid_ = request.matchdict['uuid']

    posted = request.json
    permissions = [(x['uid'], x['permission'],) for x in posted]
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            remove_acl(cursor, uuid_, permissions)

    resp = request.response
    resp.status_int = 200
    return resp
