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

from cnxpublishing.db import db_connect
from cnxpublishing.main import cache


ALL_KEY_INFO_SQL_STMT = "SELECT id, key, name, groups FROM api_keys"


@cache.cache(expire=60*60*24)  # cache for one day
def lookup_api_key_info():
    """Given a dbapi cursor, lookup all the api keys and their information."""
    info = {}
    with db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(ALL_KEY_INFO_SQL_STMT)
            for row in cursor.fetchall():
                id, key, name, groups = row
                user_id = "api_key:{}".format(id)
                info[key] = dict(id=id, user_id=user_id,
                                 name=name, groups=groups)
    return info


@implementer(IAuthenticationPolicy)
class APIKeyAuthenticationPolicy(object):
    """Authentication using preconfigured API keys"""

    @property
    def user_info_by_key(self):
        return lookup_api_key_info()

    def _discover_requesting_party(self, request):
        """With the request object, discover who is making the request.
        Returns both the api-key and the principal-id
        """
        user_id = None
        api_key = request.headers.get('x-api-key', None)
        try:
            principal_info = self.user_info_by_key[api_key]
        except KeyError:
            principal_info = None
        if principal_info is not None:
            user_id = principal_info['user_id']
        return api_key, user_id, principal_info

    def authenticated_userid(self, request):
        api_key, user_id, _ = self._discover_requesting_party(request)
        return user_id

    # We aren't using a persistent store, for these,
    # so the implementation can be the same.
    unauthenticated_userid = authenticated_userid

    def effective_principals(self, request):
        """ Return a sequence representing the effective principals
        including the userid and any groups belonged to by the current
        user, including 'system' groups such as Everyone and
        Authenticated. """
        api_key, user_id, info = self._discover_requesting_party(request)
        if api_key is None or user_id is None:
            return []
        try:
            principals = list(info['groups'])
        except TypeError:
            principals = []
        principals.append(security.Everyone)
        principals.append(security.Authenticated)
        return principals

    def remember(self, request, principal, **kw):
        return []  # No session information is saved when using API keys.

    def forget(self, request):
        return []  # No need to forget when everything is already forgotten.


__all__ = (
    'APIKeyAuthenticationPolicy',
    'lookup_api_key_info',
    )
