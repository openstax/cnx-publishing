# -*- coding: utf-8 -*-


def up(cursor):
    cursor.execute("""\
        ALTER TABLE pending_resources
            ADD COLUMN filename TEXT""")


def down(cursor):
    cursor.execute("""\
        ALTER TABLE pending_resources
            DROP COLUMN filename""")
