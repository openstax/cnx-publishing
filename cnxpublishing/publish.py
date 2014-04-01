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
from cnxarchive.utils import split_ident_hash

from .utils import parse_user_uri


__all__ = ('publish_model',)


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
     parent, parentauthors,
     authors, maintainers, licensors,
     google_analytics, buylink,
     stateid, doctype)
  VALUES
    ({__uuid__}, {__major_version__}, {__minor_version__},
     DEFAULT, %(_portal_type)s, DEFAULT,
     %(title)s, %(created)s, %(revised)s, %(language)s,
     %(publisher)s, %(publication_message)s,
     (SELECT abstractid FROM abstract_insertion),
     (SELECT licenseid FROM license_lookup),
     DEFAULT, DEFAULT,
     %(authors)s, DEFAULT, %(copyright_holders)s,
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
    ((SELECT module_ident FROM module_insertion), 5, %(editors)s))
SELECT module_ident, ident_hash FROM module_insertion
"""

# Constructs a table for mapping file data, filename
# and metadata. It should look like this:
#
# row_number | filename | mimetype
# ------------+------------------+------------
# 1 | a.txt | text/plain
# ------------+------------------+------------
# 2 | index.cnxml.html | text/html
#
# This table is used for joining with the result from file_insertion:
#
# fileid | md5 | row_number
# --------+----------------------------------+------------
# 19 | 0ab908a54aa2e7e8ae52f7cfd92c79f4 | 1
# --------+----------------------------------+------------
# 20 | 11ddd7ab03313249c3bca3aba8cdc257 | 2
#
# So in the end we'll have a table with all fields:
# fileid, md5, row_number, filename and mimetype
MODULE_FILES_INSERTION_TEMPLATE = """\
WITH file_insertion1 AS (
  -- Note, the md5 hash is generated on insertion through a trigger.
  INSERT INTO files (file)
  VALUES {file_values}
  RETURNING fileid, md5
  ),
file_insertion AS (
  SELECT *, ROW_NUMBER() OVER () FROM file_insertion1
  ),
module_file_values AS ({module_file_values_sql}),
module_file_insertion AS (
  INSERT INTO module_files (module_ident, fileid, filename, mimetype)
  SELECT %(module_ident)s, fileid, filename, mimetype
  FROM
    file_insertion NATURAL JOIN module_file_values
  RETURNING fileid, filename
  )
SELECT filename, md5
FROM file_insertion f
JOIN module_file_insertion mf ON f.fileid = mf.fileid
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


def _insert_metadata(cursor, model, publisher, message):
    """Insert a module with the given ``metadata``."""
    params = model.metadata.copy()
    params['publisher'] = publisher
    params['publication_message'] = message
    params['_portal_type'] = _model_to_portaltype(model)
    params['authors'] = [parse_user_uri(x['id']) for x in params['authors']]

    # Assign the id and version if one is known.
    if model.ident_hash is not None:
        uuid, version = split_ident_hash(model.ident_hash,
                                         split_version=True)
        params['_uuid'] = uuid
        params['_major_version'], params['_minor_version'] = version
        # Format the statement to accept the identifiers.
        stmt = MODULE_INSERTION_TEMPLATE.format(**{
            '__uuid__': "%(_uuid)s::uuid",
            '__major_version__': "%(_major_version)s",
            '__minor_version__': "%(_minor_version)s",
            })
    else:
        # Format the statement for defaults.
        stmt = MODULE_INSERTION_TEMPLATE.format(**{
            '__uuid__': "DEFAULT",
            '__major_version__': "DEFAULT",
            '__minor_version__': "DEFAULT",
            })

    cursor.execute(stmt, params)
    return cursor.fetchone()


def _insert_files(cursor, module_ident, files):
    """Insert files and relates them to a document.
    ``files`` should be a list of dicts::

        [{'filename': 'a.txt', 'mimetype': 'text/plain',
          'data': 'content of a.txt'},
         ...]

    This returns a list of filenames and hashes.
    """
    module_file_values = []
    file_values = []
    hashes = {}
    params = {'module_ident': module_ident}
    for i, file_ in enumerate(files):
        names = {
                'row': i + 1,
                'document': 'document{}'.format(i + 1),
                'filename': 'filename{}'.format(i + 1),
                'mimetype': 'mimetype{}'.format(i + 1),
                }
        params.update({
            names['document']: memoryview(file_['data']),
            names['filename']: file_['filename'],
            names['mimetype']: file_['mimetype'],
            })

        file_values.append('(%({document})s)'.format(**names))
        module_file_values.append("""\
                SELECT {row} AS row_number,
                       %({filename})s AS filename,
                       %({mimetype})s AS mimetype"""
                .format(**names))

    if file_values:
        stmt = MODULE_FILES_INSERTION_TEMPLATE.format(**{
            'file_values': ','.join(file_values),
            'module_file_values_sql': ' UNION ALL '.join(module_file_values),
            })
        cursor.execute(stmt, params)
        hashes = dict(list(cursor.fetchall()))

    return hashes


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
    module_ident, ident_hash = _insert_metadata(cursor, model, publisher, message)
    if isinstance(model, Document):
        files = [
                {
                    'filename': 'index.cnxml.html',
                    'mimetype': 'text/html',
                    'data': model.html.encode('utf-8'),
                    },
                ]
        for resource in model.resources:
            files.append({
                'filename': resource.filename,
                'mimetype': resource.media_type,
                'data': resource.data.read(),
                })
        file_hashes = _insert_files(cursor, module_ident, files)
    elif isinstance(model, Binder):
        tree = cnxepub.model_to_tree(model)
        tree = _insert_tree(cursor, tree)
    return ident_hash
