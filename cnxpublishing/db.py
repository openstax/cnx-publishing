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
from cnxarchive.utils import join_ident_hash, split_ident_hash
from pyramid.threadlocal import (
    get_current_request, get_current_registry,
    )

from .config import CONNECTION_STRING
from .utils import parse_archive_uri, parse_user_uri
from .publish import publish_model


__all__ = (
    'initdb',
    'add_publication', 'poke_publication_state',
    'add_pending_document',
    )


here = os.path.abspath(os.path.dirname(__file__))
SQL_DIR = os.path.join(here, 'sql')
SCHEMA_FILES = (
    'schema-types.sql',
    'schema-tables.sql',
    'schema-indexes.sql',
    'schema-triggers.sql',
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
    for user in metadata['authors']:
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


def add_pending_document(cursor, publication_id, document):
    """Adds a document that is awaiting publication to the database."""
    uri = document.get_uri('cnx-archive')
    if uri is None:
        id = uuid.uuid4()
        version = (1, None,)
    else:
        ident_hash = parse_archive_uri(uri)
        id, version = split_ident_hash(ident_hash, split_version=True)

    args = [publication_id, id, version[0], version[1], 'Document',
            False, False,]
    cursor.execute("""\
INSERT INTO "pending_documents"
  ("publication_id", "uuid", "major_version", "minor_version", "type",
   "license_accepted", "roles_accepted")
VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING "id", "uuid", concat_ws('.', "major_version", "minor_version")
""", args)
    pending_id, id, version = cursor.fetchone()
    pending_ident_hash = join_ident_hash(id, version)

    # FIXME This can't be here, because content reference resolution will need
    # to write updates to the document after all document metadata
    # has been added. This is because not all documents will have system
    # identifiers until after metadata persistence.
    # We will need to move this operation up a layer.
    args = (json.dumps(document.metadata),
            psycopg2.Binary(document.content.read()),
            pending_id,)
    cursor.execute("""\
UPDATE "pending_documents"
SET ("metadata", "content") = (%s, %s)
WHERE "id" = %s
""", args)

    for resource in document.resources:
        add_pending_resource(cursor, resource)

    upsert_pending_acceptors(cursor, pending_id)

    # Assign the new ident_hash to the document for later use.
    request = get_current_request()
    path = request.route_path('get-content', ident_hash=pending_ident_hash)
    document.set_uri('cnx-archive', path)

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
    state_urls = []

    for package in epub:
        binder = cnxepub.adapt_package(package)
        # The binding object could be translucent/see-through,
        # (case for a binder that only contains loose-documents).
        # Otherwise we should also publish the the binder.
        if not binder.is_translucent:
            raise NotImplementedError()
        for document in cnxepub.flatten_to_documents(binder):
            ident_hash = add_pending_document(cursor, publication_id, document)
            request = get_current_request()
            url = request.route_url('get-content', ident_hash=ident_hash)
            state_urls.append(url)
    return publication_id, state_urls


def poke_publication_state(publication_id):
    """Invoked to poke at the publication to update and acquire its current
    state. This is used to persist the publication to archive.
    """
    registry = get_current_registry()
    conn_str = registry.settings[CONNECTION_STRING]
    with psycopg2.connect(conn_str) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT
  pd.uuid || '@' || concat_ws('.', pd.major_version, pd.minor_version),
  license_accepted, roles_accepted
FROM publications AS p NATURAL JOIN pending_documents AS pd
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
                cursor.execute("""\
SELECT "state"
FROM publications
WHERE id = %s""", (publication_id,))
                publication_state = cursor.fetchone()[0]
    return publication_state


def publish_pending(cursor, publication_id):
    """Given a publication id as ``publication_id``,
    write the documents to the *Connexions Archive*.
    """
    cursor.execute("""\
SELECT publisher, publication_message
FROM publications
WHERE id = %s""", (publication_id,))
    publisher, message = cursor.fetchone()

    # Commit documents one at a time...
    cursor.execute("""\
SELECT id, uuid, major_version, minor_version, metadata, content
FROM pending_documents
WHERE type = 'Document' AND publication_id = %s""", (publication_id,))
    rows = cursor.fetchall()
    for row in rows:
        # FIXME Oof, this is hideous!
        id, major_version, minor_version = row[1:4]
        id = str(id)
        version = '.'.join([str(x)
                            for x in (major_version, minor_version,)
                            if x is not None])
        metadata, content = row[-2:]
        content = io.BytesIO(content[:])
        metadata['version'] = version
        document = cnxepub.Document(id, content, metadata)
        ident_hash = publish_model(cursor, document, publisher, message)

    # And now the binders, one at a time...
    cursor.execute("""\
SELECT id, uuid, major_version, minor_version, metadata, content
FROM pending_documents
WHERE type = 'Binder' AND publication_id = %s""", (publication_id,))
    rows = cursor.fetchall()
    for row in rows:
        ident_hash = publish_model(cursor, binder, publisher, message)

    # Lastly, update the publication status.
    cursor.execute("""\
UPDATE publications
SET state = 'Done/Success'
WHERE id = %s
RETURNING state""", (publication_id,))
    state = cursor.fetchone()[0]
    return state
