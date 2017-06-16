# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from cnxarchive.config import CONNECTION_STRING
from pyramid import security
from pyramid.config import Configurator


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

    def __getitem__(self, key):  # pragma: no cover
        raise KeyError(key)


def configure(settings):
    # Check for required settings
    settings['session_key'] = settings.get('session_key', 'itsaseekreet')
    # File uploads size limit in MB
    settings['file_upload_limit'] = int(settings.get('file_upload_limit', 50))
    assert 'channel_processing.channels' in settings, (
        'missing {} setting'.format('channel_processing.channels'))
    assert CONNECTION_STRING in settings, (
        'missing {} setting'.format(CONNECTION_STRING))

    # Create the configuration object
    config = Configurator(settings=settings, root_factory=RootFactory)
    config.include('.views')
    config.include('.session')
    config.include('.cache')
    config.include('.authnz')
    config.include('.tasks')

    config.scan(ignore=['cnxpublishing.tests', 'cnxpublishing.celery'])
    return config


__all__ = (
    'CONNECTION_STRING',
    'configure',
)
