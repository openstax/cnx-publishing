# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import collections
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
try:
    from urllib.parse import unquote
except ImportError:
    from urllib2 import unquote

from cnxcommon.urlslug import generate_slug
from cnxdb.ident_hash import (
    join_ident_hash as upstream_join_ident_hash,
    split_ident_hash as upstream_split_ident_hash,
    IdentHashMissingVersion,
)


def issequence(t):
    """Test if `t` is a Sequence"""
    return isinstance(t, collections.Sequence) \
        and not isinstance(t, basestring)


def parse_archive_uri(uri):
    """Given an archive URI, parse to a split ident-hash."""
    parsed = urlparse(uri)
    path = parsed.path.rstrip('/').split('/')
    ident_hash = path[-1]
    ident_hash = unquote(ident_hash)
    return ident_hash


def parse_user_uri(uri, type_='cnx-id'):
    if type_ != 'cnx-id':
        raise ValueError("Can't parse a user uri of type '{}'."
                         .format(type_))
    # FIXME A URI to an osc-accounts (i.e. cnx-id) does not exist.
    # We have added a unique UUID for each user; and that is what
    # we will use in epub import/export for now.
    return uri


def split_ident_hash(*args, **kwargs):
    try:
        return upstream_split_ident_hash(*args, **kwargs)
    except IdentHashMissingVersion as e:
        version = None
        if kwargs.get('split_version'):
            version = (None, None)
        return e.id, version


join_ident_hash = upstream_join_ident_hash


def amend_tree_with_slugs(tree, title_seq=[]):
    """Places the 'slug' key value pair within the tree's node items."""
    title_seq = title_seq + [tree['title']]
    tree['slug'] = generate_slug(*title_seq)
    if 'contents' in tree:
        for node in tree['contents']:
            amend_tree_with_slugs(node, title_seq)


__all__ = (
    'amend_tree_with_slugs',
    'issequence',
    'join_ident_hash',
    'parse_archive_uri',
    'parse_user_uri',
    'split_ident_hash',
)
