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
SELECT ident_hash FROM module_insertion
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
WITH module AS (
  SELECT module_ident
  FROM modules
  WHERE uuid||'@'||concat_ws('.',major_version,minor_version) = %(ident_hash)s
  ),
file_insertion1 AS (
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
  SELECT module_ident, fileid, filename, mimetype
  FROM
    module,
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
    ident_hash = cursor.fetchone()[0]
    return ident_hash


def _insert_files(cursor, ident_hash, files):
    """Insert files and relates them to a document.
    ``files`` should be a list of dicts::

        [{'filename': 'a.txt', 'mimetype': 'text/plain',
          'data': 'content of a.txt'},
         ...]

    This returns a list of filenames and hashes.
    """
    raise NotImplementedError()


def _insert_tree(cursor, tree, parent_id=None, index=0):
    """Inserts a binder tree into the archive."""
    raise NotImplementedError()


def publish_model(cursor, model, publisher, message):
    """Publishes the ``model`` and return its ident_hash."""
    publishers = publisher
    if isinstance(publishers, list) and len(publishers) > 1:
        raise ValueError("Only one publisher is allowed. '{}' "
                         "were given: {}" \
                         .format(len(publishers), publishers))
    ident_hash = _insert_metadata(cursor, model, publisher, message)
    if isinstance(model, Document):
        files = []  # TODO
        # file_hashes = _insert_files(cursor, ident_hash, files)
    elif isinstance(model, Binder):
        tree = {}  # TODO
        # tree = _insert_tree(cursor, tree)
    return ident_hash
