-- ============================================================================
-- MCP TEST VIEWS - PostgreSQL
-- Apply AFTER data load (pgloader). Schema: mcp_test
-- ============================================================================

SET search_path TO mcp_test, public;

DROP VIEW IF EXISTS professional_search_view CASCADE;
DROP VIEW IF EXISTS facility_search_view CASCADE;
DROP VIEW IF EXISTS active_facilities CASCADE;
DROP VIEW IF EXISTS active_facility_professionals CASCADE;
DROP VIEW IF EXISTS facility_equipment_in_use CASCADE;

CREATE VIEW professional_search_view AS
SELECT
    p.professional_id,
    p.full_name,
    p.social_name,
    p.tax_id,
    p.health_card_number,
    COUNT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN fp.facility_id END) AS active_facilities_count,
    STRING_AGG(DISTINCT CASE WHEN fp.termination_date IS NULL THEN f.trade_name END, ', ') AS current_facilities,
    STRING_AGG(DISTINCT CASE WHEN fp.termination_date IS NULL THEN m.municipality_name || ' - ' || s.state_code END, ', ') AS current_locations,
    STRING_AGG(DISTINCT pw.professional_council_code || ': ' || pw.license_number, ', ') AS licenses,
    STRING_AGG(DISTINCT pc.council_name, ', ') AS councils,
    STRING_AGG(DISTINCT fp.occupation_code, ', ') AS occupation_codes,
    STRING_AGG(DISTINCT o.occupation_name, ', ') AS occupation_names,
    SUM(CASE WHEN fp.termination_date IS NULL THEN 1 ELSE 0 END) AS active_positions,
    SUM(pw.weekly_hours_ambulatory) AS total_weekly_hours,
    MAX(CASE WHEN pw.is_preceptor = 1 THEN 1 ELSE 0 END) AS is_preceptor,
    MAX(CASE WHEN pw.is_resident = 1 THEN 1 ELSE 0 END) AS is_resident,
    MAX(fp.last_updated_date) AS last_employment_update,
    MAX(pw.last_updated_date) AS last_workload_update
FROM professionals p
LEFT JOIN facility_professionals fp ON p.professional_id = fp.professional_id
LEFT JOIN facilities f ON fp.facility_id = f.facility_id AND f.deactivation_reason_code IS NULL
LEFT JOIN municipalities m ON f.municipality_id = m.municipality_id
LEFT JOIN states s ON m.state_code = s.state_code
LEFT JOIN professional_workload pw ON p.professional_id = pw.professional_id
LEFT JOIN professional_councils pc ON pw.professional_council_code = pc.council_code
LEFT JOIN occupations o ON fp.occupation_code = o.occupation_code
GROUP BY p.professional_id, p.full_name, p.social_name, p.tax_id, p.health_card_number;

COMMENT ON VIEW professional_search_view IS 'Pre-aggregated professional search: employment, licenses, locations. Prefer for discovery queries.';

