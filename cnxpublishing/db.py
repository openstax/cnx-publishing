# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import io
import json
import uuid

import cnxepub
import psycopg2
from psycopg2.extras import register_uuid
from cnxarchive.utils import join_ident_hash, split_ident_hash
from pyramid.security import has_permission
from pyramid.threadlocal import (
    get_current_request, get_current_registry,
    )

from .config import CONNECTION_STRING
from .utils import parse_archive_uri, parse_user_uri
from .publish import publish_model


__all__ = (
    'initdb',
    'add_publication',
    'poke_publication_state', 'check_publication_state',
    'add_pending_document',
    'accept_publication_license',
    )


here = os.path.abspath(os.path.dirname(__file__))
SQL_DIR = os.path.join(here, 'sql')
SCHEMA_FILES = (
    'schema-types.sql',
    'schema-tables.sql',
    'schema-indexes.sql',
    'schema-triggers.sql',
    )
# FIXME psycopg2 UUID adaptation doesn't seem to be registering
# itself. Temporarily call it directly.
register_uuid()
ATTRIBUTED_ROLE_KEYS = (
    'authors', 'copyright_holders', 'editors', 'illustrators',
    'publishers', 'translators',
    )


def initdb(connection_string):
    """Initialize publishing in or along-side the archive database."""
    with psycopg2.connect(connection_string) as db_conn:
        with db_conn.cursor() as cursor:
            for filename in SCHEMA_FILES:
                schema_filepath = os.path.join(SQL_DIR, filename)
                with open(schema_filepath, 'r') as fb:
                    schema = fb.read()
                    cursor.execute(schema)


def upsert_pending_acceptors(cursor, document_id):
    """Update or insert records for pending license acceptors."""
    cursor.execute("""\
SELECT "uuid", "metadata"
FROM pending_documents
WHERE id = %s""", (document_id,))
    uuid, metadata = cursor.fetchone()
    if metadata is None:
        # Metadata wasn't set yet. Bailout early.
        return

    acceptors = set([])
    for role_key in ATTRIBUTED_ROLE_KEYS:
        for user in metadata[role_key]:
            if user['type'] != 'cnx-id':
                raise ValueError("Archive only accepts Connexions users.")
            id = parse_user_uri(user['id'])
            acceptors.add(id)

    # Acquire a list of existing acceptors.
    cursor.execute("""\
SELECT "user_id", "acceptance"
FROM publications_license_acceptance
WHERE uuid = %s""", (uuid,))
    existing_acceptors_mapping = dict(cursor.fetchall())

    # Who's not in the existing list?
    existing_acceptors = set(existing_acceptors_mapping.keys())
    new_acceptors = acceptors.difference(existing_acceptors)

    # Insert the new licensor acceptors.
    for acceptor in new_acceptors:
        cursor.execute("""\
INSERT INTO publications_license_acceptance
  ("uuid", "user_id", "acceptance")
VALUES (%s, %s, NULL)""", (uuid, acceptor,))

    # Has everyone already accepted?
    cursor.execute("""\
SELECT user_id
FROM publications_license_acceptance
WHERE
  uuid = %s
  AND
  (acceptance is NULL OR acceptance = FALSE)""", (uuid,))
    defectors = set(cursor.fetchall())

    if not defectors:
        # Update the pending document license acceptance state.
        cursor.execute("""\
update pending_documents set license_accepted = 't'
where id = %s""", (document_id,))


def _get_type_name(model):
    """Returns a type name of 'Document' or 'Binder' based model's type."""
    # XXX Shouldn't need to complicate this...
    #     ... IDocument.providedBy(model)
    if isinstance(model, cnxepub.Binder):
        return 'Binder'
    else:
        return 'Document'


def add_pending_resource(cursor, resource):
    args = {
            'data': psycopg2.Binary(resource.data.read()),
            'media_type': resource.media_type,
            }
    cursor.execute("""\
INSERT INTO pending_resources
  (data, media_type)
VALUES (%(data)s, %(media_type)s);
SELECT md5(%(data)s);
""", args)
    resource.id = cursor.fetchone()[0]


