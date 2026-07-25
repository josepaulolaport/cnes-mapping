-- ============================================================================
-- SALES APP DATABASE SCHEMA
-- ============================================================================
-- Created from CNES Database Analysis
-- Source: Brazilian National Health Establishments Registry (CNES)
-- 
-- This schema transforms cryptic CNES naming into clear, modern names
-- for a sales application targeting medical equipment/pharma/supplies
--
-- Key improvements:
-- - English names instead of Portuguese abbreviations
-- - Self-documenting column names
-- - Consolidated reference tables
-- - Proper data types (BOOLEAN, DATE, DECIMAL)
-- - Optimized indexes for sales queries
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create CNES schema
CREATE SCHEMA IF NOT EXISTS cnes;

-- Set search path to CNES schema
SET search_path TO cnes, public;

-- Drop tables if they exist (in reverse dependency order)
DROP TABLE IF EXISTS cnes.professional_workload CASCADE;
DROP TABLE IF EXISTS cnes.facility_equipment CASCADE;
DROP TABLE IF EXISTS cnes.facility_services CASCADE;
DROP TABLE IF EXISTS cnes.facility_professionals CASCADE;
DROP TABLE IF EXISTS cnes.service_classifications CASCADE;
DROP TABLE IF EXISTS cnes.professionals CASCADE;
DROP TABLE IF EXISTS cnes.facilities CASCADE;
DROP TABLE IF EXISTS cnes.facility_owners CASCADE;
DROP TABLE IF EXISTS cnes.municipalities CASCADE;
DROP TABLE IF EXISTS cnes.states CASCADE;
DROP TABLE IF EXISTS cnes.facility_types CASCADE;
DROP TABLE IF EXISTS cnes.deactivation_reasons CASCADE;
DROP TABLE IF EXISTS cnes.service_specialties CASCADE;
DROP TABLE IF EXISTS cnes.equipment_catalog CASCADE;
DROP TABLE IF EXISTS cnes.professional_councils CASCADE;
DROP TABLE IF EXISTS cnes.equipment_categories CASCADE;

