# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os

import psycopg2


__all__ = ('initdb',)


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


def add_publication(cursor, epub, epub_filepath):
    """Adds a publication entry and makes each item
    a pending document.
    """
    raise NotImplementedError()


def poke_publication_state(publication_id):
    """Invoked to poke at the publication to update and acquire its current
    state. This is used to persist the publication to archive.
    """
    raise NotImplementedError()
