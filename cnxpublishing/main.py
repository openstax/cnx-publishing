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


def declare_api_routes(config):
    """Declaration of routing"""
    add_route = config.add_route
    add_route('get-content', '/contents/{ident_hash}')
    add_route('get-resource', '/resources/{hash}')

    # User actions API
    add_route('license-request', '/contents/{uuid}/licensors')
    add_route('roles-request', '/contents/{uuid}/roles')
    add_route('acl-request', '/contents/{uuid}/permissions')

    # Publishing API
    add_route('publications', '/publications')
    add_route('get-publication', '/publications/{id}')
    add_route('publication-license-acceptance',
              '/publications/{id}/license-acceptances/{uid}')
    add_route('publication-role-acceptance',
              '/publications/{id}/role-acceptances/{uid}')
    add_route('collate-content', '/contents/{ident_hash}/collate-content')

    # Moderation routes
    add_route('moderation', '/moderations')
    add_route('moderate', '/moderations/{id}')
    add_route('moderation-rss', '/feeds/moderations.rss')

    # API Key routes
    add_route('api-keys', '/api-keys')
    add_route('api-key', '/api-keys/{id}')


def declare_browsable_routes(config):
    """Declaration of routes that can be browsed by users."""
    # This makes our routes slashed, which is good browser behavior.
    config.add_notfound_view(default_exceptionresponse_view,
                             append_slash=True)

    add_route = config.add_route
    add_route('admin-index', '/a/')
    add_route('admin-moderation', '/a/moderation/')
    add_route('admin-api-keys', '/a/api-keys/')


def declare_routes(config):
    """Declare all routes."""
    config.include('pyramid_jinja2')
    config.add_jinja2_renderer('.html')
    config.add_jinja2_renderer('.rss')
    config.add_static_view(name='static', path="cnxpublishing:static/")
    # Place a few globals in the template environment.
    config.commit()
    for ext in ('.html', '.rss',):
        jinja2_env = config.get_jinja2_environment(ext)
        jinja2_env.globals.update(
            join_ident_hash=join_ident_hash,
            )

    declare_api_routes(config)
    declare_browsable_routes(config)


def main(global_config, **settings):
    """Application factory"""
    config = Configurator(settings=settings, root_factory=RootFactory)
    declare_routes(config)

    session_factory = SignedCookieSessionFactory(
        settings.get('session_key', 'itsaseekreet'))
    config.set_session_factory(session_factory)

    global cache
    cache = CacheManager(**parse_cache_config_options(settings))

    from .authnz import APIKeyAuthenticationPolicy
    api_key_authn_policy = APIKeyAuthenticationPolicy()
    config.include('openstax_accounts')
    openstax_authn_policy = config.registry.getUtility(
        IOpenstaxAccountsAuthenticationPolicy)
    policies = [api_key_authn_policy, openstax_authn_policy]
    authn_policy = MultiAuthenticationPolicy(policies)
    config.set_authentication_policy(authn_policy)
    authz_policy = ACLAuthorizationPolicy()
    config.set_authorization_policy(authz_policy)

    config.scan(ignore='cnxpublishing.tests')
    return config.make_wsgi_app()


class RootFactory(object):
    """Application root object factory.
    Everything is accessed from the root, so the acls defined here
    are applied to all requests.
    """

    __acl__ = (
        (security.Allow, security.Everyone, 'view'),
        (security.Allow, security.Authenticated, 'publish'),
        (security.Allow, 'g:trusted-publishers',
         ('publish.assign-acceptance',  # Used when assigning user actions
                                        # requests.
          'publish.remove-acceptance',
          'publish.assign-acl',  # Used when assigning access control on
                                 # documents.
          'publish.remove-acl',
          'publish.create-identifier',  # Used when content does not yet exist.
          'publish.remove-identifier',
          )),
        (security.Allow, 'g:publishers',
         ('publish.assign-acceptance',  # Used when assigning user actions
                                        # requests.
          'publish.remove-acceptance',
          'publish.assign-acl',  # Used when assigning access control on
                                 # documents.
          'publish.remove-acl',
          )),
        (security.Allow, 'g:reviewers', ('preview',)),
        (security.Allow, 'g:moderators', ('preview', 'moderate',)),
        (security.Allow, 'g:administrators',
         ('preview',
          'moderate',
          'administer')),
        security.DENY_ALL,
        )

    def __init__(self, request):
        self.request = request

    def __getitem__(self, key):
        raise KeyError(key)
