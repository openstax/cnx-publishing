# -*- coding: utf-8 -*-
import os

from pyramid.paster import get_appsettings

from .config import configure


pyramid_ini = os.environ['PYRAMID_INI']
settings = get_appsettings(pyramid_ini)
app = configure(settings).make_celery_app()
