-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE TABLE publications (
  "id" SERIAL PRIMARY KEY,
  "created" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  "publisher" TEXT NOT NULL,
  "publication_message" TEXT NOT NULL,
  "epub" BYTEA,
  -- Pre-publication, do not commit to *archive*.
  "is_pre_publication" BOOLEAN DEFAULT FALSE,
  -- State information, included an optional message.
  "state" publication_states DEFAULT 'Processing',
  "state_messages" JSON
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
  FOREIGN KEY ("publication_id") REFERENCES publications ("id"),
  FOREIGN KEY ("uuid") REFERENCES document_controls ("uuid")
);


CREATE TABLE pending_resources (
  "id" SERIAL PRIMARY KEY,
  "data" BYTEA,
  -- TODO ``CONSTRAINT unique_file_hash UNIQUE``, to be put in archive as well.
  "hash" TEXT UNIQUE,  -- SHA1 hash
  "md5" TEXT,  -- Legacy MD5 hash
  "media_type" TEXT NOT NULL,
  "exists_in_archive" BOOLEAN DEFAULT 'f',
  "filename" TEXT
);


CREATE TABLE pending_resource_associations (
  "document_id" INTEGER NOT NULL,
  "resource_id" INTEGER NOT NULL,
  PRIMARY KEY ("document_id", "resource_id"),
  FOREIGN KEY ("document_id") REFERENCES pending_documents ("id"),
  FOREIGN KEY ("resource_id") REFERENCES pending_resources ("id")
);


CREATE TABLE license_acceptances (
  "uuid" UUID NOT NULL,  -- Document uuid, no constraint
  "user_id" TEXT NOT NULL,  -- User identifier, no constraint
  -- Acceptance can be three states null, true or false.
  -- The initial null value indicates action is required.
  -- A value of true or false indicates the user (at ``user_id``)
  -- has responded to the license acceptance request.
  "accepted" BOOLEAN DEFAULT NULL,
  -- When publishing sends a notification message to the user
  -- via the OpenStax Accounts service, the datetime that message
  -- was sent is recorded here. This value can be null while ``accepted``
  -- is true due to various other workflow circumstances.
  "notified" TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY ("uuid", "user_id"),
  FOREIGN KEY ("uuid") REFERENCES document_controls ("uuid")
);


CREATE TABLE role_acceptances (
  "uuid" UUID NOT NULL,
  "user_id" TEXT NOT NULL,  -- User identifier, no constraint
  "role_type" role_types NOT NULL,
  -- Acceptance can be three states null, true or false.
  -- The initial null value indicates action is required.
  -- A value of true or false indicates the user (at ``user_id``)
  -- has responded to the license acceptance request.
  "accepted" BOOLEAN DEFAULT NULL,
  -- When publishing sends a notification message to the user
  -- via the OpenStax Accounts service, the datetime that message
  -- was sent is recorded here. This value can be null while ``accepted``
  -- is true due to various other workflow circumstances.
  "notified" TIMESTAMP WITH TIME ZONE,
  PRIMARY KEY ("uuid", "user_id", "role_type"),
  FOREIGN KEY ("uuid") REFERENCES document_controls ("uuid")
);


CREATE TABLE api_keys (
  "id" SERIAL PRIMARY KEY,
  -- Any text that the service will use as an api key.
  "key" TEXT NOT NULL,
  -- This is a human readable name of the person, organization or service
  -- that we are giving an api key.
  "name" TEXT NOT NULL,
  -- A list of groups that this api key is a member of.
  -- For example, g:publishers or g:trusted-publishers.
  -- See the documenation about available groups.
  "groups" TEXT[]
);


CREATE TABLE post_publications (
  "module_ident" INTEGER NOT NULL,
  "state" post_publication_states NOT NULL,
  "state_message" TEXT,
  "timestamp" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY ("module_ident") REFERENCES modules ("module_ident")
);
