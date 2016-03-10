# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013-2016, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
from pyramid import httpexceptions
from pyramid.view import forbidden_view_config


@forbidden_view_config()
def forbidden(request):
    if request.path.startswith('/a/'):
        if not request.unauthenticated_userid:
            path = request.route_path('login', _query={'redirect': '/a/'})
            return httpexceptions.HTTPFound(location=path)
    return httpexceptions.HTTPForbidden()
