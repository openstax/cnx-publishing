# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os

from ._version import get_versions


__version__ = get_versions()['version']
del get_versions
__name__ = 'cnxpublishing'


def find_migrations_directory():  # pragma: no cover
    """Finds and returns the location of the database migrations directory.
    This function is used from a setuptools entry-point for db-migrator.
    """
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(here, 'sql/migrations')


def make_wsgi_app(global_config, **settings):  # pragma: no cover
    """Application factory"""
    from .config import configure
    return configure(settings).make_wsgi_app()
