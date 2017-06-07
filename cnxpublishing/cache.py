# -*- coding: utf-8 -*-
from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options


# Provides a means of caching function results.
# (This is reassigned with configuration in ``includeme``.)
cache_manager = CacheManager()


def includeme(config):
    """Configures the caching manager"""
    global cache_manager
    settings = config.registry.settings
    cache_manager = CacheManager(**parse_cache_config_options(settings))
