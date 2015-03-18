# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
"""\
Authentication and authorization policies for the publication application.
"""
from zope.interface import implementer
from pyramid.interfaces import IAuthenticationPolicy
from pyramid import security


@implementer(IAuthenticationPolicy)
class APIKeyAuthenticationPolicy(object):
    """Authentication using preconfigured API keys"""

    def __init__(self, entities=None):
        """The ``entities`` value is a three value
        tuple containing the api-key, user-id and list of groups.
        """
        self._api_key_index = {}
        self._principals = []  # (<uid>, [<group>, ...],)
        entities = entities or []
        for i, entity in enumerate(entities):
            key = entity[0]
            self._principals.insert(i, entity[1:])
            self._api_key_index[key] = i

    def _discover_requesting_party(self, request):
        """With the request object, discover who is making the request.
        Returns both the api-key and the principal-id
        """
        user_id = None
        api_key = request.headers.get('x-api-key', None)
        try:
            principal_index = self._api_key_index[api_key]
        except KeyError:
            principal_index = None
        if principal_index is not None:
            user_id = self._principals[principal_index][0]
        return api_key, user_id

    def authenticated_userid(self, request):
        api_key, user_id = self._discover_requesting_party(request)

    # We aren't using a persistent store, for these,
    # so the implementation can be the same.
    unauthenticated_userid = authenticated_userid

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as Everyone and
        Authenticated. """
        api_key, user_id = self._discover_requesting_party(request)
        if api_key is None or user_id is None:
            return []
        principals = list(self._principals[self._api_key_index[api_key]])
        principals.append(security.Everyone)
        principals.append(security.Authenticated)
        return principals

    def remember(self, request, principal, **kw):
        return []  # No session information is saved when using API keys.

    def forget(self, request):
        return []  # No need to forget when everything is already forgotten.
