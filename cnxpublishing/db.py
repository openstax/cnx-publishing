# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from __future__ import print_function
import contextlib
import sys
import io
import functools
import json

import cnxepub
import psycopg2
import jinja2
from cnxdb.ident_hash import IdentHashSyntaxError, IdentHashShortId
from cnxepub import ATTRIBUTED_ROLE_KEYS
from openstax_accounts.interfaces import IOpenstaxAccounts
from psycopg2.extras import register_uuid
from pyramid.threadlocal import (
    get_current_request, get_current_registry,
)

from . import exceptions
from .config import CONNECTION_STRING
from .exceptions import (
    DocumentLookupError,
    ResourceFileExceededLimitError,
    UserFetchError,
)
from .utils import (
    parse_archive_uri,
    parse_user_uri,
    join_ident_hash,
    split_ident_hash,
)


END_N_INTERIM_STATES = ('Publishing', 'Done/Success',
                        'Failed/Error', 'Rejected',)
# FIXME psycopg2 UUID adaptation doesn't seem to be registering
# itself. Temporarily call it directly.
register_uuid()


@contextlib.contextmanager
def db_connect(connection_string=None, **kwargs):
    """Function to supply a database connection object."""
    if connection_string is None:
        connection_string = get_current_registry().settings[CONNECTION_STRING]
    db_conn = psycopg2.connect(connection_string, **kwargs)
    try:
        with db_conn:
            yield db_conn
    finally:
        db_conn.close()


def with_db_cursor(func):
    """Decorator that supplies a cursor to the function.
    This passes in a psycopg2 Cursor as the argument 'cursor'.
    It also accepts a cursor if one is given.
    """

    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        if 'cursor' in kwargs or func.func_code.co_argcount == len(args):
            return func(*args, **kwargs)
        with db_connect() as db_connection:
            with db_connection.cursor() as cursor:
                kwargs['cursor'] = cursor
                return func(*args, **kwargs)

    return wrapped


# FIXME Cache the database query in this function. Cache for forever.
# TODO Move to cnx-archive.
def acquire_subject_vocabulary(cursor):
    """Acquire a list of term and identifier values.
    Returns a list of tuples containing the term and the subject identifier.
    """
    cursor.execute("""SELECT tag, tagid FROM tags WHERE tagid != 0""")
    return cursor.fetchall()


# FIXME Cache the database query in this function. Cache for forever.
def _role_type_to_db_type(type_):
    """Translates a role type (a value found in
    ``cnxepub.ATTRIBUTED_ROLE_KEYS``) to a database compatible
    value for ``role_types``.
    """
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
WITH unnested_role_types AS (
  SELECT unnest(enum_range(NULL::role_types)) as role_type
  ORDER BY role_type ASC)
SELECT array_agg(role_type)::text[] FROM unnested_role_types""")
            db_types = cursor.fetchone()[0]
    return dict(zip(cnxepub.ATTRIBUTED_ROLE_KEYS, db_types))[type_]


def _dissect_roles(metadata):
    """Given a model's ``metadata``, iterate over the roles.
    Return values are the role identifier and role type as a tuple.
    """
    for role_key in cnxepub.ATTRIBUTED_ROLE_KEYS:
        for user in metadata.get(role_key, []):
            if user['type'] != 'cnx-id':
                raise ValueError("Archive only accepts Connexions users.")
            uid = parse_user_uri(user['id'])
            yield uid, role_key
    raise StopIteration()


def upsert_pending_licensors(cursor, document_id):
    """Update or insert records for pending license acceptors."""
    cursor.execute("""\
SELECT "uuid", "metadata"
FROM pending_documents
WHERE id = %s""", (document_id,))
    uuid_, metadata = cursor.fetchone()
    acceptors = set([uid for uid, type_ in _dissect_roles(metadata)])

    # Acquire a list of existing acceptors.
    cursor.execute("""\
SELECT "user_id", "accepted"
FROM license_acceptances
WHERE uuid = %s""", (uuid_,))
    existing_acceptors_mapping = dict(cursor.fetchall())

    # Who's not in the existing list?
    existing_acceptors = set(existing_acceptors_mapping.keys())
    new_acceptors = acceptors.difference(existing_acceptors)

    # Insert the new licensor acceptors.
    for acceptor in new_acceptors:
        cursor.execute("""\
INSERT INTO license_acceptances
  ("uuid", "user_id", "accepted")
VALUES (%s, %s, NULL)""", (uuid_, acceptor,))

    # Has everyone already accepted?
    cursor.execute("""\
SELECT user_id
FROM license_acceptances
WHERE
  uuid = %s
  AND
  (accepted is UNKNOWN OR accepted is FALSE)""", (uuid_,))
    defectors = set(cursor.fetchall())

    if not defectors:
        # Update the pending document license acceptance state.
        cursor.execute("""\
update pending_documents set license_accepted = 't'
where id = %s""", (document_id,))


def upsert_pending_roles(cursor, document_id):
    """Update or insert records for pending document role acceptance."""
    cursor.execute("""\
SELECT "uuid", "metadata"
FROM pending_documents
WHERE id = %s""", (document_id,))
    uuid_, metadata = cursor.fetchone()

    acceptors = set([(uid, _role_type_to_db_type(type_),)
                     for uid, type_ in _dissect_roles(metadata)])

    # Upsert the user info.
    upsert_users(cursor, [x[0] for x in acceptors])

    # Acquire a list of existing acceptors.
    cursor.execute("""\
SELECT user_id, role_type
FROM role_acceptances
WHERE uuid = %s""", (uuid_,))
    existing_roles = set([(r, t,) for r, t in cursor.fetchall()])

    # Who's not in the existing list?
    existing_acceptors = existing_roles
    new_acceptors = acceptors.difference(existing_acceptors)

    # Insert the new role acceptors.
    for acceptor, type_ in new_acceptors:
        cursor.execute("""\
INSERT INTO role_acceptances
  ("uuid", "user_id", "role_type", "accepted")
        VALUES (%s, %s, %s, DEFAULT)""", (uuid_, acceptor, type_))

    # Has everyone already accepted?
    cursor.execute("""\
