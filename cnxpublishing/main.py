# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import tempfile

from pyramid.config import Configurator
from pyramid import security
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.session import SignedCookieSessionFactory
from pyramid_multiauth import MultiAuthenticationPolicy

from .authnz import APIKeyAuthenticationPolicy


__version__ = '0.1'
__name__ = 'cnxpublishing'


def declare_routes(config):
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


def _parse_api_key_lines(settings):
    """Parse the api-key lines from the settings."""
    api_key_entities = []
    for line in settings['api-key-authnz'].split('\n'):
        if not line.strip():
            continue
        entity = [x.strip() for x in line.split(',') if x.strip()]
        api_key_entities.append(entity)
    return api_key_entities


def main(global_config, **settings):
    """Application factory"""
    config = Configurator(settings=settings, root_factory=RootFactory)
    declare_routes(config)

    session_factory = SignedCookieSessionFactory(
        settings.get('session_key', 'itsaseekreet'))
    config.set_session_factory(session_factory)

    api_key_entities = _parse_api_key_lines(settings)
    api_key_authn_policy = APIKeyAuthenticationPolicy(api_key_entities)
    # FIXME T'is impossible to 'include' openstax-accounts as it is.
    from openstax_accounts.stub import StubAuthenticationPolicy
    openstax_authn_policy = StubAuthenticationPolicy(users=settings.get('openstax_accounts.stub.users'))
    config.add_route('stub-login-form', '/stub-login-form')
    config.scan(package='openstax_accounts.stub')
    # /FIXME
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
        (security.Allow, 'group:trusted-publishers',
         ('publish.create-identifier',
          'publish.remove-identifier',)),
        security.DENY_ALL,
        )

    def __init__(self, request):
        self.request = request

    def __getitem__(self, key):
        raise KeyError(key)
