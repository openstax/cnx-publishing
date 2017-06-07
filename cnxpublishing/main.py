# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os
import tempfile

from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options
from cnxarchive.utils import join_ident_hash
from openstax_accounts.interfaces import IOpenstaxAccountsAuthenticationPolicy
from pyramid.config import Configurator
from pyramid import security
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.httpexceptions import default_exceptionresponse_view
from pyramid.session import SignedCookieSessionFactory
from pyramid_multiauth import MultiAuthenticationPolicy


__version__ = '0.1'
__name__ = 'cnxpublishing'


# Provides a means of caching function results.
# (This is reassigned with configuration in ``main()``.)
cache = CacheManager()


def find_migrations_directory():  # pragma: no cover
    """Finds and returns the location of the database migrations directory.
    This function is used from a setuptools entry-point for db-migrator.
    """
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(here, 'sql/migrations')


def make_wsgi_app(global_config, **settings):
    """Application factory"""
    from .config import configure
    return configure(settings).make_wsgi_app()
