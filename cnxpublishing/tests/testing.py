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
    'TEST_DATA_DIR'
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


def _dsn_to_args(dsn):
    """Translates a libpq DSN to dict
    to be used with ``sqlalchemy.engine.url.URL``.

    """
    args = {'query': {}}
    import inspect
    from sqlalchemy.engine.url import URL
    url_args = inspect.getargspec(URL.__init__).args
    for item in dsn.split():
        name, value = item.split('=')
        if name == 'user':
            name = 'username'
        elif name == 'dbname':
            name = 'database'
        if name in url_args:
            args[name] = value
        else:
            args['query'][name] = value
    return args


def libpq_dsn_to_url(dsn):
    """Translate a libpq DSN to URL"""
    args = _dsn_to_args(dsn)
    from sqlalchemy.engine.url import URL
    url = URL('postgresql', **args)
    return str(url)


def init_db(db_conn_str):
    venv = os.getenv('AS_VENV_IMPORTABLE', 'true').lower() == 'true'
    from sqlalchemy import create_engine
    engine = create_engine(libpq_dsn_to_url(db_conn_str))
    _init_db(engine, venv)
