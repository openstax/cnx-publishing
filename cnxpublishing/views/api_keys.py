# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import psycopg2
from pyramid.view import view_config

from .. import config


@view_config(route_name='api-keys', request_method='GET',
             accept="application/json",
             renderer='json', permission='administer')
def get_api_keys(request):
    """Return the list of API keys."""
    settings = request.registry.settings

    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
  SELECT id, key, name, groups FROM api_keys
) AS combined_rows""")
            api_keys = [x[0] for x in cursor.fetchall()]

    return api_keys

# TODO Add CRUD views for API Keys...
