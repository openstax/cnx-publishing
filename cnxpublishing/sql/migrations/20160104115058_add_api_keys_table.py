# -*- coding: utf-8 -*-


def up(cursor):
    cursor.execute("""\
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
""")


def down(cursor):
    cursor.execute("DROP TABLE api_keys;")
