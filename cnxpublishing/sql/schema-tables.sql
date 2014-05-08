-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE TABLE publications (
  "id" SERIAL PRIMARY KEY,
  "publisher" TEXT NOT NULL,
  "publication_message" TEXT NOT NULL,
  "epub" BYTEA NOT NULL,
  -- State information, included an optional message.
  "state" publication_states DEFAULT 'Processing'
);


CREATE TABLE pending_documents (
  "id" SERIAL PRIMARY KEY,
  "publication_id" INTEGER NOT NULL,
  -- Identifiers
  "uuid" UUID NOT NULL,
  "major_version" INTEGER,
  "minor_version" INTEGER DEFAULT NULL,
  "type" document_types NOT NULL,
  -- Document content
  metadata JSON,
  content BYTEA,
  -- Pending information
  "license_accepted" BOOLEAN DEFAULT FALSE,
  "roles_accepted" BOOLEAN DEFAULT FALSE,
  FOREIGN KEY ("publication_id") REFERENCES publications ("id")
);


CREATE TABLE pending_resources (
  "id" SERIAL PRIMARY KEY,
  "data" BYTEA,
  -- TODO ``CONSTRAINT unique_file_hash UNIQUE``, to be put in archive as well.
  "hash" TEXT UNIQUE,  -- Trigger updated.
  "media_type" TEXT NOT NULL
);


CREATE TABLE publications_license_acceptance (
  "uuid" UUID,  -- Document uuid, no constraint
  "user_id" TEXT,  -- User identifier, no constraint
  -- Acceptance can be three states null, true or false.
  -- The initial null value indicates action is required.
  -- A value of true or false indicates the user (at ``user_id``)
  -- has responded to the license acceptance request.
  "acceptance" BOOLEAN DEFAULT NULL,
  PRIMARY KEY ("uuid", "user_id")
);


CREATE TABLE publications_role_acceptance (
  "pending_document_id" INTEGER,
  "user_id" TEXT,  -- User identifier, no constraint
  -- Acceptance can be three states null, true or false.
  -- The initial null value indicates action is required.
  -- A value of true or false indicates the user (at ``user_id``)
  -- has responded to the license acceptance request.
  "acceptance" BOOLEAN DEFAULT NULL,
  FOREIGN KEY ("pending_document_id") REFERENCES pending_documents ("id"),
  PRIMARY KEY ("pending_document_id", "user_id")
);
