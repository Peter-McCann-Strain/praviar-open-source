DO $$
DECLARE
  observed_head text;
  aspirin_id uuid;
  aspirin_name text;
  legacy_name text;
  association_count integer;
  biologic_count integer;
  forced_rls_count integer;
BEGIN
  SELECT version_num INTO observed_head FROM alembic_version;

  SELECT id, name
  INTO aspirin_id, aspirin_name
  FROM compounds
  WHERE inchi_key = 'BSYNRYMUTXBXSQ-UHFFFAOYSA-N';

  SELECT name
  INTO legacy_name
  FROM compounds
  WHERE id = '52222222-2222-4222-8222-222222222222';

  SELECT count(*)
  INTO association_count
  FROM organization_compounds
  WHERE org_id = '51111111-1111-4111-8111-111111111111';

  SELECT count(*)
  INTO biologic_count
  FROM analyses
  WHERE id = '55555555-5555-4555-8555-555555555555'
    AND status = 'completed';

  SELECT count(*)
  INTO forced_rls_count
  FROM pg_class
  WHERE relname IN ('organization_compounds', 'weekly_digest_deliveries')
    AND relrowsecurity
    AND relforcerowsecurity;

  IF observed_head <> 'd9e0f1a2b3c4'
     OR aspirin_id <> md5(
       'praviar-compound:BSYNRYMUTXBXSQ-UHFFFAOYSA-N'
     )::uuid
     OR aspirin_name <> ''
     OR legacy_name <> ''
     OR association_count <> 2
     OR biologic_count <> 1
     OR forced_rls_count <> 2 THEN
    RAISE EXCEPTION
      'seeded upgrade canary failed: head %, aspirin %, aspirin name %, legacy name %, associations %, biologic %, forced RLS %',
      observed_head,
      aspirin_id,
      aspirin_name,
      legacy_name,
      association_count,
      biologic_count,
      forced_rls_count;
  END IF;
END
$$;