-- ============================================================================
-- REFERENCE/LOOKUP TABLES (No Dependencies)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- States (Brazilian States)
-- ----------------------------------------------------------------------------
CREATE TABLE states (
    state_code CHAR(2) PRIMARY KEY,
    state_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE states IS 'Brazilian states (UF)';
COMMENT ON COLUMN states.state_code IS 'State abbreviation (SP, RJ, MG, etc.)';
COMMENT ON COLUMN states.state_name IS 'Full state name';

-- ----------------------------------------------------------------------------
-- Municipalities (Brazilian Cities)
-- ----------------------------------------------------------------------------
CREATE TABLE municipalities (
    municipality_id VARCHAR(10) PRIMARY KEY,
    municipality_name VARCHAR(100) NOT NULL,
    state_code CHAR(2) NOT NULL,
    registration_type VARCHAR(10),
    pact_type VARCHAR(10),
    data_submission_type VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (state_code) REFERENCES states(state_code)
);

COMMENT ON TABLE municipalities IS 'Brazilian municipalities (cities)';
COMMENT ON COLUMN municipalities.municipality_id IS 'IBGE municipality code';
COMMENT ON COLUMN municipalities.state_code IS 'State where municipality is located';

CREATE INDEX idx_municipalities_state ON municipalities(state_code);

-- ----------------------------------------------------------------------------
-- Facility Types
-- ----------------------------------------------------------------------------
CREATE TABLE facility_types (
    facility_type_code VARCHAR(10) PRIMARY KEY,
    facility_type_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE facility_types IS 'Types of health facilities (hospital, clinic, etc.)';

-- ----------------------------------------------------------------------------
-- Deactivation Reasons
-- ----------------------------------------------------------------------------
CREATE TABLE deactivation_reasons (
    deactivation_code VARCHAR(10) PRIMARY KEY,
    deactivation_reason VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE deactivation_reasons IS 'Reasons why facilities are deactivated';

-- ----------------------------------------------------------------------------
-- Service Specialties
-- ----------------------------------------------------------------------------
CREATE TABLE service_specialties (
    service_code VARCHAR(10) PRIMARY KEY,
    service_name VARCHAR(500) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE service_specialties IS 'Medical service specialties available';

-- ----------------------------------------------------------------------------
-- Equipment Catalog
-- ----------------------------------------------------------------------------
CREATE TABLE equipment_catalog (
    equipment_id SERIAL PRIMARY KEY,
    equipment_code VARCHAR(10) NOT NULL,
    equipment_type_code VARCHAR(10),
    equipment_name VARCHAR(500) NOT NULL,
    renem_code VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE equipment_catalog IS 'Catalog of medical equipment types';
CREATE INDEX idx_equipment_catalog_code ON equipment_catalog(equipment_code);
CREATE INDEX idx_equipment_catalog_type ON equipment_catalog(equipment_type_code);

-- ----------------------------------------------------------------------------
-- Professional Councils
-- ----------------------------------------------------------------------------
CREATE TABLE professional_councils (
    council_code VARCHAR(10) PRIMARY KEY,
    council_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE professional_councils IS 'Professional councils (CRM, CRO, CRF, etc.)';

-- ----------------------------------------------------------------------------
-- Equipment Categories
-- ----------------------------------------------------------------------------
CREATE TABLE equipment_categories (
    category_code VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE equipment_categories IS 'Equipment type categories';

-- ----------------------------------------------------------------------------
-- Service Classifications
-- Detailed service classification hierarchy
-- ----------------------------------------------------------------------------
CREATE TABLE service_classifications (
    classification_id VARCHAR(10) NOT NULL,
    service_specialty_code VARCHAR(10) NOT NULL,
    classification_name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (classification_id, service_specialty_code)
);

COMMENT ON TABLE service_classifications IS 'Detailed service classification hierarchy';

CREATE INDEX idx_service_class_specialty ON service_classifications(service_specialty_code);

-- ============================================================================
-- MAIN ENTITY TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Facility Owners (Mantenedora)
-- Organizations that own/manage facilities
-- ----------------------------------------------------------------------------
CREATE TABLE facility_owners (
    tax_id VARCHAR(20) PRIMARY KEY,
    owner_name VARCHAR(200),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE facility_owners IS 'Organizations that own or manage health facilities';
COMMENT ON COLUMN facility_owners.tax_id IS 'CNPJ of the owner organization';

-- ----------------------------------------------------------------------------
-- Facilities (Health Establishments)
-- CRITICAL: This is the core table for sales targeting
-- ----------------------------------------------------------------------------
CREATE TABLE facilities (
    facility_id VARCHAR(50) PRIMARY KEY,
    cnes_code VARCHAR(20) UNIQUE,
    
    -- Names
    legal_name VARCHAR(200),
    trade_name VARCHAR(200),
    
    -- Address
    street_address VARCHAR(200),
    street_number VARCHAR(20),
    address_complement VARCHAR(100),
    neighborhood VARCHAR(100),
    postal_code VARCHAR(10),
    municipality_id VARCHAR(10),
    health_region_id VARCHAR(10),
    
    -- Contact
    phone_number VARCHAR(50),
    fax_number VARCHAR(50),
    email VARCHAR(100),
    website_url VARCHAR(200),
    
    -- Geolocation
    latitude DECIMAL(10,7),
    longitude DECIMAL(10,7),
    
    -- Tax & Legal
    tax_id_cnpj VARCHAR(20),
    tax_id_cpf VARCHAR(20),
    owner_tax_id VARCHAR(20),
    legal_entity_type_code VARCHAR(10),
    entity_type CHAR(1), -- P=Person, J=Company
    
    -- Classification
    facility_type_code VARCHAR(10),
    primary_activity_code VARCHAR(10),
    unit_type_code VARCHAR(10),
    operating_hours_code VARCHAR(10),
    
    -- Status (CRITICAL FOR SALES!)
    deactivation_reason_code VARCHAR(10), -- NULL = ACTIVE
    
    -- Characteristics
    is_24_7 BOOLEAN DEFAULT FALSE,
    is_philanthropic BOOLEAN DEFAULT FALSE,
    has_internet BOOLEAN DEFAULT FALSE,
    has_formal_contract BOOLEAN DEFAULT FALSE,
    
    -- Dates
    license_issue_date DATE,
    sanitary_license_expiry DATE,
    last_updated_date DATE,
    
    -- Metadata
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (municipality_id) REFERENCES municipalities(municipality_id),
    FOREIGN KEY (owner_tax_id) REFERENCES facility_owners(tax_id),
    FOREIGN KEY (facility_type_code) REFERENCES facility_types(facility_type_code),
    FOREIGN KEY (deactivation_reason_code) REFERENCES deactivation_reasons(deactivation_code)
);

COMMENT ON TABLE facilities IS 'Health facilities/establishments - PRIMARY TARGET for sales';
COMMENT ON COLUMN facilities.facility_id IS 'Unique facility identifier (CO_UNIDADE)';
COMMENT ON COLUMN facilities.deactivation_reason_code IS 'NULL = ACTIVE facility, NOT NULL = deactivated';
COMMENT ON COLUMN facilities.trade_name IS 'Business/trade name (most commonly used)';
COMMENT ON COLUMN facilities.is_24_7 IS 'Open 24 hours, 7 days a week';

-- Critical indexes for sales queries
CREATE INDEX idx_facilities_municipality ON facilities(municipality_id);
CREATE INDEX idx_facilities_type ON facilities(facility_type_code);
CREATE INDEX idx_facilities_deactivation ON facilities(deactivation_reason_code);
CREATE INDEX idx_facilities_active ON facilities(facility_id) WHERE deactivation_reason_code IS NULL;
CREATE INDEX idx_facilities_geolocation ON facilities(latitude, longitude) WHERE latitude IS NOT NULL;
CREATE INDEX idx_facilities_owner ON facilities(owner_tax_id);

-- Full-text search on names
CREATE INDEX idx_facilities_trade_name_trgm ON facilities USING gin(trade_name gin_trgm_ops);
CREATE INDEX idx_facilities_legal_name_trgm ON facilities USING gin(legal_name gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- Professionals (Healthcare Professionals)
-- Doctors, nurses, technicians, etc.
-- ----------------------------------------------------------------------------
CREATE TABLE professionals (
    professional_id VARCHAR(20) PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    social_name VARCHAR(200),
    tax_id VARCHAR(20), -- Partially masked for privacy
    health_card_number VARCHAR(20),
    nationality_code VARCHAR(10),
    last_updated_date DATE,
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE professionals IS 'Healthcare professionals (doctors, nurses, etc.)';
COMMENT ON COLUMN professionals.professional_id IS 'Unique professional identifier';
COMMENT ON COLUMN professionals.social_name IS 'Preferred/social name if different from legal name';

-- Indexes for name searches
CREATE INDEX idx_professionals_name_trgm ON professionals USING gin(full_name gin_trgm_ops);

-- ============================================================================
-- RELATIONSHIP TABLES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Facility-Professionals (Employment/Assignment)
-- Links professionals to facilities - WHO WORKS WHERE
-- CRITICAL: Use termination_date to find ACTIVE employees
-- ----------------------------------------------------------------------------
CREATE TABLE facility_professionals (
    facility_id VARCHAR(20) NOT NULL,
    professional_id VARCHAR(20) NOT NULL,
    occupation_code VARCHAR(10) NOT NULL, -- CBO code (specialty)
    municipality_id VARCHAR(10),
    service_area_id VARCHAR(10),
    team_sequence_number INTEGER,
    
    -- Employment details
    service_type CHAR(1), -- S=SUS/public, N=private
    employment_type_code VARCHAR(10),
    
    -- Dates (CRITICAL FOR ACTIVE STATUS!)
    start_date DATE,
    termination_date DATE, -- NULL = CURRENTLY EMPLOYED
    
    -- Other
    micro_area_code VARCHAR(10),
    other_team_cnes VARCHAR(20),
    last_updated_date DATE,
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (facility_id, professional_id, occupation_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id),
    FOREIGN KEY (municipality_id) REFERENCES municipalities(municipality_id)
);

COMMENT ON TABLE facility_professionals IS 'Links professionals to facilities - employment records';
COMMENT ON COLUMN facility_professionals.termination_date IS 'NULL = currently employed, NOT NULL = terminated';
COMMENT ON COLUMN facility_professionals.occupation_code IS 'CBO code indicating specialty/role';

-- Critical indexes for finding active professionals
CREATE INDEX idx_fp_facility ON facility_professionals(facility_id);
CREATE INDEX idx_fp_professional ON facility_professionals(professional_id);
CREATE INDEX idx_fp_occupation ON facility_professionals(occupation_code);
CREATE INDEX idx_fp_termination ON facility_professionals(termination_date);
CREATE INDEX idx_fp_active ON facility_professionals(facility_id, professional_id) WHERE termination_date IS NULL;

-- ----------------------------------------------------------------------------
-- Facility Services
-- Services and specialties offered by each facility
-- ----------------------------------------------------------------------------
CREATE TABLE facility_services (
    facility_id VARCHAR(20) NOT NULL,
    service_code VARCHAR(10) NOT NULL,
    classification_code VARCHAR(10) NOT NULL,
    characteristic_type VARCHAR(10) NOT NULL,
    owner_tax_id VARCHAR(20) NOT NULL,
    address_complement VARCHAR(20) NOT NULL,
    
    -- Capacity
    ambulatory_capacity INTEGER,
    ambulatory_capacity_sus INTEGER,
    hospital_capacity INTEGER,
    hospital_capacity_sus INTEGER,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    
    last_updated_date DATE,
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (facility_id, service_code, classification_code, characteristic_type, owner_tax_id, address_complement),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_services IS 'Services and specialties offered by facilities';
COMMENT ON COLUMN facility_services.is_active IS 'Whether this service is currently active';

CREATE INDEX idx_fs_facility ON facility_services(facility_id);
CREATE INDEX idx_fs_service ON facility_services(service_code);
CREATE INDEX idx_fs_classification ON facility_services(classification_code);
CREATE INDEX idx_fs_active ON facility_services(facility_id, service_code) WHERE is_active = TRUE;

-- ----------------------------------------------------------------------------
-- Facility Equipment
-- Equipment inventory at facilities
-- ----------------------------------------------------------------------------
CREATE TABLE facility_equipment (
    facility_id VARCHAR(20) NOT NULL,
    equipment_code VARCHAR(10) NOT NULL,
    equipment_category_code VARCHAR(10),
    quantity INTEGER NOT NULL DEFAULT 0,
    operational_status VARCHAR(10), -- E=In use, D=Inactive, M=Maintenance
    last_updated_date DATE,
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (facility_id, equipment_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_equipment IS 'Equipment inventory at facilities';
COMMENT ON COLUMN facility_equipment.operational_status IS 'E=In use, D=Inactive, M=Maintenance';

CREATE INDEX idx_fe_facility ON facility_equipment(facility_id);
CREATE INDEX idx_fe_equipment ON facility_equipment(equipment_code);
CREATE INDEX idx_fe_category ON facility_equipment(equipment_category_code);
CREATE INDEX idx_fe_operational ON facility_equipment(operational_status);

-- ----------------------------------------------------------------------------
-- Professional Workload
-- Working hours, credentials, and licenses
-- ----------------------------------------------------------------------------
CREATE TABLE professional_workload (
    facility_id VARCHAR(20) NOT NULL,
    professional_id VARCHAR(20) NOT NULL,
    occupation_code VARCHAR(10) NOT NULL,
    
    -- Hours
    weekly_hours_ambulatory INTEGER,
    
    -- Type
    service_type CHAR(1), -- S=SUS, N=private
    employment_type_code VARCHAR(10),
    
    -- Credentials
    professional_council_code VARCHAR(10), -- CRM, CRO, CRF, etc.
    license_number VARCHAR(20),
    license_state CHAR(2),
    
    -- Roles
    is_preceptor BOOLEAN DEFAULT FALSE,
    is_resident BOOLEAN DEFAULT FALSE,
    
    last_updated_date DATE,
    updated_by_user VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (facility_id, professional_id, occupation_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id)
);

COMMENT ON TABLE professional_workload IS 'Working hours and professional credentials';
COMMENT ON COLUMN professional_workload.professional_council_code IS 'CRM=Medical, CRO=Dental, CRF=Pharmacy, etc.';
COMMENT ON COLUMN professional_workload.is_preceptor IS 'Teaches/supervises residents';

CREATE INDEX idx_pw_facility ON professional_workload(facility_id);
CREATE INDEX idx_pw_professional ON professional_workload(professional_id);
CREATE INDEX idx_pw_council ON professional_workload(professional_council_code);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Active facilities with location info
CREATE VIEW active_facilities AS
SELECT 
    f.*,
    m.municipality_name,
    s.state_name,
    s.state_code,
    ft.facility_type_name
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN facility_types ft ON ft.facility_type_code = f.facility_type_code
WHERE f.deactivation_reason_code IS NULL;

COMMENT ON VIEW active_facilities IS 'Active facilities with location details';

-- Active professionals at facilities
CREATE VIEW active_facility_professionals AS
SELECT 
    fp.*,
    f.trade_name AS facility_name,
    p.full_name AS professional_name,
    pw.professional_council_code,
    pw.license_number
FROM facility_professionals fp
JOIN facilities f ON fp.facility_id = f.facility_id
JOIN professionals p ON fp.professional_id = p.professional_id
LEFT JOIN professional_workload pw 
    ON fp.facility_id = pw.facility_id 
    AND fp.professional_id = pw.professional_id
    AND fp.occupation_code = pw.occupation_code
WHERE fp.termination_date IS NULL
    AND f.deactivation_reason_code IS NULL;

COMMENT ON VIEW active_facility_professionals IS 'Currently employed professionals at active facilities';

-- Facility equipment in use
CREATE VIEW facility_equipment_in_use AS
SELECT 
    fe.*,
    f.trade_name AS facility_name,
    f.municipality_id,
    ec.equipment_name,
    ecat.category_name AS equipment_category
FROM facility_equipment fe
JOIN facilities f ON fe.facility_id = f.facility_id
LEFT JOIN equipment_catalog ec ON ec.equipment_code = fe.equipment_code
LEFT JOIN equipment_categories ecat ON ecat.category_code = fe.equipment_category_code
WHERE fe.operational_status = 'E'
    AND fe.quantity > 0
    AND f.deactivation_reason_code IS NULL;

COMMENT ON VIEW facility_equipment_in_use IS 'Equipment currently in use at active facilities';

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to check if facility is active
CREATE OR REPLACE FUNCTION is_facility_active(p_facility_id VARCHAR)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM facilities 
        WHERE facility_id = p_facility_id 
        AND deactivation_reason_code IS NULL
    );
END;
$$ LANGUAGE plpgsql;

-- Function to check if professional is currently employed at facility
CREATE OR REPLACE FUNCTION is_professional_active_at_facility(
    p_professional_id VARCHAR,
    p_facility_id VARCHAR
)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM facility_professionals 
        WHERE professional_id = p_professional_id
        AND facility_id = p_facility_id
        AND termination_date IS NULL
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- GRANTS (Adjust for your specific users)
-- ============================================================================

-- Grant read access to application user (adjust username as needed)
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO sales_app_user;
-- GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO sales_app_user;

-- ============================================================================
-- COMPLETION
-- ============================================================================

-- Display table statistics
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Success message
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Sales App Schema Created Successfully!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - states';
    RAISE NOTICE '  - municipalities';
    RAISE NOTICE '  - facility_types';
    RAISE NOTICE '  - deactivation_reasons';
    RAISE NOTICE '  - service_specialties';
    RAISE NOTICE '  - equipment_catalog';
    RAISE NOTICE '  - professional_councils';
    RAISE NOTICE '  - equipment_categories';
    RAISE NOTICE '  - service_classifications';
    RAISE NOTICE '  - facility_owners';
    RAISE NOTICE '  - facilities';
    RAISE NOTICE '  - professionals';
    RAISE NOTICE '  - facility_professionals';
    RAISE NOTICE '  - facility_services';
    RAISE NOTICE '  - facility_equipment';
    RAISE NOTICE '  - professional_workload';
    RAISE NOTICE '';
    RAISE NOTICE 'Views created:';
    RAISE NOTICE '  - active_facilities';
    RAISE NOTICE '  - active_facility_professionals';
    RAISE NOTICE '  - facility_equipment_in_use';
    RAISE NOTICE '';
END $$;
