# -*- coding: utf-8 -*-
import os

import cnxepub
import pytest

from . import use_cases
from .testing import config_uri, integration_test_settings


@pytest.fixture(autouse=True, scope='session')
def assign_testing_env_vars():
    os.environ['PYRAMID_INI'] = config_uri()


# Override cnx-db's fixture.
@pytest.fixture
def db_init_and_wipe(db_engines, db_wipe, db_init):
    """Combination of the initialization and wiping procedures."""
    # The argument order, 'wipe' then 'init' is important, because
    #   db_wipe assumes you want to start with a clean database.
    # This closes any existing connections, which is sometimes necessary
    #   because previous connections may not be virtualenv initialized.
    for engine in db_engines.values():
        engine.dispose()


# Override cnx-db's settings fixture.
@pytest.fixture(scope='session')
def db_settings():
    """Returns database connection settings. These settings are provided
    in a similar format to that of `cnxdb.config.discover_settings`.

    """
    from cnxpublishing.config import CONNECTION_STRING
    url = integration_test_settings()[CONNECTION_STRING]
    return {
        'db.common.url': url,
        'db.super.url': url,
    }


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


@pytest.fixture
def complex_book_one_v2(db_cursor):
    # FIXME This uses `None` as the test_case argument.
    binder = use_cases.setup_COMPLEX_BOOK_ONE_v2_in_archive(None, db_cursor)
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


@pytest.fixture
def recipes(db_cursor):
    # FIXME This uses `None` as the test_case argument.
    return use_cases.setup_RECIPES_in_archive(None, db_cursor)


@pytest.fixture(scope='session')
def celery_includes():
    return [
        'celery.contrib.testing.tasks',  # For the shared 'ping' task.
        'cnxpublishing.subscribers',
    ]


@pytest.fixture(scope='session')
def celery_config():
    from .testing import integration_test_settings
    settings = integration_test_settings()
    return {
        'broker_url': settings['celery.broker'],
        'result_backend': settings['celery.backend'],
    }


@pytest.fixture(scope='session')
def celery_parameters():
    from ..tasks import PyramidAwareTask
    return {
        'name': 'tasks',
        'task_cls': PyramidAwareTask,
    }


@pytest.fixture
def scoped_pyramid_app(celery_app, db_init_and_wipe):
    from .testing import integration_test_settings
    settings = integration_test_settings()
    from pyramid import testing
    config = testing.setUp(settings=settings)
    # Register the routes for reverse generation of urls.
    config.include('cnxpublishing.views')
    # Tack the pyramid config on the celery app.
    # See cnxpublishing.tasks.includeme
    config.registry.celery_app = celery_app
    config.registry.celery_app.conf['pyramid_config'] = config
    config.scan('cnxpublishing.subscribers')

    # Celery only creates the tables once per session.  This gets celery to
    # create the tables again (as a side effect of a new session manager) since
    # we are starting with an empty database.
    from celery.backends.database.session import SessionManager
    celery_app.backend.ResultSession(SessionManager())

    # Initialize the authentication policy.
    from openstax_accounts.stub import main
    main(config)
    config.commit()
    yield config

    testing.tearDown()

    # Force celery to create a new event loop.
    # See https://github.com/celery/celery/issues/4088
    from kombu.asynchronous import set_event_loop
    set_event_loop(None)
