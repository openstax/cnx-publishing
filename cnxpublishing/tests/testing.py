# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os

import psycopg2
from pyramid.paster import get_appsettings


__all__ = ('integration_test_settings', 'db_connection_factory',)


here = os.path.abspath(os.path.dirname(__file__))


def integration_test_settings():
    """Integration settings initializer"""
    config_uri = os.environ.get('TESTING_CONFIG', None)
    if config_uri is None:
        project_root = os.path.join(here, '..', '..')
        config_uri = os.path.join(project_root, 'testing.ini')
    settings = get_appsettings(config_uri)
    return settings


def db_connection_factory(connection_string=None):
    if connection_string is None:
        settings = integration_test_settings()
        from ..config import CONNECTION_STRING
        connection_string = settings[CONNECTION_STRING]

    def db_connect():
        return psycopg2.connect(connection_string)

    return db_connect
