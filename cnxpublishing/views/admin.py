# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from pyramid import httpexceptions
from pyramid.view import view_config

from .moderation import get_moderation
from .api_keys import get_api_keys


@view_config(route_name='admin-index', request_method='GET',
             renderer="cnxpublishing.views:templates/index.html",
             permission='preview')
def admin_index(request):  # pragma: no cover
    return {
        'navigation': [
            {'name': 'Moderation List',
             'uri': request.route_url('admin-moderation'),
             },
            {'name': 'API Keys',
             'uri': request.route_url('admin-api-keys'),
             },
            ],
        }


@view_config(route_name='admin-moderation', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.html",
             permission='moderate')
@view_config(route_name='moderation-rss', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.rss",
             permission='view')
def admin_moderations(request):  # pragma: no cover
    return {'moderations': get_moderation(request)}


@view_config(route_name='admin-api-keys', request_method='GET',
             renderer="cnxpublishing.views:templates/api-keys.html",
             permission='administer')
def admin_api_keys(request):  # pragma: no cover
    # Easter Egg that will invalidate the cache, just hit this page.
    # FIXME Move this logic into the C[R]UD views...
    from ..authnz import lookup_api_key_info
    from ..main import cache
    cache.invalidate(lookup_api_key_info)

    return {'api_keys': get_api_keys(request)}
