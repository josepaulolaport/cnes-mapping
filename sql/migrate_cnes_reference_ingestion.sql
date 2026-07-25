-- ============================================================================
-- Add CNES reference tables + facility enrichments (live mcp_test migration)
-- Safe to re-run: uses IF NOT EXISTS / conditional drops where possible
-- ============================================================================

SET search_path TO mcp_test, public;

-- ---------------------------------------------------------------------------
-- Reference lookups
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS agreement_types (
    agreement_code TEXT PRIMARY KEY,
    agreement_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agreement_types IS 'Payment/agreement types (SUS, particular, health plan). From tbConvenio.';

CREATE TABLE IF NOT EXISTS care_types (
    care_type_code TEXT PRIMARY KEY,
    care_type_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE care_types IS 'Care delivery modes (ambulatorial, internacao). From tbAtendimentoPrestado.';

CREATE TABLE IF NOT EXISTS installation_subtypes (
    installation_subtype_code TEXT PRIMARY KEY,
    installation_subtype_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS physical_installation_types (
    installation_type_code TEXT PRIMARY KEY,
    installation_type_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS physical_installations (
    installation_code TEXT PRIMARY KEY,
    installation_subtype_code TEXT,
    installation_name TEXT NOT NULL,
    installation_type_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE physical_installations IS 'Physical installation catalog (consulting rooms, clinics). From tbInstalFisicaParaAssist.';

CREATE TABLE IF NOT EXISTS maintainers (
    tax_id TEXT PRIMARY KEY,
    legal_name TEXT,
    bank_code TEXT,
    branch_number TEXT,
    account_number TEXT,
    street_address TEXT,
    street_number TEXT,
    address_complement TEXT,
    neighborhood TEXT,
    postal_code TEXT,
    municipality_id TEXT,
    health_region_id TEXT,
    phone_number TEXT,
    form_filled_date TEXT,
    fms_fes_status TEXT,
    fms_fes_tax_id TEXT,
    legal_entity_type_code TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    manager_code TEXT,
    manager_municipality_id TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE maintainers IS 'Facility maintainer organizations (mantenedora). Full record from tbMantenedora.';
COMMENT ON COLUMN maintainers.tax_id IS 'CNPJ (NU_CNPJ_MANTENEDORA)';

-- ---------------------------------------------------------------------------
-- Relationship tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS facility_agreements (
    facility_id TEXT NOT NULL,
    care_type_code TEXT NOT NULL,
    agreement_code TEXT NOT NULL,
    updated_by_user TEXT,
    last_updated_date TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, care_type_code, agreement_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_agreements IS 'Payment/care agreements accepted by facility. From rlEstabAtendPrestConv.';

CREATE INDEX IF NOT EXISTS idx_facility_agreements_facility ON facility_agreements(facility_id);
CREATE INDEX IF NOT EXISTS idx_facility_agreements_agreement ON facility_agreements(agreement_code);

CREATE TABLE IF NOT EXISTS facility_physical_installations (
    facility_id TEXT NOT NULL,
    installation_code TEXT NOT NULL,
    quantity INTEGER,
    bed_count INTEGER,
    last_updated_date TEXT,
    updated_by_user TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, installation_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_physical_installations IS 'Physical installations at each facility. From rlEstabInstFisiAssist.';

CREATE INDEX IF NOT EXISTS idx_facility_physical_installations_facility ON facility_physical_installations(facility_id);
CREATE INDEX IF NOT EXISTS idx_facility_physical_installations_code ON facility_physical_installations(installation_code);

CREATE TABLE IF NOT EXISTS facility_representatives (
    facility_id TEXT PRIMARY KEY,
    representative_name TEXT NOT NULL,
    role_title TEXT,
    email TEXT,
    tax_id TEXT,
    updated_by_user TEXT,
    last_updated_date TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_representatives IS 'Official legal representatives at facilities. From rlEstabRepresentante.';

CREATE INDEX IF NOT EXISTS idx_facility_representatives_name ON facility_representatives(representative_name);
CREATE INDEX IF NOT EXISTS idx_facility_representatives_email ON facility_representatives(email)
    WHERE email IS NOT NULL AND email <> '';

-- ---------------------------------------------------------------------------
-- Enrich facilities (unit type/subtype names)
-- ---------------------------------------------------------------------------

ALTER TABLE facilities ADD COLUMN IF NOT EXISTS unit_type_name TEXT;
ALTER TABLE facilities ADD COLUMN IF NOT EXISTS unit_subtype_name TEXT;

COMMENT ON COLUMN facilities.unit_type_name IS 'Denormalized from tbTipoUnidade via unit_type_code';
COMMENT ON COLUMN facilities.unit_subtype_name IS 'Denormalized from rlEstabSubTipo + tbSubTipo; NULL if no subtype registered';

-- ---------------------------------------------------------------------------
-- Replace facility_owners with maintainers FK
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'mcp_test' AND table_name = 'facility_owners'
    ) THEN
        ALTER TABLE facilities DROP CONSTRAINT IF EXISTS facilities_owner_tax_id_fkey;
        DROP TABLE facility_owners CASCADE;
    END IF;
END $$;

-- Null owner_tax_id values not present in maintainers (applied after maintainers load)
-- ALTER TABLE facilities ADD CONSTRAINT facilities_owner_tax_id_fkey ...  (in apply script)
