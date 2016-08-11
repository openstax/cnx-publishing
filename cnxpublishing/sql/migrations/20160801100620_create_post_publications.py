# -*- coding: utf-8 -*-


def up(cursor):
    cursor.execute("""\
CREATE TYPE post_publication_states AS ENUM (
  'Done/Success',
  'Failed/Error',
  'Processing'
);
CREATE TABLE post_publications (
  "module_ident" INTEGER NOT NULL,
  "state" post_publication_states NOT NULL,
  "state_message" TEXT,
  "timestamp" TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY ("module_ident") REFERENCES modules ("module_ident")
);""")


def down(cursor):
    cursor.execute('DROP TYPE IF EXISTS collation_states')
    cursor.execute('DROP TABLE IF EXISTS collation_states')