SELECT user_id
FROM role_acceptances
WHERE
  uuid = %s
  AND
  (accepted is UNKNOWN OR accepted is FALSE)""", (uuid_,))
    defectors = set(cursor.fetchall())

    if not defectors:
        # Update the pending document license acceptance state.
        cursor.execute("""\
update pending_documents set roles_accepted = 't'
where id = %s""", (document_id,))


def _get_type_name(model):
    """Returns a type name of 'Document' or 'Binder' based model's type."""
    if isinstance(model, cnxepub.Binder):
        return 'Binder'
    else:
        return 'Document'


def add_pending_resource(cursor, resource, document=None):
    settings = get_current_registry().settings
    args = {
        'media_type': resource.media_type,
        'hash': resource.hash,
        'filename': resource.filename,
    }
    with resource.open() as data:
        upload_limit = settings['file_upload_limit'] * 1024 * 1024
        if data.seek(0, 2) > upload_limit:
            raise ResourceFileExceededLimitError(
                settings['file_upload_limit'], resource.filename)
        data.seek(0)
        args['data'] = psycopg2.Binary(data.read())

    cursor.execute("""\
INSERT INTO pending_resources
  (data, hash, media_type, filename)
VALUES (%(data)s, %(hash)s, %(media_type)s, %(filename)s)
""", args)

    if document:
        # upsert document and resource into pending resource associations
        cursor.execute("""\
WITH document AS (
    SELECT id FROM pending_documents
    WHERE ident_hash(uuid, major_version, minor_version) = %(id)s
), resource AS (
    SELECT id FROM pending_resources
    WHERE hash = %(hash)s
)
INSERT INTO pending_resource_associations
    (document_id, resource_id)
    SELECT document.id, resource.id
    FROM document, resource
    WHERE NOT EXISTS
    (SELECT * FROM pending_resource_associations, document, resource
     WHERE document_id = document.id AND resource_id = resource.id)
""", {'id': document.ident_hash, 'hash': resource.hash})
    resource.id = resource.hash


# FIXME Cache this this function. There is no reason it needs to run
#       more than once in a 24hr period.
def obtain_licenses():
    """Obtain the licenses in a dictionary form, keyed by url."""
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT combined_row.url, row_to_json(combined_row) FROM (
  SELECT "code", "version", "name", "url", "is_valid_for_publication"
  FROM licenses) AS combined_row""")
            licenses = {r[0]: r[1] for r in cursor.fetchall()}
    return licenses


def _validate_license(model):
    """Given the model, check the license is one valid for publication."""
    license_mapping = obtain_licenses()
    try:
        license_url = model.metadata['license_url']
    except KeyError:
        raise exceptions.MissingRequiredMetadata('license_url')
    try:
        license = license_mapping[license_url]
    except KeyError:
        raise exceptions.InvalidLicense(license_url)
    if not license['is_valid_for_publication']:
        raise exceptions.InvalidLicense(license_url)
    # TODO Does the given license_url match the license in document_controls?


def _validate_roles(model):
    """Given the model, check that all the metadata role values
    have valid information in them and any required metadata fields
    contain values.
    """
    required_roles = (ATTRIBUTED_ROLE_KEYS[0], ATTRIBUTED_ROLE_KEYS[4],)
    for role_key in ATTRIBUTED_ROLE_KEYS:
        try:
            roles = model.metadata[role_key]
        except KeyError:
            if role_key in required_roles:
                raise exceptions.MissingRequiredMetadata(role_key)
        else:
            if role_key in required_roles and len(roles) == 0:
                raise exceptions.MissingRequiredMetadata(role_key)
        for role in roles:
            if role.get('type') != 'cnx-id':
                raise exceptions.InvalidRole(role_key, role)


def _validate_derived_from(cursor, model):
    """Given a database cursor and model, check the derived-from
    value accurately points to content in the archive.
    The value can be nothing or must point to existing content.
    """
    derived_from_uri = model.metadata.get('derived_from_uri')
    if derived_from_uri is None:
        return  # bail out early

    # Can we parse the value?
    try:
        ident_hash = parse_archive_uri(derived_from_uri)
        uuid_, version = split_ident_hash(ident_hash, split_version=True)
    except (ValueError, IdentHashSyntaxError, IdentHashShortId) as exc:
        raise exceptions.InvalidMetadata('derived_from_uri', derived_from_uri,
                                         original_exception=exc)
    # Is the ident-hash a valid pointer?
    args = [uuid_]
    table = 'modules'
    version_condition = ''
    if version != (None, None,):
        args.extend(version)
        table = 'modules'
        version_condition = " AND major_version = %s" \
                            " AND minor_version {} %s" \
                            .format(version[1] is None and 'is' or '=')
    cursor.execute("""SELECT 't' FROM {} WHERE uuid::text = %s{}"""
                   .format(table, version_condition), args)
    try:
        _exists = cursor.fetchone()[0]  # noqa
    except TypeError:  # None type
        raise exceptions.InvalidMetadata('derived_from_uri', derived_from_uri)

    # Assign the derived_from value so that we don't have to split it again.
    model.metadata['derived_from'] = ident_hash


def _validate_subjects(cursor, model):
    """Give a database cursor and model, check the subjects against
    the subject vocabulary.
    """
    subject_vocab = [term[0] for term in acquire_subject_vocabulary(cursor)]
    subjects = model.metadata.get('subjects', [])
    invalid_subjects = [s for s in subjects if s not in subject_vocab]
    if invalid_subjects:
        raise exceptions.InvalidMetadata('subjects', invalid_subjects)


def validate_model(cursor, model):
    """Validates the model using a series of checks on bits of the data."""
    # Check the license is one valid for publication.
    _validate_license(model)
    _validate_roles(model)

    # Other required metadata includes: title, summary
    required_metadata = ('title', 'summary',)
    for metadata_key in required_metadata:
        if model.metadata.get(metadata_key) in [None, '', []]:
            raise exceptions.MissingRequiredMetadata(metadata_key)

    # Ensure that derived-from values are either None
    # or point at a live record in the archive.
    _validate_derived_from(cursor, model)

    # FIXME Valid language code?

    # Are the given 'subjects'
    _validate_subjects(cursor, model)

    # Optional metadata that does not need validation:
    #   created, revised, keywords, google_analytics, buylink


def is_publication_permissible(cursor, publication_id, uuid_):
    """Check the given publisher of this publication given
    by ``publication_id`` is allowed to publish the content given
    by ``uuid``.
    """
    # Check the publishing user has permission to publish
    cursor.execute("""\
