# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2019, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from pyramid.view import view_config

from ..db import db_connect


@view_config(route_name='api-keys', request_method='GET',
             accept="application/json",
             renderer='json', permission='administer', http_cache=0)
def get_api_keys(request):
    """Return the list of API keys."""
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
  SELECT id, key, name, groups FROM api_keys
) AS combined_rows""")
            api_keys = [x[0] for x in cursor.fetchall()]

    return api_keys


@view_config(route_name='admin-api-keys', request_method='GET',
             renderer="cnxpublishing.views:templates/api-keys.html",
             permission='administer', http_cache=0)
def admin_api_keys(request):  # pragma: no cover
    # Easter Egg that will invalidate the cache, just hit this page.
    # FIXME Move this logic into the C[R]UD views...
    from ..authnz import lookup_api_key_info
    from ..cache import cache_manager
    cache_manager.invalidate(lookup_api_key_info)

    return {'api_keys': get_api_keys(request)}

# TODO Add CRUD views for API Keys...
