# -*- coding: utf-8 -*-
from pyramid.httpexceptions import default_exceptionresponse_view


def declare_api_routes(config):
    """Declaration of routing"""
    add_route = config.add_route
    add_route('get-content', '/contents/{ident_hash}')
    add_route('get-resource', '/resources/{hash}')

    # User actions API
    add_route('license-request', '/contents/{uuid}/licensors')
    add_route('roles-request', '/contents/{uuid}/roles')
    add_route('acl-request', '/contents/{uuid}/permissions')

    # Publishing API
    add_route('publications', '/publications')
    add_route('get-publication', '/publications/{id}')
    add_route('publication-license-acceptance',
              '/publications/{id}/license-acceptances/{uid}')
    add_route('publication-role-acceptance',
              '/publications/{id}/role-acceptances/{uid}')
    # TODO (8-May-12017) Remove because the term collate is being phased out.
    add_route('collate-content', '/contents/{ident_hash}/collate-content')
    add_route('bake-content', '/contents/{ident_hash}/baked')

    # Moderation routes
    add_route('moderation', '/moderations')
    add_route('moderate', '/moderations/{id}')
    add_route('moderation-rss', '/feeds/moderations.rss')

    # API Key routes
    add_route('api-keys', '/api-keys')
    add_route('api-key', '/api-keys/{id}')


def declare_browsable_routes(config):
    """Declaration of routes that can be browsed by users."""
    # This makes our routes slashed, which is good browser behavior.
    config.add_notfound_view(default_exceptionresponse_view,
                             append_slash=True)

    add_route = config.add_route
    add_route('admin-index', '/a/')
    add_route('admin-moderation', '/a/moderation/')
    add_route('admin-api-keys', '/a/api-keys/')
    add_route('admin-add-site-messages', '/a/site-messages/',
              request_method='GET')
    add_route('admin-add-site-messages-POST', '/a/site-messages/',
              request_method='POST')
    add_route('admin-delete-site-messages', '/a/site-messages/',
              request_method='DELETE')
    add_route('admin-edit-site-message', '/a/site-messages/{id}/',
              request_method='GET')
    add_route('admin-edit-site-message-POST', '/a/site-messages/{id}/',
              request_method='POST')

    add_route('admin-content-status', '/a/content-status/')
    add_route('admin-content-status-single', '/a/content-status/{uuid}')

    add_route('admin-print-style', '/a/print-style/')
    add_route('admin-print-style-single', '/a/print-style/{style}')


def includeme(config):
    """Declare all routes."""
    config.include('pyramid_jinja2')
    config.add_jinja2_renderer('.html')
    config.add_jinja2_renderer('.rss')
    config.add_static_view(name='/a/static', path="cnxpublishing:static/")

    # Commit the configuration otherwise the jija2_env won't have
    # a `globals` assignment.
    config.commit()

    # Place a few globals in the template environment.
    from cnxdb.ident_hash import join_ident_hash
    for ext in ('.html', '.rss',):
        jinja2_env = config.get_jinja2_environment(ext)
        jinja2_env.globals.update(
            join_ident_hash=join_ident_hash,
        )

    declare_api_routes(config)
    declare_browsable_routes(config)