SELECT 't'::boolean
FROM
  pending_documents AS pd
  NATURAL JOIN document_acl AS acl
  JOIN publications AS p ON (pd.publication_id = p.id)
WHERE
  p.id = %s
  AND
  pd.uuid = %s
  AND
  p.publisher = acl.user_id
  AND
  acl.permission = 'publish'""", (publication_id, uuid_,))
    try:
        is_allowed = cursor.fetchone()[0]
    except TypeError:
        is_allowed = False
    return is_allowed


def add_pending_model(cursor, publication_id, model):
    """Adds a model (binder or document) that is awaiting publication
    to the database.
    """
    # FIXME Too much happening here...
    assert isinstance(model, (cnxepub.Document, cnxepub.Binder,)), type(model)
    uri = model.get_uri('cnx-archive')

    if uri is not None:
        ident_hash = parse_archive_uri(uri)
        id, version = split_ident_hash(ident_hash, split_version=True)
        cursor.execute("""\
SELECT major_version + 1 as next_version
FROM latest_modules
WHERE uuid = %s
UNION ALL
SELECT 1 as next_version
ORDER BY next_version DESC
LIMIT 1
""", (id,))
        next_major_version = cursor.fetchone()[0]
        if isinstance(model, cnxepub.Document):
            version = (next_major_version, None,)
        else:  # ...assume it's a binder.
            version = (next_major_version, 1,)
    else:
        cursor.execute("""\
WITH
control_insert AS (
  INSERT INTO document_controls (uuid) VALUES (DEFAULT) RETURNING uuid),
acl_insert AS (
  INSERT INTO document_acl (uuid, user_id, permission)
  VALUES ((SELECT uuid FROM control_insert),
          (SELECT publisher FROM publications WHERE id = %s),
          'publish'::permission_type))
SELECT uuid FROM control_insert""", (publication_id,))
        id = cursor.fetchone()[0]
        if isinstance(model, cnxepub.Document):
            version = (1, None,)
        else:  # ...assume it's a binder.
            version = (1, 1,)

    type_ = _get_type_name(model)
    model.id = str(id)
    model.metadata['version'] = '.'.join([str(v) for v in version if v])
    args = [publication_id, id, version[0], version[1], type_,
            json.dumps(model.metadata)]
    cursor.execute("""\
INSERT INTO "pending_documents"
  ("publication_id", "uuid", "major_version", "minor_version", "type",
    "license_accepted", "roles_accepted", "metadata")
VALUES (%s, %s, %s, %s, %s, 'f', 'f', %s)
RETURNING "id", "uuid", module_version("major_version", "minor_version")
""", args)
    pending_id, uuid_, version = cursor.fetchone()
    pending_ident_hash = join_ident_hash(uuid_, version)

    # Assign the new ident-hash to the document for later use.
    request = get_current_request()
    path = request.route_path('get-content', ident_hash=pending_ident_hash)
    model.set_uri('cnx-archive', path)

    # Check if the publication is allowed for the publishing user.
    if not is_publication_permissible(cursor, publication_id, id):
        # Set the failure but continue the operation of inserting
        # the pending document.
        exc = exceptions.NotAllowed(id)
        exc.publication_id = publication_id
        exc.pending_document_id = pending_id
        exc.pending_ident_hash = pending_ident_hash
        set_publication_failure(cursor, exc)

    try:
        validate_model(cursor, model)
    except exceptions.PublicationException as exc:
        exc_info = sys.exc_info()
        exc.publication_id = publication_id
        exc.pending_document_id = pending_id
        exc.pending_ident_hash = pending_ident_hash
        try:
            set_publication_failure(cursor, exc)
        except BaseException:
            import traceback
            print("Critical data error. Immediate attention is "
                  "required. On publication at '{}'."
                  .format(publication_id),
                  file=sys.stderr)
            # Print the critical exception.
            traceback.print_exc()
            # Raise the previous exception, so we know the original cause.
            raise exc_info[0], exc_info[1], exc_info[2]
    else:
        upsert_pending_licensors(cursor, pending_id)
        upsert_pending_roles(cursor, pending_id)
        notify_users(cursor, pending_id)
    return pending_ident_hash


def lookup_document_pointer(ident_hash, cursor):
    """Lookup a document by id and version."""
    id, version = split_ident_hash(ident_hash, split_version=True)
    stmt = "SELECT name FROM modules WHERE uuid = %s"
    args = [id]
    if version and version[0] is not None:
        operator = version[1] is None and 'is' or '='
        stmt += " AND (major_version = %s AND minor_version {} %s)" \
            .format(operator)
        args.extend(version)
    cursor.execute(stmt, args)
    try:
        title = cursor.fetchone()[0]
    except TypeError:
        raise DocumentLookupError()
    else:
        metadata = {'title': title}
    return cnxepub.DocumentPointer(ident_hash, metadata)


def add_pending_model_content(cursor, publication_id, model):
    """Updates the pending model's content.
    This is a secondary step not in ``add_pending_model, because
    content reference resolution requires the identifiers as they
    will appear in the end publication.
    """
    cursor.execute("""\
        SELECT id, ident_hash(uuid, major_version, minor_version)
        FROM pending_documents
        WHERE publication_id = %s AND uuid = %s""",
                   (publication_id, model.id,))
    document_info = cursor.fetchone()

    def attach_info_to_exception(exc):
        """Small cached function to grab the pending document id
        and hash to attach to the exception, which is useful when
        reading the json data on a response.
        """
        exc.publication_id = publication_id
        exc.pending_document_id, exc.pending_ident_hash = document_info

    def mark_invalid_reference(reference):
        """Set the publication to failure and attach invalid reference
        to the publication.
        """
        exc = exceptions.InvalidReference(reference)
        attach_info_to_exception(exc)
        set_publication_failure(cursor, exc)

    for resource in getattr(model, 'resources', []):
        add_pending_resource(cursor, resource, document=model)

    if isinstance(model, cnxepub.Document):
        for reference in model.references:
            if reference.is_bound:
                reference.bind(reference.bound_model, '/resources/{}')
            elif reference.remote_type == cnxepub.INTERNAL_REFERENCE_TYPE:
                if reference.uri.startswith('#'):
                    pass
                elif reference.uri.startswith('/contents'):
                    ident_hash = parse_archive_uri(reference.uri)
                    try:
                        doc_pointer = lookup_document_pointer(
                            ident_hash, cursor)
                    except DocumentLookupError:
                        mark_invalid_reference(reference)
                    else:
                        reference.bind(doc_pointer, "/contents/{}")
                else:
                    mark_invalid_reference(reference)
            # else, it's a remote or cnx.org reference ...Do nothing.

        args = (psycopg2.Binary(model.content.encode('utf-8')),
                publication_id, model.id,)
        stmt = """\
            UPDATE "pending_documents"
            SET ("content") = (%s)
            WHERE "publication_id" = %s AND "uuid" = %s"""
    else:
        metadata = model.metadata.copy()
        # All document pointers in the tree are valid?
        document_pointers = [m for m in cnxepub.flatten_model(model)
                             if isinstance(m, cnxepub.DocumentPointer)]
        document_pointer_ident_hashes = [
            (split_ident_hash(dp.ident_hash)[0],
             split_ident_hash(dp.ident_hash, split_version=True)[1][0],
             split_ident_hash(dp.ident_hash, split_version=True)[1][1],)
            #  split_ident_hash(dp.ident_hash, split_version=True)[1][0],)
            for dp in document_pointers]
        document_pointer_ident_hashes = zip(*document_pointer_ident_hashes)

        if document_pointers:
            uuids, major_vers, minor_vers = document_pointer_ident_hashes
            cursor.execute("""\
