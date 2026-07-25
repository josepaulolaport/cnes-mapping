-- ============================================================================
-- MCP TEST SCHEMA - PostgreSQL
-- Ported from create_sales_app_schema_sqlite.sql (source of truth)
-- Schema: mcp_test | Tables only (views in create_mcp_test_views.sql)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS mcp_test;
SET search_path TO mcp_test, public;

-- Drop tables (reverse dependency order)
DROP TABLE IF EXISTS professional_workload CASCADE;
DROP TABLE IF EXISTS facility_representatives CASCADE;
DROP TABLE IF EXISTS facility_physical_installations CASCADE;
DROP TABLE IF EXISTS facility_agreements CASCADE;
DROP TABLE IF EXISTS facility_equipment CASCADE;
DROP TABLE IF EXISTS facility_services CASCADE;
DROP TABLE IF EXISTS facility_professionals CASCADE;
DROP TABLE IF EXISTS occupations CASCADE;
DROP TABLE IF EXISTS service_classifications CASCADE;
DROP TABLE IF EXISTS professionals CASCADE;
DROP TABLE IF EXISTS facilities CASCADE;
DROP TABLE IF EXISTS maintainers CASCADE;
DROP TABLE IF EXISTS physical_installations CASCADE;
DROP TABLE IF EXISTS physical_installation_types CASCADE;
DROP TABLE IF EXISTS installation_subtypes CASCADE;
DROP TABLE IF EXISTS care_types CASCADE;
DROP TABLE IF EXISTS agreement_types CASCADE;
DROP TABLE IF EXISTS municipalities CASCADE;
DROP TABLE IF EXISTS states CASCADE;
DROP TABLE IF EXISTS facility_types CASCADE;
DROP TABLE IF EXISTS deactivation_reasons CASCADE;
DROP TABLE IF EXISTS service_specialties CASCADE;
DROP TABLE IF EXISTS equipment_catalog CASCADE;
DROP TABLE IF EXISTS professional_councils CASCADE;
DROP TABLE IF EXISTS equipment_categories CASCADE;

-- ============================================================================
-- REFERENCE TABLES
-- ============================================================================

