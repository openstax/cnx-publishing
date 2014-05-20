# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###
import json


class PublicationException(Exception):
    """Base class for more detailed exceptions.
    This exception is utilized when and only when a publication
    has been parsed correctly, but one or more pieces of the data
    is incorrect.
    """

    def __init__(self, publication_id=None, message=None,
                 epub_filename=None, pending_document_id=None):
        self.publication_id = publication_id
        self.epub_filename = epub_filename
        self.pending_document_id = pending_document_id
        self._message = message

    @property
    def description(self):
        # TODO Setting the logger level to 'debug' should dump as much
        # information about the publication and model as possible.
        desc = "publication_id = {} & pending_document_id = {} " \
               "& epub_filename = {} " \
               .format(self.publication_id, self.pending_document_id,
                       self.epub_filename)
        return desc

    @property
    def args(self):
        if self._message is not None:
            message_arg = "{}  {}".format(self._message, self.description)
        else:
            message_arg = self.description
        return (message_arg,)

    def to_json(self):
        """Render the except to json"""
        data = {
            'publication_id': self.publication_id,
            'epub_filename': self.epub_filename,
            'pending_document_id': self.pending_document_id,
            'message': self._message,
            }
        return json.dumps(data)


class InvalidLicense(PublicationException):
    """Raised when a incoming publication is itself under or
    child contents under an invalid/unrecognized license.
    """

    
