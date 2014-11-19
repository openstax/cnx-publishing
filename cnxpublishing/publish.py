# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""\
Functions used to commit publication works to the archive.
"""
import cnxepub
from cnxepub import Document, Binder
from cnxarchive.utils import join_ident_hash, split_ident_hash

from .utils import parse_user_uri


__all__ = ('publish_model',)


ATTRIBUTED_ROLE_KEYS = (
    'authors', 'copyright_holders', 'editors', 'illustrators',
    'publishers', 'translators',
    )
MODULE_INSERTION_TEMPLATE = """\
WITH abstract_insertion AS (
  INSERT INTO abstracts (abstractid, abstract, html)
  VALUES (DEFAULT, %(summary)s, %(summary)s)
  RETURNING abstractid),
license_lookup AS (
  SELECT licenseid
  FROM licenses
  WHERE url = %(license_url)s),
module_insertion AS (
  INSERT INTO modules
    (uuid, major_version, minor_version,
     module_ident, portal_type, moduleid,
     name, created, revised, language,
     submitter, submitlog,
     abstractid,
     licenseid,
     parent,
     parentauthors,
     authors, maintainers, licensors,
     google_analytics, buylink,
     stateid, doctype)
  VALUES
    ({__uuid__}, {__major_version__}, {__minor_version__},
     DEFAULT, %(_portal_type)s, {__moduleid__},
     %(title)s, %(created)s, CURRENT_TIMESTAMP, %(language)s,
     %(publisher)s, %(publication_message)s,
     (SELECT abstractid FROM abstract_insertion),
     (SELECT licenseid FROM license_lookup),
     (SELECT module_ident FROM modules
        WHERE uuid || '@' || concat_ws('.', major_version, minor_version) = %(parent_ident_hash)s),
     (SELECT authors FROM modules
        WHERE uuid || '@' || concat_ws('.', major_version, minor_version) = %(parent_ident_hash)s),
     %(authors)s, %(publishers)s, %(copyright_holders)s,
     DEFAULT, DEFAULT,
     DEFAULT, ' ')
  RETURNING
    module_ident,
    uuid||'@'||concat_ws('.',major_version,minor_version) AS ident_hash),
author_roles AS (
  INSERT INTO moduleoptionalroles (module_ident, roleid, personids)
  VALUES ((SELECT module_ident FROM module_insertion), 1, %(authors)s)),
licensor_roles AS (
  INSERT INTO moduleoptionalroles
    (module_ident, roleid, personids)
  VALUES
    ((SELECT module_ident FROM module_insertion), 2, %(copyright_holders)s)),
translator_roles AS (
  INSERT INTO moduleoptionalroles
    (module_ident, roleid, personids)
  VALUES
    ((SELECT module_ident FROM module_insertion), 4, %(translators)s)),
editor_roles AS (
  INSERT INTO moduleoptionalroles
    (module_ident, roleid, personids)
  VALUES
    ((SELECT module_ident FROM module_insertion), 5, %(editors)s)),
subjects AS (
  INSERT INTO moduletags
    SELECT (SELECT module_ident FROM module_insertion),
           (SELECT tagid FROM tags WHERE tag = s)
    FROM unnest(%(subjects)s::text[]) AS s),
keyword_inserts AS (
  INSERT INTO keywords
    (word)
    (SELECT word FROM unnest(%(keywords)s::text[]) AS word
     WHERE word NOT IN (SELECT k.word FROM keywords AS k))
  RETURNING word, keywordid),
keywords_relationship_from_new AS (
  INSERT INTO modulekeywords
    (module_ident, keywordid)
    (SELECT (SELECT module_ident FROM module_insertion), k.keywordid
     FROM keyword_inserts AS k)),
keywords_relationship_from_existing AS (
  INSERT INTO modulekeywords
    (module_ident, keywordid)
    (SELECT (SELECT module_ident FROM module_insertion), k.keywordid
     FROM unnest(%(keywords)s::text[]) AS i
          LEFT JOIN keywords AS k ON (i = k.word)
     WHERE word not in (SELECT word FROM keyword_inserts)))