CREATE VIEW facility_search_view AS
SELECT
    f.facility_id,
    f.cnes_code,
    f.legal_name,
    f.trade_name,
    f.street_address || COALESCE(', ' || f.street_number, '') AS full_address,
    f.neighborhood,
    f.postal_code,
    m.municipality_name,
    s.state_code,
    s.state_name,
    f.phone_number,
    f.email,
    f.website_url,
    fr.representative_name,
    fr.role_title AS representative_role,
    fr.email AS representative_email,
    f.latitude,
    f.longitude,
    ft.facility_type_name AS facility_type,
    f.facility_type_code,
    f.unit_type_code,
    f.unit_type_name,
    f.unit_subtype_name,
    mt.legal_name AS maintainer_name,
    f.owner_tax_id AS maintainer_tax_id,
    f.is_24_7,
    f.is_philanthropic,
    f.has_internet,
    CASE WHEN f.deactivation_reason_code IS NULL THEN 'ACTIVE' ELSE 'INACTIVE' END AS status,
    dr.deactivation_reason,
    COUNT(DISTINCT CASE WHEN fp.termination_date IS NULL THEN fp.professional_id END) AS active_professionals_count,
    COUNT(DISTINCT fp.occupation_code) AS occupation_types_count,
    COUNT(DISTINCT CASE WHEN fs.is_active = 1 THEN fs.service_code END) AS active_services_count,
    STRING_AGG(DISTINCT ss.service_name, ', ') AS specialties,
    STRING_AGG(DISTINCT at.agreement_name, ', ' ORDER BY at.agreement_name) AS agreement_types,
    COUNT(DISTINCT fpi.installation_code) AS physical_installation_types_count,
    STRING_AGG(DISTINCT pi.installation_name, ', ') AS physical_installations,
    COUNT(DISTINCT fe.equipment_code) AS equipment_types_count,
    SUM(fe.quantity) AS total_equipment_count,
    STRING_AGG(DISTINCT ecat.category_name, ', ') AS equipment_categories,
    SUM(fs.ambulatory_capacity) AS total_ambulatory_capacity,
    SUM(fs.hospital_capacity) AS total_hospital_capacity,
    MAX(fp.last_updated_date) AS last_professional_update,
    MAX(fe.last_updated_date) AS last_equipment_update,
    f.last_updated_date AS facility_last_update
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN facility_types ft ON f.facility_type_code = ft.facility_type_code
LEFT JOIN maintainers mt ON f.owner_tax_id = mt.tax_id
LEFT JOIN deactivation_reasons dr ON f.deactivation_reason_code = dr.deactivation_code
LEFT JOIN facility_representatives fr ON f.facility_id = fr.facility_id
LEFT JOIN facility_professionals fp ON f.facility_id = fp.facility_id
LEFT JOIN facility_services fs ON f.facility_id = fs.facility_id
LEFT JOIN service_specialties ss ON fs.service_code = ss.service_code
LEFT JOIN facility_agreements fa ON f.facility_id = fa.facility_id
LEFT JOIN agreement_types at ON fa.agreement_code = at.agreement_code
LEFT JOIN facility_physical_installations fpi ON f.facility_id = fpi.facility_id
LEFT JOIN physical_installations pi ON fpi.installation_code = pi.installation_code
LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id
LEFT JOIN equipment_categories ecat ON fe.equipment_category_code = ecat.category_code
GROUP BY f.facility_id, f.cnes_code, f.legal_name, f.trade_name, f.street_address, f.street_number,
         f.neighborhood, f.postal_code, m.municipality_name, s.state_code, s.state_name,
         f.phone_number, f.email, f.website_url,
         fr.representative_name, fr.role_title, fr.email,
         f.latitude, f.longitude, ft.facility_type_name,
         f.facility_type_code, f.unit_type_code, f.unit_type_name, f.unit_subtype_name,
         mt.legal_name, f.owner_tax_id, f.is_24_7, f.is_philanthropic, f.has_internet,
         f.deactivation_reason_code, dr.deactivation_reason, f.last_updated_date;

COMMENT ON VIEW facility_search_view IS 'Pre-aggregated facility search with staff, services, equipment counts. Prefer for sales discovery.';

CREATE VIEW active_facilities AS
SELECT
    f.*,
    m.municipality_name,
    s.state_code,
    s.state_name,
    ft.facility_type_name
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN facility_types ft ON f.facility_type_code = ft.facility_type_code
WHERE f.deactivation_reason_code IS NULL;

COMMENT ON VIEW active_facilities IS 'Active facilities only (deactivation_reason_code IS NULL) with location and type.';

CREATE VIEW active_facility_professionals AS
SELECT
    fp.*,
    f.trade_name AS facility_name,
    p.full_name AS professional_name,
    o.occupation_name,
    pw.professional_council_code,
    pw.license_number
FROM facility_professionals fp
JOIN facilities f ON fp.facility_id = f.facility_id
JOIN professionals p ON fp.professional_id = p.professional_id
LEFT JOIN occupations o ON fp.occupation_code = o.occupation_code
LEFT JOIN professional_workload pw
    ON fp.facility_id = pw.facility_id
    AND fp.professional_id = pw.professional_id
    AND fp.occupation_code = pw.occupation_code
WHERE fp.termination_date IS NULL
    AND f.deactivation_reason_code IS NULL;

COMMENT ON VIEW active_facility_professionals IS 'Currently employed professionals at active facilities.';

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

COMMENT ON VIEW facility_equipment_in_use IS 'Equipment currently in use at active facilities (operational_status=E, quantity>0).';

-- Optional pg_trgm indexes for text search
CREATE INDEX IF NOT EXISTS idx_facilities_trade_name_trgm
    ON facilities USING gin (trade_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_professionals_name_trgm
    ON professionals USING gin (full_name gin_trgm_ops);
