-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE OR REPLACE FUNCTION update_pending_resource ()
RETURNS "trigger"
AS $$
  import hashlib
  # Lagacy compat.
  md5 = TD['new']['md5'] = hashlib.new('md5', TD['new']['data']).hexdigest()

  plan = plpy.prepare("""
      SELECT null as fileid, hash from pending_resources WHERE hash = $1
      UNION ALL
      SELECT fileid, md5 as hash from files WHERE md5 = $2""",
                      ['text', 'text'])
  hash = TD['new']['hash']
  existing_resource = plpy.execute(plan, [hash, md5], 1)
  # If the resource exists in the archive, null the data and set
  # the flag. This helps to keep the database small'ish.
  if existing_resource:
      if existing_resource[0]['fileid'] is not None:
          TD['new']['exists_in_archive'] = True
      else:
          # exists in pending_resources, don't insert again
          return 'SKIP'
  return 'MODIFY'
$$
LANGUAGE plpythonu;


CREATE TRIGGER update_pending_resources_hash
BEFORE INSERT ON "pending_resources"
FOR EACH ROW EXECUTE PROCEDURE update_pending_resource();
