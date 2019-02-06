# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from pyramid import httpexceptions
from pyramid.view import view_config

from ..db import poke_publication_state, db_connect


@view_config(route_name='moderation', request_method='GET',
             accept="application/json",
             renderer='json', permission='moderate', http_cache=0)
def get_moderation(request):
    """Return the list of publications that need moderation."""
    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            cursor.execute("""\
SELECT row_to_json(combined_rows) FROM (
  SELECT id, created, publisher, publication_message,
         (select array_agg(row_to_json(pd))
          from pending_documents as pd
          where pd.publication_id = p.id) AS models
  FROM publications AS p
  WHERE state = 'Waiting for moderation') AS combined_rows""")
            moderations = [x[0] for x in cursor.fetchall()]

    return moderations


@view_config(route_name='moderate', request_method='POST',
             accept="application/json", permission='moderate', http_cache=0)
def post_moderation(request):
    publication_id = request.matchdict['id']
    posted = request.json
    if 'is_accepted' not in posted \
       or not isinstance(posted.get('is_accepted'), bool):
        raise httpexceptions.HTTPBadRequest(
            "Missing or invalid 'is_accepted' value.")
    is_accepted = posted['is_accepted']

    with db_connect() as db_conn:
        with db_conn.cursor() as cursor:
            if is_accepted:
                # Give the publisher moderation approval.
                cursor.execute("""\
UPDATE users SET (is_moderated) = ('t')
WHERE username = (SELECT publisher FROM publications
                  WHERE id = %s and state = 'Waiting for moderation')""",
                               (publication_id,))
                # Poke the publication into a state change.
                poke_publication_state(publication_id, cursor)
            else:
                # Reject! And Vacuum properties of the publication
                #   record to /dev/null.
                cursor.execute("""\
UPDATE users SET (is_moderated) = ('f')
WHERE username = (SELECT publisher FROM publications
                  WHERE id = %sand state = 'Waiting for moderation')""",
                               (publication_id,))
                cursor.execute("""\
UPDATE publications SET (epub, state) = (null, 'Rejected')
WHERE id = %s""", (publication_id,))

    return httpexceptions.HTTPAccepted()


@view_config(route_name='admin-moderation', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.html",
             permission='moderate', http_cache=0)
@view_config(route_name='moderation-rss', request_method='GET',
             renderer="cnxpublishing.views:templates/moderations.rss",
             permission='view', http_cache=0)
def admin_moderations(request):  # pragma: no cover
    return {'moderations': get_moderation(request)}
