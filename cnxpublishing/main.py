# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import tempfile

from pyramid.config import Configurator


__version__ = '0.1'
__name__ = 'cnxpublishing'


def declare_routes(config):
    """Declaration of routing"""
    add_route = config.add_route
    add_route('get-content', '/contents/{ident_hash}')
    add_route('get-resource', '/resources/{hash}')
    add_route('publications', '/publications')
    add_route('get-publication', '/publications/{id}')


def main(global_config, **settings):
    """Application factory"""
    config = Configurator(settings=settings)
    declare_routes(config)

    config.scan(ignore='cnxpublishing.tests')
    return config.make_wsgi_app()
