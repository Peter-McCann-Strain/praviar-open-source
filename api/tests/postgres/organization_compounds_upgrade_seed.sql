INSERT INTO organizations (id, clerk_org_id, name, slug)
VALUES (
  '51111111-1111-4111-8111-111111111111',
  'org_compound_upgrade_canary',
  'Compound Upgrade Canary',
  'compound-upgrade-canary'
);

INSERT INTO users (
  id,
  clerk_user_id,
  org_id,
  email,
  full_name,
  role
)
VALUES (
  '5aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  'user_compound_upgrade_canary',
  '51111111-1111-4111-8111-111111111111',
  'compound-upgrade@canary.test',
  'Compound Upgrade Canary',
  'attorney'
);

INSERT INTO compounds (
  id,
  canonical_smiles,
  inchi_key,
  name,
  molecular_formula,
  functional_groups,
  analysis_count
)
VALUES (
  '52222222-2222-4222-8222-222222222222',
  'CCN',
  'QUSNBJAOOMFDIB-UHFFFAOYSA-N',
  'Legacy Tenant Secret',
  'C2H7N',
  '[]'::jsonb,
  1
);

INSERT INTO analyses (
  id,
  org_id,
  compound_input,
  compound_name,
  compound_smiles,
  status,
  report_data,
  completed_at,
  initiated_by
)
VALUES
  (
    '53333333-3333-4333-8333-333333333333',
    '51111111-1111-4111-8111-111111111111',
    'new-valid-inchi',
    'Canary Aspirin',
    'CC(=O)OC1=CC=CC=C1C(=O)O',
    'completed',
    '{
      "compound": {
        "compound_type": "small_molecule",
        "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
        "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "name": "Canary Aspirin",
        "molecular_formula": "C9H8O4"
      }
    }'::jsonb,
    '2026-07-04 09:00:00+00',
    '5aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  ),
  (
    '54444444-4444-4444-8444-444444444444',
    '51111111-1111-4111-8111-111111111111',
    'unique-smiles-fallback',
    'Canary Ethylamine',
    'CCN',
    'completed',
    '{
      "compound": {
        "compound_type": "small_molecule",
        "inchi_key": "",
        "canonical_smiles": "CCN",
        "name": "Canary Ethylamine",
        "molecular_formula": "C2H7N"
      }
    }'::jsonb,
    '2026-07-05 09:00:00+00',
    '5aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  ),
  (
    '55555555-5555-4555-8555-555555555555',
    '51111111-1111-4111-8111-111111111111',
    'blank-biologic',
    'Canary Biologic',
    '',
    'completed',
    '{
      "compound": {
        "compound_type": "biologic",
        "inchi_key": "",
        "canonical_smiles": "",
        "name": "Canary Biologic"
      }
    }'::jsonb,
    '2026-07-06 09:00:00+00',
    '5aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  );
