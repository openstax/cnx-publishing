# -*- coding: utf-8 -*-
# ###
# Copyright (c) 2013, Rice University
# This software is subject to the provisions of the GNU Affero General
# Public License version 3 (AGPLv3).
# See LICENCE.txt for details.
# ###


# ###################### #
#   General Exceptions   #
# ###################### #

class UserFetchError(Exception):
    """Raised when a user's info cannot be retrieved from the accounts system.
    """

    def __init__(self, user_id):
        self.user_id = user_id

    @property
    def message(self):
        msg = "User, named '{}', cannot be found in the accounts system." \
            .format(self.user_id)
        return msg

    @property
    def args(self):
        return (self.message, self.__dict__,)


class DocumentLookupError(Exception):
    """Generally used when a document cannot be found."""


# ########################## #
#   Publication Exceptions   #
# ########################## #

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


class NotAllowed(PublicationException):
    """Raised when a user attempts to publish something they don't
    have permision to publish.
    """
    code = 8
    _message_template = "Not allowed to publish '{uuid}'."

    def __init__(self, uuid):
        """``uuid`` is the content identifier
        for which this exception applies.
        """
        super(NotAllowed, self).__init__()
        self._uuid = uuid

    @property
    def __dict__(self):
        data = super(NotAllowed, self).__dict__
        data['uuid'] = self._uuid
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


class InvalidMetadata(PublicationException):
    """Raised when an incoming publication has metadata
    but the value does not conform to the expected syntax, type
    or vocabulary.
    """
    code = 12
    _message_template = "Invalid value given for '{key}': {value}\n{message}"

    def __init__(self, metadata_key, value, original_exception=None):
        """``metadata_key`` tells which metadata has the
        invalid ``value``. If ``original_exception`` is supplied, it will be
        used to supply additional information.
        """
        super(InvalidMetadata, self).__init__()
        self._key = metadata_key
        self._value = value
        self._original_exception = original_exception

    @property
    def __dict__(self):
        data = super(InvalidMetadata, self).__dict__
        data['key'] = self._key
        data['value'] = self._value
        data['message'] = ''
        try:
            message = self._original_exception.message
        except AttributeError:
            pass
        else:
            data['message'] = message
        return data


class InvalidReference(PublicationException):
    """Raised when a Document contains an invalid reference to an internal
    Document or Resource.
    """

    code = 20
    _message_template = "Invalid reference at '{xpath}'."

    def __init__(self, reference):
        """``reference`` is the Reference object that contains
        the invalid reference.
        """
        super(InvalidReference, self).__init__()
        self._reference = reference

    @property
    def __dict__(self):
        data = super(InvalidReference, self).__dict__
        elm = self._reference.elm
        data['xpath'] = elm.getroottree().getpath(elm)
        data['value'] = self._reference.uri
        return data


class InvalidDocumentPointer(PublicationException):
    """Raised when a Document contains an invalid reference to an internal
    Document or Resource.
    """
    code = 21
    _message_template = "Invalid document pointer: {ident_hash}"

    def __init__(self, document_pointer, exists, is_document):
        """``document_pointer`` is the DocumentPointer object that contains
        the invalid reference.
        """
        super(InvalidDocumentPointer, self).__init__()
        self._document_pointer = document_pointer
        self._exists = bool(exists)
        self._is_document = bool(is_document)

    @property
    def __dict__(self):
        data = super(InvalidDocumentPointer, self).__dict__
        data['ident_hash'] = self._document_pointer.ident_hash
        data['exists'] = self._exists
        data['is_document'] = self._is_document
        return data


class ResourceFileExceededLimitError(PublicationException):
    """Raised when a user tries to publish a document with resource
    files bigger than the size limit
    """
    code = 22
    _message_template = ('Resource files cannot be bigger than {size_limit}MB'
                         ' ({filename})')

    def __init__(self, size_limit, filename):
        super(ResourceFileExceededLimitError, self).__init__()
        self._size_limit = size_limit
        self._filename = filename

    @property
    def __dict__(self):
        data = super(ResourceFileExceededLimitError, self).__dict__
        data['size_limit'] = self._size_limit
        data['filename'] = self._filename
        return data


__all__ = (
    'DocumentLookupError',
    'InvalidLicense',
    'InvalidRole',
    'InvalidMetadata',
    'InvalidReference',
    'InvalidDocumentPointer',
    'MissingRequiredMetadata',
    'NotAllowed',
    'PublicationException',
    'ResourceFileExceededLimitError',
    'UserFetchError',
)
