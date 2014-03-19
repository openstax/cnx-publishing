# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###



def add_publication(cursor, epub, epub_filepath):
    """Adds a publication entry and makes each item
    a pending document.
    """
    raise NotImplementedError()


def poke_publication_state(publication_id):
    """Invoked to poke at the publication to update and acquire its current
    state. This is used to persist the publication to archive.
    """
    raise NotImplementedError()
