# -*- coding: utf-8 -*-


def up(cursor):
    cursor.execute("""\
        CREATE TABLE pending_resource_associations (
          "document_id" INTEGER NOT NULL,
          "resource_id" INTEGER NOT NULL,
          PRIMARY KEY ("document_id", "resource_id"),
          FOREIGN KEY ("document_id") REFERENCES pending_documents ("id"),
          FOREIGN KEY ("resource_id") REFERENCES pending_resources ("id")
        )""")


def down(cursor):
    cursor.execute('DROP TABLE pending_resource_associations')
