# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse
try:
    from urllib.parse import unquote
except ImportError:
    from urllib2 import unquote


__all__ = (
    'parse_archive_uri', 'parse_user_uri',
    )


def parse_archive_uri(uri):
    """Given an archive URI, parse to a split ident-hash."""
    parsed = urlparse(uri)
    path = parsed.path.rstrip('/').split('/')
    try:
        ident_hash = path[-1]
    except:
        raise ValueError("Expected a path like /contents/{ident_hash}, "
                         "got '{}' instead.".format(path))
    ident_hash = unquote(ident_hash)
    return ident_hash


def parse_user_uri(uri, type_='cnx-id'):
    if type_ != 'cnx-id':
        raise ValueError("Can't parse a user uri of type '{}'." \
                         .format(type_))
    # FIXME A URI to an osc-accounts (i.e. cnx-id) does not exist.
    # We have added a unique UUID for each user; and that is what
    # we will use in epub import/export for now.
    return uri