SELECT dp.uuid, module_version(dp.maj_ver, dp.min_ver) AS version,
       dp.uuid = m.uuid AS exists,
       m.portal_type = 'Module' AS is_document
FROM (SELECT unnest(%s::uuid[]), unnest(%s::integer[]), unnest(%s::integer[]))\
         AS dp(uuid, maj_ver, min_ver)
     LEFT JOIN modules AS m ON dp.uuid = m.uuid AND \
         (dp.maj_ver = m.major_version OR dp.maj_ver is null)""",
                           (list(uuids), list(major_vers), list(minor_vers),))
            valid_pointer_results = cursor.fetchall()
            for result_row in valid_pointer_results:
                uuid, version, exists, is_document = result_row
                if not (exists and is_document):
                    dp = [dp for dp in document_pointers
                          if dp.ident_hash == join_ident_hash(uuid, version)
                          ][0]
                    exc = exceptions.InvalidDocumentPointer(
                        dp, exists=exists, is_document=is_document)
                    attach_info_to_exception(exc)
                    set_publication_failure(cursor, exc)

        # Insert the tree into the metadata.
        metadata['_tree'] = cnxepub.model_to_tree(model)
        args = (json.dumps(metadata),
                None,  # TODO Render the HTML tree at ``model.content``.
                publication_id, model.id,)
        # Must pave over metadata because postgresql lacks built-in
        # json update functions.
        stmt = """\
            UPDATE "pending_documents"
            SET ("metadata", "content") = (%s, %s)
            WHERE "publication_id" = %s AND "uuid" = %s"""
    cursor.execute(stmt, args)


def set_publication_failure(cursor, exc):
    """Given a publication exception, set the publication as failed and
    append the failure message to the publication record.
    """
    publication_id = exc.publication_id
    if publication_id is None:
        raise ValueError("Exception must have a ``publication_id`` value.")
    cursor.execute("""\
SELECT "state_messages"
FROM publications
WHERE id = %s""", (publication_id,))
    state_messages = cursor.fetchone()[0]
    if state_messages is None:
        state_messages = []
    entry = exc.__dict__
    entry['message'] = exc.message
    state_messages.append(entry)
    state_messages = json.dumps(state_messages)
    cursor.execute("""\
UPDATE publications SET ("state", "state_messages") = (%s, %s)
WHERE id = %s""", ('Failed/Error', state_messages, publication_id,))


def add_publication(cursor, epub, epub_file, is_pre_publication=False):
    """Adds a publication entry and makes each item
    a pending document.
    """
    publisher = epub[0].metadata['publisher']
    publish_message = epub[0].metadata['publication_message']
    epub_binary = psycopg2.Binary(epub_file.read())
    args = (publisher, publish_message, epub_binary, is_pre_publication,)
    cursor.execute("""\
INSERT INTO publications
  ("publisher", "publication_message", "epub", "is_pre_publication")
VALUES (%s, %s, %s, %s)
RETURNING id
""", args)
    publication_id = cursor.fetchone()[0]
    insert_mapping = {}

    models = set([])
    for package in epub:
        binder = cnxepub.adapt_package(package)
        if binder in models:
            continue
        for document in cnxepub.flatten_to_documents(binder):
            if document not in models:
                ident_hash = add_pending_model(
                    cursor, publication_id, document)
                insert_mapping[document.id] = ident_hash
                models.add(document)
        # The binding object could be translucent/see-through,
        # (case for a binder that only contains loose-documents).
        # Otherwise we should also publish the the binder.
        if not binder.is_translucent:
            ident_hash = add_pending_model(cursor, publication_id, binder)
            insert_mapping[binder.id] = ident_hash
            models.add(binder)
    for model in models:
        # Now that all models have been given an identifier
        # we can write the content to the database.
        try:
            add_pending_model_content(cursor, publication_id, model)
        except ResourceFileExceededLimitError as e:
            e.publication_id = publication_id
            set_publication_failure(cursor, e)
    return publication_id, insert_mapping


def _check_pending_document_license_state(cursor, document_id):
    """Check the aggregate state on the pending document."""
    cursor.execute("""\
SELECT BOOL_AND(accepted IS TRUE)
FROM
  pending_documents AS pd,
  license_acceptances AS la
WHERE
  pd.id = %s
  AND
  pd.uuid = la.uuid""",
                   (document_id,))
    try:
        is_accepted = cursor.fetchone()[0]
    except TypeError:
        # There are no licenses associated with this document.
        is_accepted = True
    return is_accepted


def _check_pending_document_role_state(cursor, document_id):
    """Check the aggregate state on the pending document."""
    cursor.execute("""\
SELECT BOOL_AND(accepted IS TRUE)
FROM
  role_acceptances AS ra,
  pending_documents as pd
