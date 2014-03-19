-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE TYPE publication_states AS ENUM (
  'Done/Success',
  'Processing',
  'Waiting for acceptance',
  'Failed/Error'
);


CREATE TYPE document_types AS ENUM (
  'Document',
  'Binder'
);