SELECT module_ident, ident_hash FROM module_insertion
"""

TREE_NODE_INSERT = """
INSERT INTO trees
  (nodeid, parent_id, documentid,
   title, childorder, latest)
VALUES
  (DEFAULT, %(parent_id)s, %(document_id)s,
   %(title)s, %(child_order)s, %(is_latest)s)
RETURNING nodeid
"""


def _model_to_portaltype(model):
    if isinstance(model, Document):
        type_ = 'Module'
    elif isinstance(model, Binder):
        type_ = 'Collection'
    else:
        raise ValueError("Unknown type: {}".format(type(model)))
    return type_


def parse_parent_ident_hash(model):
    derived_from = model.metadata.get('derived_from_uri')
    if derived_from:
        return derived_from.rsplit('/', 1)[-1]


def _insert_metadata(cursor, model, publisher, message):
    """Insert a module with the given ``metadata``."""
    params = model.metadata.copy()
    params['publisher'] = publisher
    params['publication_message'] = message
    params['_portal_type'] = _model_to_portaltype(model)

    # Transform person structs to id lists for database array entry.
    for person_field in ATTRIBUTED_ROLE_KEYS:
        params[person_field] = [parse_user_uri(x['id'])
                                for x in params.get(person_field, [])]
    params['parent_ident_hash'] = parse_parent_ident_hash(model)

    # Assign the id and version if one is known.
    if model.ident_hash is not None:
        uuid, version = split_ident_hash(model.ident_hash,
                                         split_version=True)
        params['_uuid'] = uuid
        params['_major_version'], params['_minor_version'] = version
        # Lookup legacy ``moduleid``.
        cursor.execute("SELECT moduleid FROM latest_modules WHERE uuid = %s",
                       (uuid,))
        # There is the chance that a uuid and version have been set,
        #   but a previous publication does not exist. Therefore the
        #   moduleid will not be found. This happens on a pre-publication.
        try:
            moduleid = cursor.fetchone()[0]
        except TypeError as exc:  # NoneType
            moduleid = None
        params['_moduleid'] = moduleid

        # Format the statement to accept the identifiers.
        stmt = MODULE_INSERTION_TEMPLATE.format(**{
            '__uuid__': "%(_uuid)s::uuid",
            '__major_version__': "%(_major_version)s",
            '__minor_version__': "%(_minor_version)s",
            '__moduleid__': moduleid is None and "DEFAULT" or "%(_moduleid)s",
            })
    else:
        # Format the statement for defaults.
        stmt = MODULE_INSERTION_TEMPLATE.format(**{
            '__uuid__': "DEFAULT",
            '__major_version__': "DEFAULT",
            '__minor_version__': "DEFAULT",
            '__moduleid__': "DEFAULT",
            })

    cursor.execute(stmt, params)
    return cursor.fetchone()


def _insert_resource_file(cursor, module_ident, resource):
    """Insert a resource into the modules_files table. This will
    create a new file entry or associates an existing one.
    """
    cursor.execute("""\
SELECT md5, exists_in_archive FROM pending_resources WHERE hash = %s""",
                   (resource.hash,))
    try:
        md5, exists_in_archive = cursor.fetchone()
    except TypeError:  # NoneType
        # Can't depend on the pending_* tables in publish procedures.
        md5, exists_in_archive = None, False
    if exists_in_archive:
        cursor.execute("SELECT fileid FROM files WHERE md5 = %s LIMIT 1",
                       (md5,))
        fileid = cursor.fetchone()[0]
    else:
        with resource.open() as file:
            cursor.execute("""\
INSERT INTO files (file) VALUES (%s) RETURNING fileid""",
                           (memoryview(file.read()),))
        fileid = cursor.fetchone()[0]

    args = (module_ident, fileid, resource.filename, resource.media_type,)
    cursor.execute("""\