WHERE
  pd.id = %s
  AND
  pd.uuid = ra.uuid""",
                   (document_id,))
    try:
        is_accepted = cursor.fetchone()[0]
    except TypeError:
        # There are no roles to accept
        is_accepted = True
    return is_accepted


def _update_pending_document_state(cursor, document_id, is_license_accepted,
                                   are_roles_accepted):
    """Update the state of the document's state values."""
    args = (bool(is_license_accepted), bool(are_roles_accepted),
            document_id,)
    cursor.execute("""\
UPDATE pending_documents
SET (license_accepted, roles_accepted) = (%s, %s)
WHERE id = %s""",
                   args)


@with_db_cursor
def is_revision_publication(publication_id, cursor):
    """Checks to see if the publication contains any revised models.
    Revised in this context means that it is a new version of an
    existing piece of content.
    """
    cursor.execute("""\
SELECT 't'::boolean FROM modules
WHERE uuid IN (SELECT uuid
               FROM pending_documents
               WHERE publication_id = %s)
LIMIT 1""", (publication_id,))
    try:
        cursor.fetchone()[0]
    except TypeError:  # NoneType
        has_revision_models = False
    else:
        has_revision_models = True
    return has_revision_models


@with_db_cursor
def poke_publication_state(publication_id, cursor):
    """Invoked to poke at the publication to update and acquire its current
    state. This is used to persist the publication to archive.
    """
    cursor.execute("""\
SELECT "state", "state_messages", "is_pre_publication", "publisher"
FROM publications
WHERE id = %s""", (publication_id,))
    row = cursor.fetchone()
    current_state, messages, is_pre_publication, publisher = row

    if current_state in END_N_INTERIM_STATES:
        # Bailout early, because the publication is either in progress
        # or has been completed.
        return current_state, messages

    # Check for acceptance...
    cursor.execute("""\
SELECT
  pd.id, license_accepted, roles_accepted
FROM publications AS p JOIN pending_documents AS pd ON p.id = pd.publication_id
WHERE p.id = %s
""", (publication_id,))
    pending_document_states = cursor.fetchall()
    publication_state_mapping = {}
    for document_state in pending_document_states:
        id, is_license_accepted, are_roles_accepted = document_state
        publication_state_mapping[id] = [is_license_accepted,
                                         are_roles_accepted]
        has_changed_state = False
        if is_license_accepted and are_roles_accepted:
            continue
        if not is_license_accepted:
            accepted = _check_pending_document_license_state(
                cursor, id)
            if accepted != is_license_accepted:
                has_changed_state = True
                is_license_accepted = accepted
                publication_state_mapping[id][0] = accepted
        if not are_roles_accepted:
            accepted = _check_pending_document_role_state(
                cursor, id)
            if accepted != are_roles_accepted:
                has_changed_state = True
                are_roles_accepted = accepted
                publication_state_mapping[id][1] = accepted
        if has_changed_state:
            _update_pending_document_state(cursor, id,
                                           is_license_accepted,
                                           are_roles_accepted)

    # Are all the documents ready for publication?
    state_lump = set([license and roles for license, roles
                      in publication_state_mapping.values()])
    is_publish_ready = not (False in state_lump) and not (None in state_lump)
    change_state = "Done/Success"
    if not is_publish_ready:
        change_state = "Waiting for acceptance"

    # Does this publication need moderation? (ignore on pre-publication)
    # TODO Is this a revision publication? If so, it doesn't matter who the
    #      user is, because they have been vetted by the previous publisher.
    #      This has loopholes...
    if not is_pre_publication and is_publish_ready:
        # Has this publisher been moderated before?
        cursor.execute("""\
SELECT is_moderated
FROM users AS u LEFT JOIN publications AS p ON (u.username = p.publisher)
WHERE p.id = %s""",
                       (publication_id,))
        try:
            is_publisher_moderated = cursor.fetchone()[0]
        except TypeError:
            is_publisher_moderated = False

        # Are any of these documents a revision? Thus vetting of
        #   the publisher was done by a vetted peer.
        if not is_publisher_moderated \
           and not is_revision_publication(publication_id, cursor):
            # Hold up! This publish needs moderation.
            change_state = "Waiting for moderation"
            is_publish_ready = False

    # Publish the pending documents.
    if is_publish_ready:
        change_state = "Done/Success"
        if not is_pre_publication:
            publication_state = publish_pending(cursor, publication_id)
        else:
            cursor.execute("""\
UPDATE publications
SET state = %s
WHERE id = %s
RETURNING state, state_messages""", (change_state, publication_id,))
            publication_state, messages = cursor.fetchone()
    else:
        # `change_state` set prior to this...
        cursor.execute("""\
UPDATE publications
SET state = %s
WHERE id = %s
RETURNING state, state_messages""", (change_state, publication_id,))
        publication_state, messages = cursor.fetchone()

    return publication_state, messages


def check_publication_state(publication_id):
    """Check the publication's current state."""
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT "state", "state_messages"
FROM publications
WHERE id = %s""", (publication_id,))
            publication_state, publication_messages = cursor.fetchone()
    return publication_state, publication_messages


def _node_to_model(tree_or_item, metadata=None, parent=None,
                   lucent_id=cnxepub.TRANSLUCENT_BINDER_ID):
    """Given a tree, parse to a set of models"""
    if 'contents' in tree_or_item:
        # It is a binder.
        tree = tree_or_item
        binder = cnxepub.TranslucentBinder(metadata=tree)
        for item in tree['contents']:
            node = _node_to_model(item, parent=binder,
                                  lucent_id=lucent_id)
            if node.metadata['title'] != item['title']:
                binder.set_title_for_node(node, item['title'])
        result = binder
    else:
        # It is an item pointing at a document.
        item = tree_or_item
        result = cnxepub.DocumentPointer(item['id'], metadata=item)
    if parent is not None:
        parent.append(result)
    return result


def _reassemble_binder(id, tree, metadata):
    """Reassemble a Binder object coming out of the database."""
    binder = cnxepub.Binder(id, metadata=metadata)
    for item in tree['contents']:
        node = _node_to_model(item, parent=binder)
        if node.metadata['title'] != item['title']:
            binder.set_title_for_node(node, item['title'])
    return binder


def publish_pending(cursor, publication_id):
    """Given a publication id as ``publication_id``,
    write the documents to the *Connexions Archive*.
    """
    cursor.execute("""\
