5# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import cnxepub
import psycopg2
from pyramid.view import view_config
from pyramid import httpexceptions

from . import config
from .db import add_publication, poke_publication_state


@view_config(route_name='publications', request_method='POST', renderer='json')
def publish(request):
    """Accept a publication request at form value 'epub'"""
    if 'epub' not in request.POST:
        raise httpexceptions.HTTPBadRequest("Missing EPUB in POST body.")

    epub_upload = request.POST['epub']
    try:
        epub = cnxepub.EPUB.from_file(epub_upload.file)
    except:
        raise httpexceptions.HTTPBadRequest('Format not recognized.')

    settings = request.registry.settings
    # Make a publication entry in the database for status checking
    # the publication. This also creates publication entries for all
    # of the content in the EPUB.
    with psycopg2.connect(settings[config.CONNECTION_STRING]) as db_conn:
        with db_conn.cursor() as cursor:
            publication_id, publications = add_publication(cursor,
                                                           epub,
                                                           epub_upload.file)

    # Poke at the publication & lookup its state.
    state = poke_publication_state(publication_id)

    response_data = {
        'publication': publication_id,
        'mapping': publications,
        'state': state,
        }
    return response_data


@view_config(route_name='get-publication', request_method=['GET', 'HEAD'],
             renderer='json')
def get_publication(request):
    """Lookup publication state"""
    publication_id = request.matchdict['id']
    state = poke_publication_state(publication_id)
    response_data = {
        'publication': publication_id,
        'state': state,
        }
    return response_data
