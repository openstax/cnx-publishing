# -*- coding: utf-8 -*-
from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options


def includeme(config):
    """Configures the caching manager"""
    settings = config.registry.settings
    # FIXME Don't import from main for this...
    from . import main
    main.cache = CacheManager(**parse_cache_config_options(settings))
