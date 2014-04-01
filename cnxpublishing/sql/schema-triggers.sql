-- ###
-- Copyright (c) 2013, Rice University
-- This software is subject to the provisions of the GNU Affero General
-- Public License version 3 (AGPLv3).
-- See LICENCE.txt for details.
-- ###


CREATE OR REPLACE FUNCTION update_pending_hash ()
RETURNS "trigger"
AS $$
BEGIN
  NEW.hash = md5(NEW.data);
  IF EXISTS (SELECT hash FROM pending_resources WHERE hash = NEW.hash) THEN
    RETURN NULL;
  ELSE
    RETURN NEW;
  END IF;
END;
$$
LANGUAGE plpgsql;


CREATE TRIGGER update_pending_resources_hash
BEFORE INSERT or update ON "pending_resources"
FOR EACH ROW EXECUTE PROCEDURE update_pending_hash();