WITH state_update AS (
  UPDATE publications SET state = 'Publishing' WHERE id = %s
)
SELECT publisher, publication_message
FROM publications
WHERE id = %s""",
                   (publication_id, publication_id,))
    publisher, message = cursor.fetchone()
    cursor.connection.commit()

    all_models = []

    from .publish import publish_model
    # Commit documents one at a time...
    type_ = cnxepub.Document.__name__
    cursor.execute("""\
SELECT id, uuid, major_version, minor_version, metadata, content
FROM pending_documents
WHERE type = %s AND publication_id = %s""", (type_, publication_id,))
    for row in cursor.fetchall():
        # FIXME Oof, this is hideous!
        id, major_version, minor_version = row[1:4]
        id = str(id)
        version = '.'.join([str(x)
                            for x in (major_version, minor_version,)
                            if x is not None])
        metadata, content = row[-2:]
        content = content[:]
        metadata['version'] = version

        document = cnxepub.Document(id, content, metadata)
        for ref in document.references:
            if ref.uri.startswith('/resources/'):
                hash = ref.uri[len('/resources/'):]
                cursor.execute("""\
SELECT data, media_type
FROM pending_resources
WHERE hash = %s""", (hash,))
                data, media_type = cursor.fetchone()
                document.resources.append(cnxepub.Resource(
                    hash, io.BytesIO(data[:]), media_type, filename=hash))

        _ident_hash = publish_model(cursor, document, publisher, message)  # noqa
        all_models.append(document)

    # And now the binders, one at a time...
    type_ = cnxepub.Binder.__name__
    cursor.execute("""\
SELECT id, uuid, major_version, minor_version, metadata, content
FROM pending_documents
WHERE type = %s AND publication_id = %s""", (type_, publication_id,))
    for row in cursor.fetchall():
        id, major_version, minor_version, metadata = row[1:5]
        tree = metadata['_tree']
        binder = _reassemble_binder(str(id), tree, metadata)
        # Add the resources
        cursor.execute("""\
SELECT hash, data, media_type, filename
FROM pending_resources r
JOIN pending_resource_associations a ON a.resource_id = r.id
JOIN pending_documents d ON a.document_id = d.id
WHERE ident_hash(uuid, major_version, minor_version) = %s""",
                       (binder.ident_hash,))
        binder.resources = [
            cnxepub.Resource(r_hash,
                             io.BytesIO(r_data[:]),
                             r_media_type,
                             filename=r_filename)
            for (r_hash, r_data, r_media_type, r_filename)
            in cursor.fetchall()]
        _ident_hash = publish_model(cursor, binder, publisher, message)  # noqa
        all_models.append(binder)

    # Republish binders containing shared documents.
    from .publish import republish_binders
    _republished_ident_hashes = republish_binders(cursor, all_models)  # noqa

    # Lastly, update the publication status.
    cursor.execute("""\
UPDATE publications
SET state = 'Done/Success'
WHERE id = %s
RETURNING state""", (publication_id,))
    state = cursor.fetchone()[0]
    return state


def accept_publication_license(cursor, publication_id, user_id,
                               document_ids, is_accepted=False):
    """Accept or deny  the document license for the publication
    (``publication_id``) and user (at ``user_id``)
    for the documents (listed by id as ``document_ids``).
    """
    cursor.execute("""\
UPDATE license_acceptances AS la
SET accepted = %s
FROM pending_documents AS pd
WHERE
  pd.publication_id = %s
  AND
  la.user_id = %s
  AND
  pd.uuid = ANY(%s::UUID[])
  AND
  pd.uuid = la.uuid""",
                   (is_accepted, publication_id, user_id, document_ids,))


def accept_publication_role(cursor, publication_id, user_id,
                            document_ids, is_accepted=False):
    """Accept or deny  the document role attribution for the publication
    (``publication_id``) and user (at ``user_id``)
    for the documents (listed by id as ``document_ids``).
    """
    cursor.execute("""\
UPDATE role_acceptances AS ra
SET accepted = %s
FROM pending_documents AS pd
WHERE
  pd.publication_id = %s
  AND
  ra.user_id = %s
  AND
  pd.uuid = ANY(%s::UUID[])
  AND
  pd.uuid = ra.uuid""",
                   (is_accepted, publication_id, user_id, document_ids,))


def upsert_license_requests(cursor, uuid_, roles):
    """Given a ``uuid`` and list of ``roles`` (user identifiers)
    create a license acceptance entry. If ``has_accepted`` is supplied,
    it will be used to assign an acceptance value to all listed ``uids``.
    """
    if not isinstance(roles, (list, set, tuple,)):
        raise TypeError("``roles`` is an invalid type: {}".format(type(roles)))

    acceptors = set([x['uid'] for x in roles])

    # Acquire a list of existing acceptors.
    cursor.execute("""\
SELECT user_id, accepted FROM license_acceptances WHERE uuid = %s""",
                   (uuid_,))
    existing_acceptors = cursor.fetchall()

    # Who's not in the existing list?
    new_acceptors = acceptors.difference([x[0] for x in existing_acceptors])

    # Insert the new licensor acceptors.
    if new_acceptors:
        args = []
        values_fmt = []
        for uid in new_acceptors:
            has_accepted = [x.get('has_accepted', None)
                            for x in roles
                            if uid == x['uid']][0]
            args.extend([uuid_, uid, has_accepted])
            values_fmt.append("(%s, %s, %s)")
        values_fmt = ', '.join(values_fmt)
        cursor.execute("""\
INSERT INTO license_acceptances (uuid, user_id, accepted)
VALUES {}""".format(values_fmt), args)

    # Update any existing license acceptors
    acceptors = set([
        (x['uid'], x.get('has_accepted', None),)
        for x in roles
        # Prevent updating newly inserted records.
        if (x['uid'], x.get('has_accepted', None),) not in new_acceptors
    ])
    existing_acceptors = set([
        x for x in existing_acceptors
        # Prevent updating newly inserted records.
        if x[0] not in new_acceptors
    ])
    tobe_updated_acceptors = acceptors.difference(existing_acceptors)

    for uid, has_accepted in tobe_updated_acceptors:
        cursor.execute("""\
