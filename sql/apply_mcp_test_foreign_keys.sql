-- ============================================================================
-- Apply foreign keys for CNES reference ingestion + service FKs
-- Run AFTER migrate_cnes_reference_ingestion.sql and data import
-- ============================================================================

SET search_path TO mcp_test, public;

-- ---------------------------------------------------------------------------
-- facility_professionals → professionals
-- ---------------------------------------------------------------------------
DELETE FROM facility_professionals fp
WHERE NOT EXISTS (
    SELECT 1 FROM professionals p WHERE p.professional_id = fp.professional_id
);

DELETE FROM professional_workload pw
WHERE NOT EXISTS (
    SELECT 1 FROM professionals p WHERE p.professional_id = pw.professional_id
);

-- ---------------------------------------------------------------------------
-- maintainers: null orphan owner_tax_id on facilities before FK
-- ---------------------------------------------------------------------------
UPDATE facilities f
SET owner_tax_id = NULL
WHERE owner_tax_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM maintainers m WHERE m.tax_id = f.owner_tax_id);

-- ---------------------------------------------------------------------------
-- facility_services: drop orphan service / classification references
-- ---------------------------------------------------------------------------
DELETE FROM facility_services fs
WHERE NOT EXISTS (
    SELECT 1 FROM service_specialties ss WHERE ss.service_code = fs.service_code
);

DELETE FROM facility_services fs
WHERE NOT EXISTS (
    SELECT 1 FROM service_classifications sc
    WHERE sc.classification_id = fs.classification_code
      AND sc.service_specialty_code = fs.service_code
);

-- ---------------------------------------------------------------------------
-- facility_agreements / facility_physical_installations orphans
-- ---------------------------------------------------------------------------
DELETE FROM facility_agreements fa
WHERE NOT EXISTS (SELECT 1 FROM facilities f WHERE f.facility_id = fa.facility_id)
   OR NOT EXISTS (SELECT 1 FROM care_types c WHERE c.care_type_code = fa.care_type_code)
   OR NOT EXISTS (SELECT 1 FROM agreement_types a WHERE a.agreement_code = fa.agreement_code);

DELETE FROM facility_physical_installations fpi
WHERE NOT EXISTS (SELECT 1 FROM facilities f WHERE f.facility_id = fpi.facility_id)
   OR NOT EXISTS (SELECT 1 FROM physical_installations pi WHERE pi.installation_code = fpi.installation_code);

-- ---------------------------------------------------------------------------
-- physical_installations orphan FK cleanup
-- ---------------------------------------------------------------------------
UPDATE physical_installations
SET installation_subtype_code = NULL
WHERE installation_subtype_code IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM installation_subtypes s WHERE s.installation_subtype_code = physical_installations.installation_subtype_code
  );

UPDATE physical_installations
SET installation_type_code = NULL
WHERE installation_type_code IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM physical_installation_types t WHERE t.installation_type_code = physical_installations.installation_type_code
  );

-- ---------------------------------------------------------------------------
-- occupations: stub missing CBO codes referenced in employment data
-- ---------------------------------------------------------------------------
INSERT INTO occupations (occupation_code, occupation_name, is_health_occupation)
SELECT DISTINCT fp.occupation_code,
       'CBO ' || fp.occupation_code || ' (not in tbAtividadeProfissional)',
       'S'
FROM facility_professionals fp
WHERE NOT EXISTS (SELECT 1 FROM occupations o WHERE o.occupation_code = fp.occupation_code)
ON CONFLICT (occupation_code) DO NOTHING;

INSERT INTO occupations (occupation_code, occupation_name, is_health_occupation)
SELECT DISTINCT pw.occupation_code,
       'CBO ' || pw.occupation_code || ' (not in tbAtividadeProfissional)',
       'S'
FROM professional_workload pw
WHERE NOT EXISTS (SELECT 1 FROM occupations o WHERE o.occupation_code = pw.occupation_code)
ON CONFLICT (occupation_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Add constraints
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_professionals_professional_id_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_professionals
            ADD CONSTRAINT facility_professionals_professional_id_fkey
            FOREIGN KEY (professional_id) REFERENCES professionals(professional_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'professional_workload_professional_id_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE professional_workload
            ADD CONSTRAINT professional_workload_professional_id_fkey
            FOREIGN KEY (professional_id) REFERENCES professionals(professional_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facilities_owner_tax_id_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facilities
            ADD CONSTRAINT facilities_owner_tax_id_fkey
            FOREIGN KEY (owner_tax_id) REFERENCES maintainers(tax_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_services_service_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_services
            ADD CONSTRAINT facility_services_service_code_fkey
            FOREIGN KEY (service_code) REFERENCES service_specialties(service_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_services_classification_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_services
            ADD CONSTRAINT facility_services_classification_fkey
            FOREIGN KEY (classification_code, service_code)
            REFERENCES service_classifications(classification_id, service_specialty_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_agreements_care_type_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_agreements
            ADD CONSTRAINT facility_agreements_care_type_code_fkey
            FOREIGN KEY (care_type_code) REFERENCES care_types(care_type_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_agreements_agreement_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_agreements
            ADD CONSTRAINT facility_agreements_agreement_code_fkey
            FOREIGN KEY (agreement_code) REFERENCES agreement_types(agreement_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_physical_installations_installation_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_physical_installations
            ADD CONSTRAINT facility_physical_installations_installation_code_fkey
            FOREIGN KEY (installation_code) REFERENCES physical_installations(installation_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'physical_installations_installation_subtype_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE physical_installations
            ADD CONSTRAINT physical_installations_installation_subtype_code_fkey
            FOREIGN KEY (installation_subtype_code) REFERENCES installation_subtypes(installation_subtype_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'facility_professionals_occupation_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE facility_professionals
            ADD CONSTRAINT facility_professionals_occupation_code_fkey
            FOREIGN KEY (occupation_code) REFERENCES occupations(occupation_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'professional_workload_occupation_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE professional_workload
            ADD CONSTRAINT professional_workload_occupation_code_fkey
            FOREIGN KEY (occupation_code) REFERENCES occupations(occupation_code);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'physical_installations_installation_type_code_fkey'
          AND connamespace = 'mcp_test'::regnamespace
    ) THEN
        ALTER TABLE physical_installations
            ADD CONSTRAINT physical_installations_installation_type_code_fkey
            FOREIGN KEY (installation_type_code) REFERENCES physical_installation_types(installation_type_code);
    END IF;
END
$$;

SELECT conname, conrelid::regclass AS table_name
FROM pg_constraint
WHERE connamespace = 'mcp_test'::regnamespace AND contype = 'f'
ORDER BY conname;