INSERT INTO module_files (module_ident, fileid, filename, mimetype)
VALUES (%s, %s, %s, %s)""", args)


def _insert_tree(cursor, tree, parent_id=None, index=0):
    """Inserts a binder tree into the archive."""
    if isinstance(tree, dict):
        if tree['id'] == 'subcol':
            document_id = None
            title = tree['title']
        else:
            cursor.execute("""\
            SELECT module_ident, name
            FROM modules
            WHERE uuid||'@'||concat_ws('.',major_version,minor_version) = %s
            """, (tree['id'],))
            try:
                document_id, document_title = cursor.fetchone()
            except TypeError as exc:  # NoneType
                raise ValueError("Missing published document for '{}'."\
                                 .format(tree['id']))
            if tree.get('title', None):
                title = tree['title']
            else:
                title = document_title
        # TODO We haven't settled on a flag (name or value)
        #      to pin the node to a specific version.
        is_latest = True
        cursor.execute(TREE_NODE_INSERT,
                       dict(document_id=document_id, parent_id=parent_id,
                            title=title, child_order=index,
                            is_latest=is_latest))
        node_id = cursor.fetchone()[0]
        if 'contents' in tree:
            _insert_tree(cursor, tree['contents'], parent_id=node_id)
    elif isinstance(tree, list):
        for tree_node in tree:
            _insert_tree(cursor, tree_node, parent_id=parent_id,
                         index=tree.index(tree_node))


def publish_model(cursor, model, publisher, message):
    """Publishes the ``model`` and return its ident_hash."""
    publishers = publisher
    if isinstance(publishers, list) and len(publishers) > 1:
        raise ValueError("Only one publisher is allowed. '{}' "
                         "were given: {}" \
                         .format(len(publishers), publishers))
    module_ident, ident_hash = _insert_metadata(cursor, model,
                                                publisher, message)
    if isinstance(model, Document):
        file_arg = {
            'module_ident': module_ident,
            'filename': 'index.cnxml.html',
            'mime_type': 'text/html',
            'data': model.html.encode('utf-8'),
            }
        cursor.execute("""\
WITH file_insertion AS (
  INSERT INTO files (file) VALUES (%(data)s) RETURNING fileid)
INSERT INTO module_files
  (module_ident, fileid, filename, mimetype)
VALUES
  (%(module_ident)s,
   (SELECT fileid FROM file_insertion), 
   %(filename)s, %(mime_type)s)""", file_arg)
        for resource in model.resources:
            _insert_resource_file(cursor, module_ident, resource)
    elif isinstance(model, Binder):
        tree = cnxepub.model_to_tree(model)
        tree = _insert_tree(cursor, tree)
    return ident_hash


def republish_binders(cursor, models):
    """Republish the Binders that share Documents in the publication context.
    This needs to be given all the models in the publication context."""
    documents = set([])
    binders = set([])
    history_mapping = {}  # <previous-ident-hash>: <current-ident-hash>
    if not isinstance(models, (list, tuple, set,)):
        raise TypeError("``models`` Must be a sequence of model objects." \
                        "We were given: {}".format(models))
    for model in models:
        if isinstance(model, (cnxepub.Binder,)):
            binders.add(split_ident_hash(model.ident_hash))
            for doc in cnxepub.flatten_to_documents(model):
                documents.add(split_ident_hash(doc.ident_hash))
        else:
            documents.add(split_ident_hash(model.ident_hash))

    to_be_republished = []
    # What binders are these documents a part of?
    for (uuid, version) in documents:
        ident_hash = join_ident_hash(uuid, version)
        previous_ident_hash = get_previous_publication(cursor, ident_hash)
        if previous_ident_hash is None:
            # Has no prior existence.
            continue
        else:
            history_mapping[previous_ident_hash] = ident_hash
        cursor.execute("""\
