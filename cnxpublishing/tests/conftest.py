# -*- coding: utf-8 -*-
import os

import pytest
import cnxepub
from pyramid import testing

from . import use_cases
from .testing import config_uri, integration_test_settings


@pytest.fixture(autouse=True, scope='session')
def assign_testing_env_vars():
    os.environ['PYRAMID_INI'] = config_uri()


# Override cnx-db's connection_string fixture.
@pytest.fixture(scope='session')
def db_connection_string():
    """Returns a connection string"""
    from cnxpublishing.config import CONNECTION_STRING
    return integration_test_settings()[CONNECTION_STRING]


@pytest.fixture
def complex_book_one(db_cursor):
    # FIXME This uses `None` as the test_case argument.
    binder = use_cases.setup_COMPLEX_BOOK_ONE_in_archive(None, db_cursor)
    idents = map(lambda m: m.ident_hash,
                 cnxepub.flatten_to(binder, lambda m: True))
    db_cursor.connection.commit()
    db_cursor.execute(
        "SELECT ident_hash(uuid, major_version, minor_version), module_ident "
        "FROM modules "
        "WHERE ident_hash(uuid, major_version, minor_version) = ANY (%s)",
        (idents,))
    ident_hash_to_module_ident_mapping = dict(db_cursor.fetchall())
    for m in cnxepub.flatten_to(binder, lambda m: bool(m.ident_hash)):
        module_ident = ident_hash_to_module_ident_mapping[m.ident_hash]
        ident_hash_to_module_ident_mapping[m.ident_hash] = module_ident
    return (binder, ident_hash_to_module_ident_mapping,)


@pytest.fixture(scope='session')
def celery_includes():
    return [
        'celery.contrib.testing.tasks',  # For the shared 'ping' task.
        'cnxpublishing.subscribers',
    ]
