# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import os

from pyramid.paster import get_appsettings


__all__ = ('integration_test_settings',)


here = os.path.abspath(os.path.dirname(__file__))


def integration_test_settings():
    """Integration settings initializer"""
    config_uri = os.environ.get('TESTING_CONFIG', None)
    if config_uri is None:
        project_root = os.path.join(here, '..', '..')
        config_uri = os.path.join(project_root, 'testing.ini')
    settings = get_appsettings(config_uri)
    return settings
