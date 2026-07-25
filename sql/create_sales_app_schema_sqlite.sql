-- ============================================================================
-- SALES APP DATABASE SCHEMA - SQLite Version
-- ============================================================================
-- Created from CNES Database Analysis
-- Source: Brazilian National Health Establishments Registry (CNES)
-- 
-- This schema transforms cryptic CNES naming into clear, modern names
-- for a sales application targeting medical equipment/pharma/supplies
-- ============================================================================

-- Enable foreign keys (required for SQLite)
PRAGMA foreign_keys = ON;

-- Drop tables if they exist (in reverse dependency order)
DROP TABLE IF EXISTS professional_workload;
DROP TABLE IF EXISTS facility_equipment;
DROP TABLE IF EXISTS facility_services;
DROP TABLE IF EXISTS facility_professionals;
DROP TABLE IF EXISTS service_classifications;
DROP TABLE IF EXISTS professionals;
DROP TABLE IF EXISTS facilities;
DROP TABLE IF EXISTS facility_owners;
DROP TABLE IF EXISTS municipalities;
DROP TABLE IF EXISTS states;
DROP TABLE IF EXISTS facility_types;
DROP TABLE IF EXISTS deactivation_reasons;
DROP TABLE IF EXISTS service_specialties;
DROP TABLE IF EXISTS equipment_catalog;
DROP TABLE IF EXISTS professional_councils;
DROP TABLE IF EXISTS equipment_categories;

-- Drop views if they exist
DROP VIEW IF EXISTS professional_search_view;
DROP VIEW IF EXISTS facility_search_view;
DROP VIEW IF EXISTS active_facilities;
DROP VIEW IF EXISTS active_facility_professionals;
DROP VIEW IF EXISTS facility_equipment_in_use;

-- ============================================================================
-- REFERENCE TABLES
-- ============================================================================

