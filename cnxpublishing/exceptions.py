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
    _message_template = None

    def __init__(self, publication_id=None,
                 epub_filename=None, pending_document_id=None,
                 pending_ident_hash=None):
        """All these parameters are optional, because the raising code
        usually doesn't have enough information to fill in the details.
        """
        self.publication_id = publication_id
        self.epub_filename = epub_filename
        self.pending_document_id = pending_document_id
        self.pending_ident_hash = pending_ident_hash

    def __repr__(self):
        return "{}: {}".format(self.__class__.__name__, self.__dict__)

    def __str__(self):
        return repr(self)

    @property
    def message(self):
        if self._message_template is not None:
            msg = self._message_template.format(**self.__dict__)
        else:
            msg = repr(self)
        return msg

    @property
    def args(self):
        return (self.message, self.__dict__,)

    @property
    def __dict__(self):
        """Render the except to dict"""
        data = {
            'code': self.code,
            'type': self.__class__.__name__,
            'publication_id': self.publication_id,
            'epub_filename': self.epub_filename,
            'pending_document_id': self.pending_document_id,
            'pending_ident_hash': self.pending_ident_hash,
            }
        return data


class MissingRequiredMetadata(PublicationException):
    """Raised when an incoming publication lacks a required metadata value."""
    code = 9
    _message_template = "Missing metadata for '{key}'."

    def __init__(self, key):
        """``key`` is the name/label/field/key of the missing metadata."""
        super(MissingRequiredMetadata, self).__init__()
        self._key = key

    @property
    def __dict__(self):
        data = super(MissingRequiredMetadata, self).__dict__
        data['key'] = self._key
        return data


class InvalidLicense(PublicationException):
    """Raised when a incoming publication is itself under or
    child contents under an invalid/unrecognized license.
    """
    code = 10
    _message_template = "Invalid license: {value}"

    def __init__(self, value):
        """``value`` is the invalid license."""
        super(InvalidLicense, self).__init__()
        self._value = value

    @property
    def __dict__(self):
        data = super(InvalidLicense, self).__dict__
        data['value'] = self._value
        return data


class InvalidRole(PublicationException):
    """Raised when an incoming publication contains an invalid
    role value.
    """
    code = 11
    # TODO Should probably make this less cryptic.
    #      It should probably answer, "Why is this invalid?"
    _message_template = "Invalid role for '{key}': {value}"

    def __init__(self, metadata_key, value):
        """``metadata_key`` tells which metadata role name the
        invalid role is under. ``value`` is the invalid role."""
        super(InvalidRole, self).__init__()
        self._key = metadata_key
        self._value = value

    @property
    def __dict__(self):
        data = super(InvalidRole, self).__dict__
        data['key'] = self._key
        data['value'] = self._value
        return data