WITH RECURSIVE t(nodeid, parent_id, documentid, path) AS (
  SELECT tr.nodeid, tr.parent_id, tr.documentid, ARRAY[tr.nodeid]
  FROM trees tr
  WHERE tr.documentid = (
    SELECT module_ident FROM modules
    WHERE uuid||'@'||concat_ws('.', major_version, minor_version) = %s)
UNION ALL
  SELECT c.nodeid, c.parent_id, c.documentid, path || ARRAY[c.nodeid]
  FROM trees c JOIN t ON (c.nodeid = t.parent_id)
  WHERE not c.nodeid = ANY(t.path)
)
SELECT uuid||'@'||concat_ws('.', major_version, minor_version)
FROM t JOIN latest_modules m ON (t.documentid = m.module_ident)
WHERE t.parent_id IS NULL
""",
                       (previous_ident_hash,))
        to_be_republished.extend([split_ident_hash(x[0])
                                  for x in cursor.fetchall()])
    to_be_republished = set(to_be_republished)

    republished_ident_hashes = []
    # Republish the Collections set.
    for (uuid, version) in to_be_republished:
        if (uuid, version,) in binders:
            # This binder is already in the publication context,
            # don't try to publish it again.
            continue
        ident_hash = join_ident_hash(uuid, version)
        bumped_version = bump_version(cursor, uuid, is_minor_bump=True)
        republished_ident_hash = republish_collection(cursor, ident_hash,
                                                      version=bumped_version)
        # Set the identifier history.
        history_mapping[ident_hash] = republished_ident_hash
        rebuild_collection_tree(cursor, ident_hash, history_mapping)
        republished_ident_hashes.append(republished_ident_hash)

    return republished_ident_hashes


def get_previous_publication(cursor, ident_hash):
    """Get the previous publication of the given
    publication as an ident-hash.
    """
    uuid, version = split_ident_hash(ident_hash)
    cursor.execute("""\
WITH contextual_module AS (
  SELECT uuid, module_ident
  FROM modules
  WHERE uuid = %s AND concat_ws('.', major_version, minor_version) = %s)
SELECT m.uuid||'@'||concat_ws('.', m.major_version, m.minor_version)
FROM modules AS m JOIN contextual_module AS context ON (m.uuid = context.uuid)
WHERE
  m.module_ident < context.module_ident
ORDER BY revised DESC
LIMIT 1""",
                   (uuid, version,))
    try:
        previous_ident_hash = cursor.fetchone()[0]
    except TypeError:  # NoneType
        previous_ident_hash = None
    return previous_ident_hash


def bump_version(cursor, uuid, is_minor_bump=False):
    """Bump to the next version of the given content identified
    by ``uuid``. Returns the next available version as a version tuple,
    containing major and minor version.
    If ``is_minor_bump`` is ``True`` the version will minor bump. That is
    1.2 becomes 1.3 in the case of Collections. And 2 becomes 3 for
    Modules regardless of this option.
    """
    cursor.execute("""\
SELECT portal_type, major_version, minor_version
FROM latest_modules
WHERE uuid = %s::uuid""", (uuid,))
    type_, major_version, minor_version = cursor.fetchone()
    incr = 1
    if type_ == 'Collection' and is_minor_bump:
        minor_version = minor_version + incr
    else:
        major_version = major_version + incr
    return (major_version, minor_version,)


def republish_collection(cursor, ident_hash, version):
    """Republish the collection identified as ``ident_hash`` with
    the given ``version``.
    """
    if not isinstance(version, (list, tuple,)):
        split_version = version.split('.')
        if len(split_version) == 1:
            split_version.append(None)
        version = tuple(split_version)
    major_version, minor_version = version

    cursor.execute("""\
WITH previous AS (
  SELECT module_ident
  FROM modules
  WHERE uuid||'@'||concat_ws('.', major_version, minor_version) = %s),