CREATE TABLE states (
    state_code TEXT PRIMARY KEY,
    state_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE municipalities (
    municipality_id TEXT PRIMARY KEY,
    municipality_name TEXT NOT NULL,
    state_code TEXT NOT NULL,
    registration_type TEXT,
    pact_type TEXT,
    data_submission_type TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (state_code) REFERENCES states(state_code)
);

CREATE INDEX idx_municipalities_state ON municipalities(state_code);

CREATE TABLE facility_types (
    facility_type_code TEXT PRIMARY KEY,
    facility_type_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE deactivation_reasons (
    deactivation_code TEXT PRIMARY KEY,
    deactivation_reason TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE service_specialties (
    service_code TEXT PRIMARY KEY,
    service_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE equipment_catalog (
    equipment_code TEXT NOT NULL,
    equipment_type_code TEXT NOT NULL,
    equipment_name TEXT NOT NULL,
    renem_code TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (equipment_code, equipment_type_code)
);

CREATE INDEX idx_equipment_code ON equipment_catalog(equipment_code);

CREATE TABLE professional_councils (
    council_code TEXT PRIMARY KEY,
    council_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE equipment_categories (
    category_code TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE service_classifications (
    classification_id TEXT NOT NULL,
    service_specialty_code TEXT NOT NULL,
    classification_name TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (classification_id, service_specialty_code),
    FOREIGN KEY (service_specialty_code) REFERENCES service_specialties(service_code)
);

-- ============================================================================
-- MAIN TABLES
-- ============================================================================

CREATE TABLE facility_owners (
    tax_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE facilities (
    facility_id TEXT PRIMARY KEY,
    cnes_code TEXT UNIQUE,
    
    -- Names
    legal_name TEXT,
    trade_name TEXT,
    
    -- Address
    street_address TEXT,
    street_number TEXT,
    address_complement TEXT,
    neighborhood TEXT,
    postal_code TEXT,
    municipality_id TEXT,
    health_region_id TEXT,
    
    -- Contact
    phone_number TEXT,
    fax_number TEXT,
    email TEXT,
    website_url TEXT,
    
    -- Geolocation
    latitude REAL,
    longitude REAL,
    
    -- Tax & Legal
    tax_id_cnpj TEXT,
    tax_id_cpf TEXT,
    owner_tax_id TEXT,
    legal_entity_type_code TEXT,
    entity_type TEXT,
    
    -- Classification
    facility_type_code TEXT,
    primary_activity_code TEXT,
    unit_type_code TEXT,
    operating_hours_code TEXT,
    
    -- Status (CRITICAL FOR SALES!)
    deactivation_reason_code TEXT,
    
    -- Characteristics
    is_24_7 INTEGER DEFAULT 0,
    is_philanthropic INTEGER DEFAULT 0,
    has_internet INTEGER DEFAULT 0,
    has_formal_contract INTEGER DEFAULT 0,
    
    -- Dates
    license_issue_date TEXT,
    sanitary_license_expiry TEXT,
    last_updated_date TEXT,
    
    -- Metadata
    updated_by_user TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    FOREIGN KEY (municipality_id) REFERENCES municipalities(municipality_id),
    FOREIGN KEY (owner_tax_id) REFERENCES facility_owners(tax_id),
    FOREIGN KEY (facility_type_code) REFERENCES facility_types(facility_type_code),
    FOREIGN KEY (deactivation_reason_code) REFERENCES deactivation_reasons(reason_code)
);

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
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_professionals_full_name ON professionals(full_name);
CREATE INDEX idx_professionals_tax_id ON professionals(tax_id);

CREATE TABLE facility_professionals (
    facility_id TEXT NOT NULL,
    professional_id TEXT NOT NULL,
    occupation_code TEXT NOT NULL,
    municipality_id TEXT,
    service_area_id TEXT,
    team_sequence_number INTEGER,
    
    -- Employment details
    service_type TEXT,
    employment_type_code TEXT,
    
    -- Dates (CRITICAL FOR ACTIVE STATUS!)
    start_date TEXT,
    termination_date TEXT,
    
    -- Other
    micro_area_code TEXT,
    other_team_cnes TEXT,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    PRIMARY KEY (facility_id, professional_id, occupation_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id)
);

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
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    PRIMARY KEY (facility_id, service_code, classification_code, characteristic_type, owner_tax_id, address_complement),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

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
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    PRIMARY KEY (facility_id, equipment_code, equipment_category_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (equipment_code) REFERENCES equipment_catalog(equipment_code),
    FOREIGN KEY (equipment_category_code) REFERENCES equipment_categories(category_code)
);

CREATE INDEX idx_facility_equipment_facility ON facility_equipment(facility_id);
CREATE INDEX idx_facility_equipment_equipment ON facility_equipment(equipment_code);
CREATE INDEX idx_facility_equipment_category ON facility_equipment(equipment_category_code);

CREATE TABLE professional_workload (
    facility_id TEXT NOT NULL,
    professional_id TEXT NOT NULL,
    occupation_code TEXT NOT NULL,
    weekly_hours_ambulatory INTEGER,
    service_type TEXT,
    employment_type_code TEXT NOT NULL,
    professional_council_code TEXT,
    license_number TEXT,
    license_state TEXT,
    is_preceptor INTEGER,
    is_resident INTEGER,
    last_updated_date TEXT,
    updated_by_user TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    
    PRIMARY KEY (facility_id, professional_id, occupation_code, employment_type_code),
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id),
    FOREIGN KEY (professional_id) REFERENCES professionals(professional_id),
    FOREIGN KEY (professional_council_code) REFERENCES professional_councils(council_code)
);

CREATE INDEX idx_professional_workload_facility ON professional_workload(facility_id);
CREATE INDEX idx_professional_workload_professional ON professional_workload(professional_id);
CREATE INDEX idx_professional_workload_council ON professional_workload(professional_council_code);

CREATE TABLE facility_representatives (
    facility_id TEXT PRIMARY KEY,
    representative_name TEXT NOT NULL,
    role_title TEXT,
    email TEXT,
    tax_id TEXT,
    updated_by_user TEXT,
    last_updated_date TEXT,
    origin_updated_date TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),

    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

CREATE INDEX idx_facility_representatives_name ON facility_representatives(representative_name);
CREATE INDEX idx_facility_representatives_email ON facility_representatives(email);

-- ============================================================================
-- ENHANCED SEARCH VIEWS
-- ============================================================================

-- Professional Search View: Comprehensive view for searching professionals
-- Includes all related data needed for sales searches
CREATE VIEW professional_search_view AS
SELECT 
    p.professional_id,
    p.full_name,
    p.social_name,
    p.tax_id,
    p.health_card_number,
    
    -- Current employment info
    COUNT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN fp.facility_id END) as active_facilities_count,
    GROUP_CONCAT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN f.trade_name END, ', ') as current_facilities,
    GROUP_CONCAT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN m.municipality_name || ' - ' || s.state_code END, ', ') as current_locations,
    
    -- Professional credentials
    GROUP_CONCAT(DISTINCT pw.professional_council_code || ': ' || pw.license_number, ', ') as licenses,
    GROUP_CONCAT(DISTINCT pc.council_name, ', ') as councils,
    
    -- Specialties/Occupations
    GROUP_CONCAT(DISTINCT fp.occupation_code, ', ') as occupation_codes,
    SUM(CASE WHEN fp.termination_date IS NULL THEN 1 ELSE 0 END) as active_positions,
    
    -- Work characteristics
    SUM(pw.weekly_hours_ambulatory) as total_weekly_hours,
    MAX(CASE WHEN pw.is_preceptor = 1 THEN 1 ELSE 0 END) as is_preceptor,
    MAX(CASE WHEN pw.is_resident = 1 THEN 1 ELSE 0 END) as is_resident,
    
    -- Recent activity
    MAX(fp.last_updated_date) as last_employment_update,
    MAX(pw.last_updated_date) as last_workload_update
    
FROM professionals p
LEFT JOIN facility_professionals fp ON p.professional_id = fp.professional_id
LEFT JOIN facilities f ON fp.facility_id = f.facility_id AND f.deactivation_reason_code IS NULL
LEFT JOIN municipalities m ON f.municipality_id = m.municipality_id
LEFT JOIN states s ON m.state_code = s.state_code
LEFT JOIN professional_workload pw ON p.professional_id = pw.professional_id
LEFT JOIN professional_councils pc ON pw.professional_council_code = pc.council_code
GROUP BY p.professional_id, p.full_name, p.social_name, p.tax_id, p.health_card_number;

-- Facility Search View: Comprehensive view for searching facilities
-- Includes all related data needed for sales searches
CREATE VIEW facility_search_view AS
SELECT 
    f.facility_id,
    f.cnes_code,
    f.legal_name,
    f.trade_name,
    f.street_address || COALESCE(', ' || f.street_number, '') as full_address,
    f.neighborhood,
    f.postal_code,
    m.municipality_name,
    s.state_code,
    s.state_name,
    
    -- Contact
    f.phone_number,
    f.email,
    f.website_url,
    fr.representative_name,
    fr.role_title AS representative_role,
    fr.email AS representative_email,
    
    -- Location
    f.latitude,
    f.longitude,
    
    -- Classification
    ft.type_name as facility_type,
    f.facility_type_code,
    f.is_24_7,
    f.is_philanthropic,
    f.has_internet,
    
    -- Status
    CASE WHEN f.deactivation_reason_code IS NULL THEN 'ACTIVE' ELSE 'INACTIVE' END as status,
    dr.reason_description as deactivation_reason,
    
    -- Staff counts
    COUNT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN fp.professional_id END) as active_professionals_count,
    COUNT(DISTINCT fp.occupation_code) as occupation_types_count,
    
    -- Services
    COUNT(DISTINCT CASE WHEN fs.is_active = 1 THEN fs.service_code END) as active_services_count,
    GROUP_CONCAT(DISTINCT ss.specialty_name, ', ') as specialties,
    
    -- Equipment
    COUNT(DISTINCT fe.equipment_code) as equipment_types_count,
    SUM(fe.quantity) as total_equipment_count,
    GROUP_CONCAT(DISTINCT ecat.category_name, ', ') as equipment_categories,
    
    -- Capacity
    SUM(fs.ambulatory_capacity) as total_ambulatory_capacity,
    SUM(fs.hospital_capacity) as total_hospital_capacity,
    
    -- Recent activity
    MAX(fp.last_updated_date) as last_professional_update,
    MAX(fe.last_updated_date) as last_equipment_update,
    f.last_updated_date as facility_last_update
    
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN facility_types ft ON f.facility_type_code = ft.facility_type_code
LEFT JOIN deactivation_reasons dr ON f.deactivation_reason_code = dr.reason_code
LEFT JOIN facility_representatives fr ON f.facility_id = fr.facility_id
LEFT JOIN facility_professionals fp ON f.facility_id = fp.facility_id
LEFT JOIN facility_services fs ON f.facility_id = fs.facility_id
LEFT JOIN service_specialties ss ON fs.service_code = ss.specialty_code
LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id
LEFT JOIN equipment_categories ecat ON fe.equipment_category_code = ecat.category_code
GROUP BY f.facility_id, f.cnes_code, f.legal_name, f.trade_name, f.street_address, f.street_number, 
         f.neighborhood, f.postal_code, m.municipality_name, s.state_code, s.state_name,
         f.phone_number, f.email, f.website_url,
         fr.representative_name, fr.role_title, fr.email,
         f.latitude, f.longitude, ft.type_name, 
         f.facility_type_code, f.is_24_7, f.is_philanthropic, f.has_internet, 
         f.deactivation_reason_code, dr.reason_description, f.last_updated_date;

-- Active facilities view (simplified)
CREATE VIEW active_facilities AS
SELECT 
    f.*,
    m.municipality_name,
    s.state_code,
    s.state_name,
    ft.type_name as facility_type_name
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN facility_types ft ON f.facility_type_code = ft.facility_type_code
WHERE f.deactivation_reason_code IS NULL;

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
