# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import functools

import psycopg2
from cnxdb.init import init_db as _init_db
from pyramid.paster import get_appsettings


__all__ = (
    'TEST_DATA_DIR',
    'integration_test_settings',
    'db_connection_factory', 'db_connect',
)


here = os.path.abspath(os.path.dirname(__file__))
TEST_DATA_DIR = os.path.join(here, 'data')


def config_uri():
    """Return the file path of the testing config uri"""
    config_uri = os.environ.get('TESTING_CONFIG', None)
    if config_uri is None:
        config_uri = os.path.join(here, 'testing.ini')
    return config_uri


def integration_test_settings():
    """Integration settings initializer"""
    settings = get_appsettings(config_uri())
    # See also cnxpublishing.config.expandvars_dict
    settings = {
        key: os.path.expandvars(value)
        for key, value in settings.iteritems()
    }
    return settings


def db_connection_factory(connection_string=None):
    if connection_string is None:
        settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        connection_string = settings[CONNECTION_STRING]

    def db_connect():
        return psycopg2.connect(connection_string)

    return db_connect


def db_connect(method):
    """Decorator for methods that need to use the database

    Example:
    @db_connect
    def setUp(self, cursor):
        cursor.execute(some_sql)
        # some other code
    """
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        connect = db_connection_factory()
        with connect() as db_connection:
            with db_connection.cursor() as cursor:
                return method(self, cursor, *args, **kwargs)
    return wrapped


def init_db(db_conn_str):
    venv = os.getenv('AS_VENV_IMPORTABLE', 'true').lower() == 'true'
    from sqlalchemy import create_engine
    engine = create_engine(db_conn_str)
    _init_db(engine, venv)