CREATE TABLE states (
    state_code TEXT PRIMARY KEY,
    state_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE states IS 'Brazilian states (UF). Reference table, ~27 rows.';
COMMENT ON COLUMN states.state_code IS 'State abbreviation (SP, RJ, MG, etc.)';
COMMENT ON COLUMN states.state_name IS 'Full state name';

CREATE TABLE municipalities (
    municipality_id TEXT PRIMARY KEY,
    municipality_name TEXT NOT NULL,
    state_code TEXT NOT NULL,
    registration_type TEXT,
    pact_type TEXT,
    data_submission_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (state_code) REFERENCES states(state_code)
);

COMMENT ON TABLE municipalities IS 'Brazilian municipalities (cities). ~5,600 rows. Join via municipality_id.';
COMMENT ON COLUMN municipalities.municipality_id IS 'IBGE municipality code';
COMMENT ON COLUMN municipalities.state_code IS 'FK to states.state_code';

CREATE INDEX idx_municipalities_state ON municipalities(state_code);

CREATE TABLE facility_types (
    facility_type_code TEXT PRIMARY KEY,
    facility_type_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE facility_types IS 'Types of health facilities (hospital, clinic, pharmacy, etc.). Lookup for facilities.facility_type_code.';

CREATE TABLE deactivation_reasons (
    deactivation_code TEXT PRIMARY KEY,
    deactivation_reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE deactivation_reasons IS 'Reasons why facilities are deactivated. Join facilities.deactivation_reason_code when NOT NULL.';

CREATE TABLE service_specialties (
    service_code TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE service_specialties IS 'Medical service specialties. Lookup for facility_services.service_code.';

CREATE TABLE equipment_catalog (
    equipment_code TEXT NOT NULL,
    equipment_type_code TEXT NOT NULL,
    equipment_name TEXT NOT NULL,
    renem_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (equipment_code, equipment_type_code)
);

COMMENT ON TABLE equipment_catalog IS 'Catalog of medical equipment types. Composite PK (equipment_code, equipment_type_code).';

CREATE INDEX idx_equipment_code ON equipment_catalog(equipment_code);

CREATE TABLE professional_councils (
    council_code TEXT PRIMARY KEY,
    council_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE professional_councils IS 'Professional councils (CRM=Medical, CRO=Dental, CRF=Pharmacy, etc.).';

CREATE TABLE occupations (
    occupation_code TEXT PRIMARY KEY,
    occupation_name TEXT NOT NULL,
    professional_classification TEXT,
    is_health_occupation TEXT,
    is_regulated TEXT,
    reference_year TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE occupations IS 'CBO occupation/specialty lookup. From tbAtividadeProfissional.';
COMMENT ON COLUMN occupations.occupation_code IS 'Brazilian CBO code (CO_CBO)';
COMMENT ON COLUMN occupations.occupation_name IS 'Occupation label (DS_ATIVIDADE_PROFISSIONAL)';
COMMENT ON COLUMN occupations.is_health_occupation IS 'S=health occupation, N=non-health (TP_CBO_SAUDE)';

CREATE INDEX idx_occupations_name_trgm ON occupations USING gin (occupation_name gin_trgm_ops);

CREATE TABLE equipment_categories (
    category_code TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE equipment_categories IS 'Equipment type categories. Lookup for facility_equipment.equipment_category_code.';

CREATE TABLE service_classifications (
    classification_id TEXT NOT NULL,
    service_specialty_code TEXT NOT NULL,
    classification_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (classification_id, service_specialty_code),
    FOREIGN KEY (service_specialty_code) REFERENCES service_specialties(service_code)
);

COMMENT ON TABLE service_classifications IS 'Detailed service classification hierarchy linked to service_specialties.';

CREATE TABLE agreement_types (
    agreement_code TEXT PRIMARY KEY,
    agreement_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE agreement_types IS 'Payment/agreement types (SUS, particular, health plan). From tbConvenio.';

CREATE TABLE care_types (
    care_type_code TEXT PRIMARY KEY,
    care_type_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE care_types IS 'Care delivery modes (ambulatorial, internacao). From tbAtendimentoPrestado.';

CREATE TABLE installation_subtypes (
    installation_subtype_code TEXT PRIMARY KEY,
    installation_subtype_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE physical_installation_types (
    installation_type_code TEXT PRIMARY KEY,
    installation_type_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE physical_installations (
    installation_code TEXT PRIMARY KEY,
    installation_subtype_code TEXT,
    installation_name TEXT NOT NULL,
    installation_type_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (installation_subtype_code) REFERENCES installation_subtypes(installation_subtype_code),
    FOREIGN KEY (installation_type_code) REFERENCES physical_installation_types(installation_type_code)
);

COMMENT ON TABLE physical_installations IS 'Physical installation catalog. From tbInstalFisicaParaAssist.';

CREATE TABLE maintainers (
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

-- ============================================================================
-- MAIN TABLES
-- ============================================================================

CREATE TABLE facilities (
    facility_id TEXT PRIMARY KEY,
    cnes_code TEXT UNIQUE,
    legal_name TEXT,
    trade_name TEXT,
    street_address TEXT,
    street_number TEXT,
    address_complement TEXT,
    neighborhood TEXT,
    postal_code TEXT,
    municipality_id TEXT,
    health_region_id TEXT,
    phone_number TEXT,
    fax_number TEXT,
    email TEXT,
    website_url TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    tax_id_cnpj TEXT,
    tax_id_cpf TEXT,
    owner_tax_id TEXT,
    legal_entity_type_code TEXT,
    entity_type TEXT,
    facility_type_code TEXT,
    primary_activity_code TEXT,
    unit_type_code TEXT,
    unit_type_name TEXT,
    unit_subtype_name TEXT,
    operating_hours_code TEXT,
    deactivation_reason_code TEXT,
    is_24_7 INTEGER DEFAULT 0,
    is_philanthropic INTEGER DEFAULT 0,
    has_internet INTEGER DEFAULT 0,
    has_formal_contract INTEGER DEFAULT 0,
    license_issue_date TEXT,
    sanitary_license_expiry TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (municipality_id) REFERENCES municipalities(municipality_id),
    FOREIGN KEY (owner_tax_id) REFERENCES maintainers(tax_id),
    FOREIGN KEY (facility_type_code) REFERENCES facility_types(facility_type_code),
    FOREIGN KEY (deactivation_reason_code) REFERENCES deactivation_reasons(deactivation_code)
);

COMMENT ON TABLE facilities IS 'Health facilities/establishments - PRIMARY TARGET for sales. ~623k rows.';
COMMENT ON COLUMN facilities.facility_id IS 'Unique facility identifier (CNES CO_UNIDADE)';
COMMENT ON COLUMN facilities.deactivation_reason_code IS 'NULL = ACTIVE facility, NOT NULL = deactivated (~24.5% deactivated)';
COMMENT ON COLUMN facilities.trade_name IS 'Business/trade name (most commonly used for display)';
COMMENT ON COLUMN facilities.municipality_id IS 'FK to municipalities.municipality_id (IBGE code)';
COMMENT ON COLUMN facilities.is_24_7 IS '1 = open 24 hours, 7 days a week';
COMMENT ON COLUMN facilities.unit_type_name IS 'Denormalized from tbTipoUnidade via unit_type_code';
COMMENT ON COLUMN facilities.unit_subtype_name IS 'Denormalized from rlEstabSubTipo + tbSubTipo; NULL if no subtype';

CREATE INDEX idx_facilities_municipality ON facilities(municipality_id);
CREATE INDEX idx_facilities_type ON facilities(facility_type_code);
CREATE INDEX idx_facilities_active ON facilities(deactivation_reason_code) WHERE deactivation_reason_code IS NULL;
CREATE INDEX idx_facilities_trade_name ON facilities(trade_name);
CREATE INDEX idx_facilities_postal_code ON facilities(postal_code);

CREATE TABLE professionals (
    professional_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    social_name TEXT,
    tax_id TEXT,
    health_card_number TEXT,
    nationality_code TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE professionals IS 'Healthcare professionals (doctors, nurses, etc.). ~7.5M rows.';
COMMENT ON COLUMN professionals.professional_id IS 'Unique professional identifier (CO_PROFISSIONAL_SUS)';
COMMENT ON COLUMN professionals.social_name IS 'Preferred/social name if different from legal name';
COMMENT ON COLUMN professionals.tax_id IS 'CPF (partially masked for privacy)';

CREATE INDEX idx_professionals_full_name ON professionals(full_name);
CREATE INDEX idx_professionals_tax_id ON professionals(tax_id);

CREATE TABLE facility_professionals (
    facility_id TEXT NOT NULL,
    professional_id TEXT NOT NULL,
    occupation_code TEXT NOT NULL,
    municipality_id TEXT,
    service_area_id TEXT,
    team_sequence_number INTEGER,
    service_type TEXT,
    employment_type_code TEXT,
    start_date TEXT,
    termination_date TEXT,
    micro_area_code TEXT,
    other_team_cnes TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, professional_id, occupation_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id),
    FOREIGN KEY (occupation_code) REFERENCES occupations(occupation_code)
);

COMMENT ON TABLE facility_professionals IS 'Links professionals to facilities - WHO WORKS WHERE. ~864k rows.';
COMMENT ON COLUMN facility_professionals.termination_date IS 'NULL = currently employed, NOT NULL = terminated';
COMMENT ON COLUMN facility_professionals.occupation_code IS 'CBO code indicating specialty/role (e.g. physician, nurse)';
COMMENT ON COLUMN facility_professionals.service_type IS 'S=SUS/public, N=private';

CREATE INDEX idx_facility_professionals_facility ON facility_professionals(facility_id);
CREATE INDEX idx_facility_professionals_professional ON facility_professionals(professional_id);
CREATE INDEX idx_facility_professionals_active ON facility_professionals(termination_date) WHERE termination_date IS NULL;

CREATE TABLE facility_services (
    facility_id TEXT NOT NULL,
    service_code TEXT NOT NULL,
    classification_code TEXT NOT NULL,
    characteristic_type TEXT NOT NULL,
    owner_tax_id TEXT NOT NULL,
    address_complement TEXT NOT NULL,
    ambulatory_capacity INTEGER,
    ambulatory_capacity_sus INTEGER,
    hospital_capacity INTEGER,
    hospital_capacity_sus INTEGER,
    is_active INTEGER,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, service_code, classification_code, characteristic_type, owner_tax_id, address_complement),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_services IS 'Services and specialties offered by facilities.';
COMMENT ON COLUMN facility_services.is_active IS '1 = service currently active at this facility';
COMMENT ON COLUMN facility_services.owner_tax_id IS 'CNPJ/CPF of service provider at this facility (CO_CNPJCPF)';
COMMENT ON COLUMN facility_services.address_complement IS 'Address complement distinguishing multiple service locations (CO_END_COMPL)';

CREATE INDEX idx_facility_services_facility ON facility_services(facility_id);
CREATE INDEX idx_facility_services_service ON facility_services(service_code);
CREATE INDEX idx_facility_services_active ON facility_services(is_active) WHERE is_active = 1;

CREATE TABLE facility_equipment (
    facility_id TEXT NOT NULL,
    equipment_code TEXT NOT NULL,
    equipment_category_code TEXT NOT NULL,
    quantity INTEGER,
    operational_status TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, equipment_code, equipment_category_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (equipment_category_code) REFERENCES equipment_categories(category_code)
);

COMMENT ON TABLE facility_equipment IS 'Equipment inventory at facilities.';
COMMENT ON COLUMN facility_equipment.operational_status IS 'E=In use, D=Inactive, M=Maintenance. Filter E for active equipment.';
COMMENT ON COLUMN facility_equipment.quantity IS 'Number of units; use quantity > 0 with operational_status = E';

CREATE INDEX idx_facility_equipment_facility ON facility_equipment(facility_id);
CREATE INDEX idx_facility_equipment_equipment ON facility_equipment(equipment_code);
CREATE INDEX idx_facility_equipment_category ON facility_equipment(equipment_category_code);

CREATE TABLE professional_workload (
    facility_id TEXT NOT NULL,
    professional_id TEXT NOT NULL,
    occupation_code TEXT NOT NULL,
    weekly_hours_ambulatory INTEGER,
    service_type TEXT NOT NULL,
    employment_type_code TEXT NOT NULL,
    professional_council_code TEXT,
    license_number TEXT,
    license_state TEXT,
    is_preceptor INTEGER,
    is_resident INTEGER,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, professional_id, occupation_code, employment_type_code, service_type),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id),
    FOREIGN KEY (occupation_code) REFERENCES occupations(occupation_code)
);

COMMENT ON TABLE professional_workload IS 'Working hours, credentials, and professional licenses.';
COMMENT ON COLUMN professional_workload.service_type IS 'S=SUS, N=non-SUS. Part of composite PK — same professional can have separate SUS and non-SUS workloads.';
COMMENT ON COLUMN professional_workload.professional_council_code IS 'CNES council code (generic 01-12 or regional CRM 60-83). Not FK-constrained — tbConselhoClasse only lists 12 generic types.';
COMMENT ON COLUMN professional_workload.is_preceptor IS '1 = teaches/supervises residents';
COMMENT ON COLUMN professional_workload.employment_type_code IS 'Part of composite PK with facility, professional, occupation, service_type';

CREATE INDEX idx_professional_workload_facility ON professional_workload(facility_id);
CREATE INDEX idx_professional_workload_professional ON professional_workload(professional_id);
CREATE INDEX idx_professional_workload_council ON professional_workload(professional_council_code);

CREATE TABLE facility_agreements (
    facility_id TEXT NOT NULL,
    care_type_code TEXT NOT NULL,
    agreement_code TEXT NOT NULL,
    updated_by_user TEXT,
    last_updated_date TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (facility_id, care_type_code, agreement_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (care_type_code) REFERENCES care_types(care_type_code),
    FOREIGN KEY (agreement_code) REFERENCES agreement_types(agreement_code)
);

COMMENT ON TABLE facility_agreements IS 'Payment/care agreements accepted by facility. From rlEstabAtendPrestConv.';

CREATE INDEX idx_facility_agreements_facility ON facility_agreements(facility_id);
CREATE INDEX idx_facility_agreements_agreement ON facility_agreements(agreement_code);

CREATE TABLE facility_physical_installations (
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
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (installation_code) REFERENCES physical_installations(installation_code)
);

COMMENT ON TABLE facility_physical_installations IS 'Physical installations at each facility. From rlEstabInstFisiAssist.';

CREATE INDEX idx_facility_physical_installations_facility ON facility_physical_installations(facility_id);
CREATE INDEX idx_facility_physical_installations_code ON facility_physical_installations(installation_code);

CREATE TABLE facility_representatives (
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
COMMENT ON COLUMN facility_representatives.tax_id IS 'CPF when provided; CNES often masks as literal CO_CPF (stored NULL).';
COMMENT ON COLUMN facility_representatives.role_title IS 'Role e.g. REPRESENTANTE LEGAL, PRESIDENTE, DIRETOR TECNICO.';

CREATE INDEX idx_facility_representatives_name ON facility_representatives(representative_name);
CREATE INDEX idx_facility_representatives_email ON facility_representatives(email) WHERE email IS NOT NULL AND email <> '';