def add_pending_model(cursor, publication_id, model):
    """Adds a model (binder or document) that is awaiting publication
    to the database.
    """
    # FIXME Too much happening here...
    assert isinstance(model, (cnxepub.Document, cnxepub.Binder,))
    uri = model.get_uri('cnx-archive')
    if uri is not None:
        ident_hash = parse_archive_uri(uri)
        id, version = split_ident_hash(ident_hash, split_version=True)
        if version is None or version == (None, None):
            cursor.execute("""\
SELECT major_version + 1 as next_version
FROM modules
WHERE uuid = %s
UNION ALL
SELECT 1 as next_version
ORDER BY next_version DESC
LIMIT 1
""", (id,))
            next_major_version = cursor.fetchone()[0]
            if isinstance(model, cnxepub.Document):
                version = (next_major_version, None,)
            else: # ...assume it's a binder.
                version = (next_major_version, 1,)
    else:
        id = uuid.uuid4()
        if isinstance(model, cnxepub.Document):
            version = (1, None,)
        else:  # ...assume it's a binder.
            version = (1, 1,)

    type_ = _get_type_name(model)
    # Is the publishing party a trusted source?
    request = get_current_request()
    context = request.root
    is_license_accepted = bool(
        has_permission('publish.trusted-license-assigner',
                       context, request))
    are_roles_accepted = bool(
        has_permission('publish.trusted-role-assigner',
                       context, request))

    args = [publication_id, id, version[0], version[1], type_,
            is_license_accepted, are_roles_accepted,]
    cursor.execute("""\
INSERT INTO "pending_documents"
  ("publication_id", "uuid", "major_version", "minor_version", "type",
   "license_accepted", "roles_accepted")
VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING "id", "uuid", concat_ws('.', "major_version", "minor_version")
""", args)
    pending_id, id, version = cursor.fetchone()
    # FIXME Reassigning the ID and version here is probably not the
    #       greatest approach to this.
    model.metadata['version'] = version
    model.id = str(id)

    pending_ident_hash = join_ident_hash(id, version)

    # Assign the new ident-hash to the document for later use.
    request = get_current_request()
    path = request.route_path('get-content', ident_hash=pending_ident_hash)
    model.set_uri('cnx-archive', path)

    # FIXME This can't be here, because content reference resolution will need
    # to write updates to the document after all document metadata
    # has been added. This is because not all documents will have system
    # identifiers until after metadata persistence.
    # We will need to move this operation up a layer.
    if isinstance(model, cnxepub.Document):
        for resource in model.resources:
            add_pending_resource(cursor, resource)

        for reference in model.references:
            if reference._bound_model:
                reference.bind(reference._bound_model, '/resources/{}')

        args = (json.dumps(model.metadata),
                psycopg2.Binary(model.content.encode('utf-8')),
                pending_id,)
        stmt = """\
            UPDATE "pending_documents"
            SET ("metadata", "content") = (%s, %s)
            WHERE "id" = %s"""
    else:
        metadata = model.metadata.copy()
        # Insert the tree into the metadata.
        metadata['_tree'] = cnxepub.model_to_tree(model)
        args = (json.dumps(metadata), pending_id,)
        stmt = """\
            UPDATE "pending_documents"
            SET metadata = %s
            WHERE "id" = %s"""

    cursor.execute(stmt, args)
    upsert_pending_acceptors(cursor, pending_id)
    return pending_ident_hash


def add_publication(cursor, epub, epub_file):
    """Adds a publication entry and makes each item
    a pending document.
    """
    publisher = epub[0].metadata['publisher']
    publish_message = epub[0].metadata['publication_message']
    epub_binary = psycopg2.Binary(epub_file.read())
    args = (publisher, publish_message, epub_binary,)
    cursor.execute("""\
INSERT INTO publications ("publisher", "publication_message", "epub")
VALUES (%s, %s, %s)
RETURNING id
""", args)
    publication_id = cursor.fetchone()[0]
    insert_mapping = {}

    for package in epub:
        binder = cnxepub.adapt_package(package)
        for document in cnxepub.flatten_to_documents(binder):
            ident_hash = add_pending_model(cursor, publication_id, document)
            insert_mapping[document.id] = ident_hash
        # The binding object could be translucent/see-through,
        # (case for a binder that only contains loose-documents).
        # Otherwise we should also publish the the binder.
        if not binder.is_translucent:
            ident_hash = add_pending_model(cursor, publication_id, binder)
            insert_mapping[binder.id] = ident_hash
    return publication_id, insert_mapping


def poke_publication_state(publication_id, current_state=None):
    """Invoked to poke at the publication to update and acquire its current
    state. This is used to persist the publication to archive.
    """
    registry = get_current_registry()
    conn_str = registry.settings[CONNECTION_STRING]
    with psycopg2.connect(conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            if current_state is None:
                cursor.execute(
                    """SELECT "state" FROM publications WHERE id = %s""",
                    (publication_id,))
                current_state = cursor.fetchone()[0]
    if current_state in ('Publishing', 'Done/Success',):
        # Bailout early, because the publication is either in progress
        # or has been completed.
        return current_state

    # Check for acceptance...
    with psycopg2.connect(conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT
  pd.uuid || '@' || concat_ws('.', pd.major_version, pd.minor_version),
  license_accepted, roles_accepted
FROM publications AS p JOIN pending_documents AS pd ON p.id = pd.publication_id
WHERE p.id = %s""", (publication_id,))
            pending_document_states = cursor.fetchall()
    publication_state_mapping = {x[0]:x[1:] for x in pending_document_states}

    # Are all the documents ready for publication?
    state_lump = set([l and r for l, r in publication_state_mapping.values()])
    is_publish_ready = not (False in state_lump)

    # Publish the pending documents.
    with psycopg2.connect(conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            if is_publish_ready:
                publication_state = publish_pending(cursor, publication_id)
            else:
                change_state = "Waiting for acceptance"
                cursor.execute("""\
UPDATE publications
SET state = %s
WHERE id = %s
RETURNING state""", (change_state, publication_id,))
                publication_state = cursor.fetchone()[0]
    return publication_state


def check_publication_state(publication_id):
    """Check the publication's current state."""
    registry = get_current_registry()
    conn_str = registry.settings[CONNECTION_STRING]
    with psycopg2.connect(conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute(
                """SELECT "state" FROM publications WHERE id = %s""",
                (publication_id,))
            publication_state = cursor.fetchone()[0]
    return publication_state


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
                    hash, io.BytesIO(data), media_type))

        ident_hash = publish_model(cursor, document, publisher, message)

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
        ident_hash = publish_model(cursor, binder, publisher, message)

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
UPDATE publications_license_acceptance AS pla
SET acceptance = %s
FROM pending_documents AS pd
WHERE
  pd.publication_id = %s
  AND
  pla.user_id = %s
  AND
    pd.uuid = ANY(%s::UUID[])
  AND
  pd.uuid = pla.uuid""",
                   (is_accepted, publication_id, user_id, document_ids,))