UPDATE license_acceptances SET accepted = %s
WHERE uuid = %s AND user_id = %s""", (has_accepted, uuid_, uid,))


def remove_license_requests(cursor, uuid_, uids):
    """Given a ``uuid`` and list of ``uids`` (user identifiers)
    remove the identified users' license acceptance entries.
    """
    if not isinstance(uids, (list, set, tuple,)):
        raise TypeError("``uids`` is an invalid type: {}".format(type(uids)))

    acceptors = list(set(uids))

    # Remove the the entries.
    cursor.execute("""\
DELETE FROM license_acceptances
WHERE uuid = %s AND user_id = ANY(%s::text[])""", (uuid_, acceptors,))


def upsert_role_requests(cursor, uuid_, roles):
    """Given a ``uuid`` and list of dicts containing the ``uid`` and
    ``role`` for creating a role acceptance entry. The ``roles`` dict
    can optionally contain a ``has_accepted`` value, which will default
    to true.
    """
    if not isinstance(roles, (list, set, tuple,)):
        raise TypeError("``roles`` is an invalid type: {}"
                        .format(type(roles)))

    acceptors = set([(x['uid'], x['role'],) for x in roles])

    # Acquire a list of existing acceptors.
    cursor.execute("""\
SELECT user_id, role_type, accepted
FROM role_acceptances
WHERE uuid = %s""", (uuid_,))
    existing_roles = cursor.fetchall()

    # Who's not in the existing list?
    existing_acceptors = set([(r, t,) for r, t, _ in existing_roles])
    new_acceptors = acceptors.difference(existing_acceptors)

    # Insert the new role acceptors.
    for acceptor, type_ in new_acceptors:
        has_accepted = [x.get('has_accepted', None)
                        for x in roles
                        if acceptor == x['uid'] and type_ == x['role']][0]
        cursor.execute("""\
INSERT INTO role_acceptances ("uuid", "user_id", "role_type", "accepted")
VALUES (%s, %s, %s, %s)""", (uuid_, acceptor, type_, has_accepted,))

    # Update any existing license acceptors
    acceptors = set([
        (x['uid'], x['role'], x.get('has_accepted', None),)
        for x in roles
        # Prevent updating newly inserted records.
        if (x['uid'], x.get('has_accepted', None),) not in new_acceptors
    ])
    existing_acceptors = set([
        x for x in existing_roles
        # Prevent updating newly inserted records.
        if (x[0], x[1],) not in new_acceptors
    ])
    tobe_updated_acceptors = acceptors.difference(existing_acceptors)

    for uid, type_, has_accepted in tobe_updated_acceptors:
        cursor.execute("""\
UPDATE role_acceptances SET accepted = %s
WHERE uuid = %s AND user_id = %s AND role_type = %s""",
                       (has_accepted, uuid_, uid, type_,))


def remove_role_requests(cursor, uuid_, roles):
    """Given a ``uuid`` and list of dicts containing the ``uid``
    (user identifiers) and ``role`` for removal of the identified
    users' role acceptance entries.
    """
    if not isinstance(roles, (list, set, tuple,)):
        raise TypeError("``roles`` is an invalid type: {}".format(type(roles)))

    acceptors = set([(x['uid'], x['role'],) for x in roles])

    # Remove the the entries.
    for uid, role_type in acceptors:
        cursor.execute("""\
DELETE FROM role_acceptances
WHERE uuid = %s AND user_id = %s AND role_type = %s""",
                       (uuid_, uid, role_type,))


def upsert_acl(cursor, uuid_, permissions):
    """Given a ``uuid`` and a set of permissions given as a
    tuple of ``uid`` and ``permission``, upsert them into the database.
    """
    if not isinstance(permissions, (list, set, tuple,)):
        raise TypeError("``permissions`` is an invalid type: {}"
                        .format(type(permissions)))

    permissions = set(permissions)

    # Acquire the existin ACL.
    cursor.execute("""\
SELECT user_id, permission
FROM document_acl
WHERE uuid = %s""", (uuid_,))
    existing = set([(r, t,) for r, t in cursor.fetchall()])

    # Who's not in the existing list?
    new_entries = permissions.difference(existing)

    # Insert the new permissions.
    for uid, permission in new_entries:
        cursor.execute("""\
INSERT INTO document_acl
  ("uuid", "user_id", "permission")
VALUES (%s, %s, %s)""", (uuid_, uid, permission))


def remove_acl(cursor, uuid_, permissions):
    """Given a ``uuid`` and a set of permissions given as a tuple
    of ``uid`` and ``permission``, remove these entries from the database.
    """
    if not isinstance(permissions, (list, set, tuple,)):
        raise TypeError("``permissions`` is an invalid type: {}"
                        .format(type(permissions)))

    permissions = set(permissions)

    # Remove the the entries.
    for uid, permission in permissions:
        cursor.execute("""\
DELETE FROM document_acl
WHERE uuid = %s AND user_id = %s AND permission = %s""",
                       (uuid_, uid, permission,))


def _upsert_persons(cursor, person_ids, lookup_func):
    """Upsert's user info into the database.
    The model contains the user info as part of the role values.
    """
    person_ids = list(set(person_ids))  # cleanse data

    # Check for existing records to update.
    cursor.execute("SELECT personid from persons where personid = ANY (%s)",
                   (person_ids,))

    existing_person_ids = [x[0] for x in cursor.fetchall()]

    new_person_ids = [p for p in person_ids if p not in existing_person_ids]

    # Update existing records.
    for person_id in existing_person_ids:
        # TODO only update based on a delta against the 'updated' column.
        person_info = lookup_func(person_id)
        cursor.execute("""\
UPDATE persons
SET (personid, firstname, surname, fullname) =
    ( %(username)s, %(first_name)s, %(last_name)s,
     %(full_name)s)
WHERE personid = %(username)s""", person_info)

    # Insert new records.
    # Email is an empty string because
    # accounts no longer gives out user
    # email info but a string datatype
    # is still needed for legacy to
    # properly process the persons table
    for person_id in new_person_ids:
        person_info = lookup_func(person_id)
        cursor.execute("""\