inserted AS (
  INSERT INTO modules
    (uuid, major_version, minor_version, revised,
     portal_type, moduleid,
     name, created, language,
     submitter, submitlog,
     abstractid, licenseid, parent, parentauthors,
     authors, maintainers, licensors,
     google_analytics, buylink,
     stateid, doctype)
  SELECT
    uuid, %s, %s, CURRENT_TIMESTAMP,
    portal_type, moduleid,
    name, created, language,
    submitter, submitlog,
    abstractid, licenseid, parent, parentauthors,
    authors, maintainers, licensors,
    google_analytics, buylink,
    stateid, doctype
  FROM modules AS m JOIN previous AS p ON (m.module_ident = p.module_ident)
  RETURNING
    uuid||'@'||concat_ws('.', major_version, minor_version) AS ident_hash,
    module_ident),
keywords AS (
  INSERT INTO modulekeywords (module_ident, keywordid)
  SELECT i.module_ident, keywordid
  FROM modulekeywords AS mk, inserted AS i, previous AS p
  WHERE mk.module_ident = p.module_ident),
tags AS (
  INSERT INTO moduletags (module_ident, tagid)
  SELECT i.module_ident, tagid
  FROM moduletags AS mt, inserted AS i, previous AS p
  WHERE mt.module_ident = p.module_ident)
SELECT ident_hash FROM inserted""",
                   (ident_hash, major_version, minor_version,))
    repub_ident_hash = cursor.fetchone()[0]
    return repub_ident_hash


def rebuild_collection_tree(cursor, ident_hash, history_map):
    """Create a new tree for the collection based on the old tree but with
    new document ids
    """
    collection_tree_sql = """\
WITH RECURSIVE t(nodeid, parent_id, documentid, title, childorder, latest, ident_hash, path) AS (
  SELECT
    tr.nodeid, tr.parent_id, tr.documentid,
    tr.title, tr.childorder, tr.latest,
    (SELECT uuid||'@'||concat_ws('.', major_version, minor_version)
     FROM modules
     WHERE module_ident = tr.documentid) AS ident_hash,
    ARRAY[tr.nodeid]
  FROM trees AS tr
  WHERE tr.documentid = (
    SELECT module_ident
    FROM modules
    WHERE uuid||'@'||concat_ws('.', major_version, minor_version) = %s)
UNION ALL
  SELECT
    c.*,
    (SELECT uuid||'@'||concat_ws('.', major_version, minor_version)
     FROM modules
     WHERE module_ident = c.documentid) AS ident_hash,
    path || ARRAY[c.nodeid]
  FROM trees AS c JOIN t ON (c.parent_id = t.nodeid)
  WHERE not c.nodeid = ANY(t.path)
)
SELECT row_to_json(row) FROM (SELECT * FROM t) AS row"""

    tree_insert_sql = """\
INSERT INTO trees
  (nodeid, parent_id,
   documentid,
   title, childorder, latest)
VALUES
  (DEFAULT, %(parent_id)s,
   (SELECT module_ident
    FROM modules
    WHERE uuid||'@'||concat_ws('.', major_version, minor_version) = %(ident_hash)s),
   %(title)s, %(childorder)s, %(latest)s)
RETURNING nodeid"""

    def get_tree():
        cursor.execute(collection_tree_sql, (ident_hash,))
        for row in cursor.fetchall():
            yield row[0]

    def insert(fields):
        cursor.execute(tree_insert_sql, fields)
        results = cursor.fetchone()[0]
        return results

    tree = {} # {<current-nodeid>: {<row-data>...}, ...}
    children = {} # {<nodeid>: [<child-nodeid>, ...], <child-nodeid>: [...]}
    for node in get_tree():
        tree[node['nodeid']] = node
        children.setdefault(node['parent_id'], [])
        children[node['parent_id']].append(node['nodeid'])

    def build_tree(nodeid, parent_id):
        data = tree[nodeid]
        data['parent_id'] = parent_id
        if history_map.get(data['ident_hash']) is not None \
           and data['latest']:
            data['ident_hash'] = history_map[data['ident_hash']]
        new_nodeid = insert(data)
        for child_nodeid in children.get(nodeid, []):
            build_tree(child_nodeid, new_nodeid)

    root_node = children[None][0]
    build_tree(root_node, None)
