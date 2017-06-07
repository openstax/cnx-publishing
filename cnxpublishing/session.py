# -*- coding: utf-8 -*-
from pyramid.session import SignedCookieSessionFactory


def includeme(config):
    """Configures the session manager"""
    settings = config.registry.settings
    session_factory = SignedCookieSessionFactory(settings['session_key'])
    config.set_session_factory(session_factory)