INSERT INTO persons
(personid, firstname, surname, fullname, email)
VALUES
(%(username)s, %(first_name)s,
%(last_name)s, %(full_name)s, '')""", person_info)


def _upsert_users(cursor, user_ids, lookup_func):
    """Upsert's user info into the database.
    The model contains the user info as part of the role values.
    """
    user_ids = list(set(user_ids))  # cleanse data

    # Check for existing records to update.
    cursor.execute("SELECT username from users where username = ANY (%s)",
                   (user_ids,))

    existing_user_ids = [x[0] for x in cursor.fetchall()]

    new_user_ids = [u for u in user_ids if u not in existing_user_ids]

    # Update existing records.
    for user_id in existing_user_ids:
        # TODO only update based on a delta against the 'updated' column.
        user_info = lookup_func(user_id)
        cursor.execute("""\
UPDATE users
SET (updated, username, first_name, last_name, full_name, title) =
    (CURRENT_TIMESTAMP, %(username)s, %(first_name)s, %(last_name)s,
     %(full_name)s, %(title)s)
WHERE username = %(username)s""", user_info)

    # Insert new records.
    for user_id in new_user_ids:
        user_info = lookup_func(user_id)
        cursor.execute("""\
INSERT INTO users
(username, first_name, last_name, full_name, suffix, title)
VALUES
(%(username)s, %(first_name)s, %(last_name)s, %(full_name)s,
 %(suffix)s, %(title)s)""", user_info)


def upsert_users(cursor, user_ids):
    """Given a set of user identifiers (``user_ids``),
    upsert them into the database after checking accounts for
    the latest information.
    """
    accounts = get_current_registry().getUtility(IOpenstaxAccounts)

    def lookup_profile(username):
        profile = accounts.get_profile_by_username(username)
        # See structure documentation at:
        #   https://<accounts-instance>/api/docs/v1/users/index
        if profile is None:
            raise UserFetchError(username)

        opt_attrs = ('first_name', 'last_name', 'full_name',
                     'title', 'suffix',)
        for attr in opt_attrs:
            profile.setdefault(attr, None)
        return profile

    _upsert_users(cursor, user_ids, lookup_profile)
    _upsert_persons(cursor, user_ids, lookup_profile)


NOTIFICATION_TEMPLATE = jinja2.Template("""\
Hello {{full_name}},

{% if licensor %}
You have been assigned as a licenee on content.
You will need to approve the license on content before it can be published.
{% endif %}

{% if roles %}
You have been assigned the {{ ', '.join(roles) }} role(s) on content.
You will need to approve these roles before the content can be published.
{% endif %}

Thank you from your friends at OpenStax CNX
""", trim_blocks=True, lstrip_blocks=True)
NOFIFICATION_SUBJECT = "Requesting action on OpenStax CNX content"


def notify_users(cursor, document_id):
    """Notify all users about their role and/or license acceptance
    for a piece of content associated with the given ``document_id``.
    """
    return

    registry = get_current_registry()
    accounts = registry.getUtility(IOpenstaxAccounts)
    cursor.execute("""\
SELECT la.user_id
FROM license_acceptances AS la
WHERE
  la.uuid = (SELECT uuid FROM pending_documents WHERE id = %s)
  AND la.notified IS NULL AND (NOT la.accepted or la.accepted IS UNKNOWN)
""", (document_id,))
    licensors = [x[0] for x in cursor.fetchall()]

    cursor.execute("""\
SELECT user_id, array_agg(role_type)::text[]
FROM role_acceptances AS ra
WHERE
  ra.uuid = (SELECT uuid FROM pending_documents WHERE id = %s)
  AND ra.notified IS NULL AND (NOT ra.accepted or ra.accepted IS UNKNOWN)
GROUP BY user_id
""", (document_id,))
    roles = {u: r for u, r in cursor.fetchall()}

    needs_notified = set(licensors + roles.keys())

    for user_id in needs_notified:
        data = {
            'user_id': user_id,
            'full_name': None,  # TODO
            'licensor': user_id in licensors,
            'roles': roles.get(user_id, []),
        }
        message = NOTIFICATION_TEMPLATE.render(**data)
        accounts.send_message(user_id, NOFIFICATION_SUBJECT, message)

    cursor.execute("""\
UPDATE license_acceptances SET notified = CURRENT_TIMESTAMP
WHERE
  uuid = (SELECT uuid FROM pending_documents WHERE id = %s)
  AND user_id = ANY (%s)""", (document_id, licensors,))
    # FIXME overwrites notified for all roles types a user might have.
    cursor.execute("""\
UPDATE role_acceptances SET notified = CURRENT_TIMESTAMP
WHERE
  uuid = (SELECT uuid FROM pending_documents WHERE id = %s)
  AND user_id = ANY (%s)""", (document_id, roles.keys(),))


def set_post_publications_state(cursor, module_ident, state_name,
                                state_message=''):  # pragma: no cover
    """This sets the post-publication state in the database."""
    cursor.execute("""\
INSERT INTO post_publications
  (module_ident, state, state_message)
  VALUES (%s, %s, %s)""", (module_ident, state_name, state_message))


def update_module_state(cursor, module_ident,
                        state_name, recipe):  # pragma: no cover
    """This updates the module's state in the database."""
    cursor.execute("""\
UPDATE modules
SET stateid = (
    SELECT stateid FROM modulestates WHERE statename = %s
), recipe = %s, baked = now() WHERE module_ident = %s""",
                   (state_name, recipe, module_ident))


__all__ = (
    'accept_publication_license',
    'accept_publication_role',
    'acquire_subject_vocabulary',
    'add_pending_model',
    'add_pending_model_content',
    'add_pending_resource',
    'add_publication',
    'check_publication_state',
    'db_connect',
    'is_publication_permissible',
    'is_revision_publication',
    'lookup_document_pointer',
    'notify_users',
    'obtain_licenses',
    'poke_publication_state',
    'publish_pending',
    'remove_acl',
    'remove_license_requests',
    'remove_role_requests',
    'set_post_publications_state',
    'set_publication_failure',
    'update_module_state',
    'upsert_acl',
    'upsert_license_requests',
    'upsert_pending_licensors',
    'upsert_pending_roles',
    'upsert_role_requests',
    'upsert_users',
    'validate_model',
    'with_db_cursor',
)
