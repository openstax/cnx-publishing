-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE TYPE publication_states AS ENUM (
  'Done/Success',  -- Committed to the archive.
  'Publishing',  -- In the process of committing.
  'Processing',  -- Processing any part of the publication.
  'Waiting for acceptance',
  'Failed/Error',
  'Waiting for moderation',  -- Needs moderator approval
  'Rejected' -- A moderator rejected the publication
);


CREATE TYPE document_types AS ENUM (
  'Document',
  'Binder'
);


CREATE TYPE role_types AS ENUM (
  'Author',
  'Copyright Holder',
  'Editor',
  'Illustrator',
  'Publisher',
  'Translator'
);


CREATE TYPE post_publication_states AS ENUM (
  'Done/Success',
  'Failed/Error',
  'Processing'
)
