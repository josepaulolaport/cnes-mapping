-- Fix professional_workload PK and FK issues discovered during CSV import.
-- Root causes:
--   1. PK missing service_type (TP_SUS_NAO_SUS) — 11,124 duplicate rows without it
--   2. FK to professional_councils invalid — workload uses regional CRM codes (60-83)
--      not present in tbConselhoClasse (only 12 generic council types)

SET search_path TO mcp_test, public;

DELETE FROM professional_workload;

ALTER TABLE professional_workload
    DROP CONSTRAINT IF EXISTS professional_workload_professional_council_code_fkey;

ALTER TABLE professional_workload
    DROP CONSTRAINT IF EXISTS professional_workload_pkey;

ALTER TABLE professional_workload
    ALTER COLUMN service_type SET NOT NULL;

ALTER TABLE professional_workload
    ADD PRIMARY KEY (facility_id, professional_id, occupation_code, employment_type_code, service_type);

COMMENT ON COLUMN professional_workload.service_type IS 'S=SUS, N=non-SUS. Part of composite PK — same professional can have separate SUS and non-SUS workloads.';
COMMENT ON COLUMN professional_workload.professional_council_code IS 'CNES council code (generic 01-12 or regional CRM 60-83). Not FK-constrained — tbConselhoClasse only lists 12 generic types.';
