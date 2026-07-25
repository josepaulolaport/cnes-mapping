-- ============================================================================
-- SALES APP SAMPLE QUERIES
-- ============================================================================
-- Collection of useful SQL queries for the Sales App
-- All queries use the new clear schema names
-- ============================================================================

-- ============================================================================
-- BASIC QUERIES
-- ============================================================================

-- 1. All active facilities in a specific city
SELECT 
    facility_id,
    trade_name,
    phone_number,
    email,
    street_address
FROM facilities
WHERE municipality_id = '355030'  -- São Paulo
    AND deactivation_reason_code IS NULL
ORDER BY trade_name;

-- 2. All active facilities in a state
SELECT 
    f.facility_id,
    f.trade_name,
    m.municipality_name,
    f.phone_number
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
WHERE s.state_name = 'SÃO PAULO'
    AND f.deactivation_reason_code IS NULL
ORDER BY m.municipality_name, f.trade_name;

-- 3. Facilities by type
SELECT 
    f.trade_name,
    rd.description AS facility_type,
    f.phone_number
FROM facilities f
JOIN reference_data rd 
    ON rd.reference_type = 'facility_type' 
    AND rd.code = f.facility_type_code
WHERE f.deactivation_reason_code IS NULL
ORDER BY rd.description, f.trade_name
LIMIT 100;

-- ============================================================================
-- GEOGRAPHIC / LOCATION QUERIES
-- ============================================================================

-- 4. Facilities near a location (using lat/long)
-- Find facilities within ~5km radius
SELECT 
    facility_id,
    trade_name,
    phone_number,
    latitude,
    longitude,
    -- Calculate approximate distance in km
    (
        6371 * acos(
            cos(radians(-23.550520)) * cos(radians(latitude)) * 
            cos(radians(longitude) - radians(-46.633308)) + 
            sin(radians(-23.550520)) * sin(radians(latitude))
        )
    ) AS distance_km
FROM facilities
WHERE latitude IS NOT NULL
    AND longitude IS NOT NULL
    AND deactivation_reason_code IS NULL
    AND (
        6371 * acos(
            cos(radians(-23.550520)) * cos(radians(latitude)) * 
            cos(radians(longitude) - radians(-46.633308)) + 
            sin(radians(-23.550520)) * sin(radians(latitude))
        )
    ) < 5
ORDER BY distance_km;

-- 5. Facilities with geolocation
SELECT 
    COUNT(*) as total_facilities,
    COUNT(CASE WHEN latitude IS NOT NULL THEN 1 END) as with_geolocation,
    COUNT(CASE WHEN latitude IS NULL THEN 1 END) as without_geolocation
FROM facilities
WHERE deactivation_reason_code IS NULL;

-- ============================================================================
-- SPECIALTY / SERVICE QUERIES
-- ============================================================================

-- 6. Facilities offering specific medical specialty
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    rs.description AS service_specialty,
    m.municipality_name
FROM facilities f
JOIN facility_services fs ON f.facility_id = fs.facility_id
JOIN reference_data rs 
    ON rs.reference_type = 'service_specialty' 
    AND rs.code = fs.service_code
JOIN municipalities m ON f.municipality_id = m.municipality_id
WHERE f.deactivation_reason_code IS NULL
    AND fs.is_active = TRUE
    AND rs.description LIKE '%CARDIO%'
ORDER BY m.municipality_name, f.trade_name;

-- 7. Count facilities by specialty
SELECT 
    rs.description AS specialty,
    COUNT(DISTINCT f.facility_id) AS facility_count
FROM facilities f
JOIN facility_services fs ON f.facility_id = fs.facility_id
JOIN reference_data rs 
    ON rs.reference_type = 'service_specialty' 
    AND rs.code = fs.service_code
WHERE f.deactivation_reason_code IS NULL
    AND fs.is_active = TRUE
GROUP BY rs.description
ORDER BY facility_count DESC
LIMIT 20;

-- 8. Facilities with multiple specialties (good prospects!)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    COUNT(DISTINCT fs.service_code) AS specialty_count
FROM facilities f
JOIN facility_services fs ON f.facility_id = fs.facility_id
WHERE f.deactivation_reason_code IS NULL
    AND fs.is_active = TRUE
GROUP BY f.facility_id, f.trade_name, f.phone_number
HAVING COUNT(DISTINCT fs.service_code) >= 5
ORDER BY specialty_count DESC;

-- ============================================================================
-- EQUIPMENT QUERIES
-- ============================================================================

-- 9. Facilities with specific equipment
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    re.description AS equipment_name,
    fe.quantity,
    fe.operational_status
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data re 
    ON re.reference_type = 'equipment_catalog' 
    AND re.code = fe.equipment_code
WHERE f.deactivation_reason_code IS NULL
    AND re.description LIKE '%RAIO%X%'
    AND fe.quantity > 0
ORDER BY fe.quantity DESC;

-- 10. Facilities with high-value equipment (MRI, CT, etc.)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    re.description AS equipment_name,
    fe.quantity
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data re 
    ON re.reference_type = 'equipment_catalog' 
    AND re.code = fe.equipment_code
WHERE f.deactivation_reason_code IS NULL
    AND fe.quantity > 0
    AND (
        re.description LIKE '%RESSONANCIA%'
        OR re.description LIKE '%TOMOGRAFIA%'
        OR re.description LIKE '%MAMOGRAFO%'
    )
ORDER BY f.trade_name;

-- 11. Equipment inventory by facility
SELECT 
    f.trade_name,
    f.phone_number,
    COUNT(DISTINCT fe.equipment_code) AS unique_equipment_types,
    SUM(fe.quantity) AS total_equipment_units
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
WHERE f.deactivation_reason_code IS NULL
    AND fe.quantity > 0
GROUP BY f.facility_id, f.trade_name, f.phone_number
ORDER BY total_equipment_units DESC
LIMIT 50;

-- 12. Equipment maintenance opportunities (broken equipment)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    re.description AS equipment_name,
    fe.quantity,
    fe.operational_status
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data re 
    ON re.reference_type = 'equipment_catalog' 
    AND re.code = fe.equipment_code
WHERE f.deactivation_reason_code IS NULL
    AND fe.operational_status IN ('D', 'M')  -- D=Inactive, M=Maintenance
    AND fe.quantity > 0
ORDER BY f.trade_name;

-- ============================================================================
-- PROFESSIONAL QUERIES
-- ============================================================================

-- 13. Currently employed professionals at active facilities
SELECT 
    p.professional_id,
    p.full_name,
    f.trade_name AS facility_name,
    f.phone_number AS facility_phone,
    fp.occupation_code,
    fp.start_date
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN facilities f ON fp.facility_id = f.facility_id
WHERE fp.termination_date IS NULL
    AND f.deactivation_reason_code IS NULL
LIMIT 100;

-- 14. Doctors (CRM) at specific facility
SELECT 
    p.full_name,
    pw.license_number,
    pw.license_state,
    fp.occupation_code,
    pw.weekly_hours_ambulatory
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN professional_workload pw 
    ON p.professional_id = pw.professional_id
    AND fp.facility_id = pw.facility_id
WHERE fp.facility_id = 'FACILITY_ID_HERE'
    AND fp.termination_date IS NULL
    AND pw.professional_council_code = 'CRM'
ORDER BY p.full_name;

-- 15. Cardiologists in São Paulo
SELECT 
    p.full_name,
    f.trade_name AS facility_name,
    f.phone_number,
    m.municipality_name,
    pw.license_number
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN facilities f ON fp.facility_id = f.facility_id
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN professional_workload pw 
    ON p.professional_id = pw.professional_id
    AND fp.facility_id = pw.facility_id
WHERE fp.termination_date IS NULL
    AND f.deactivation_reason_code IS NULL
    AND s.state_name = 'SÃO PAULO'
    AND fp.occupation_code IN ('225120', '225125')  -- Cardiologist CBO codes
ORDER BY m.municipality_name, p.full_name
LIMIT 100;

-- 16. Facilities with most professionals (decision-maker access)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    COUNT(DISTINCT fp.professional_id) AS professional_count
FROM facilities f
JOIN facility_professionals fp ON f.facility_id = fp.facility_id
WHERE f.deactivation_reason_code IS NULL
    AND fp.termination_date IS NULL
GROUP BY f.facility_id, f.trade_name, f.phone_number
ORDER BY professional_count DESC
LIMIT 50;

-- ============================================================================
-- SALES INTELLIGENCE QUERIES
-- ============================================================================

-- 17. High-value prospects (large facilities with equipment)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    f.email,
    COUNT(DISTINCT fs.service_code) AS specialties,
    COUNT(DISTINCT fe.equipment_code) AS equipment_types,
    COUNT(DISTINCT fp.professional_id) AS professionals
FROM facilities f
LEFT JOIN facility_services fs ON f.facility_id = fs.facility_id AND fs.is_active = TRUE
LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id AND fe.quantity > 0
LEFT JOIN facility_professionals fp ON f.facility_id = fp.facility_id AND fp.termination_date IS NULL
WHERE f.deactivation_reason_code IS NULL
GROUP BY f.facility_id, f.trade_name, f.phone_number, f.email
HAVING COUNT(DISTINCT fs.service_code) >= 3
    OR COUNT(DISTINCT fe.equipment_code) >= 5
    OR COUNT(DISTINCT fp.professional_id) >= 10
ORDER BY 
    COUNT(DISTINCT fs.service_code) + 
    COUNT(DISTINCT fe.equipment_code) + 
    COUNT(DISTINCT fp.professional_id) DESC
LIMIT 100;

-- 18. Facilities that recently activated (potential expansion)
-- Note: Need historical data to compare; this shows facilities updated recently
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    f.last_updated_date
FROM facilities f
WHERE f.deactivation_reason_code IS NULL
    AND f.last_updated_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY f.last_updated_date DESC;

-- 19. Renewal opportunities (facilities with old equipment data)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    re.description AS equipment_name,
    fe.quantity,
    fe.last_updated_date
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data re 
    ON re.reference_type = 'equipment_catalog' 
    AND re.code = fe.equipment_code
WHERE f.deactivation_reason_code IS NULL
    AND fe.quantity > 0
    AND fe.last_updated_date < CURRENT_DATE - INTERVAL '2 years'
ORDER BY fe.last_updated_date;

-- 20. Facilities without equipment (sales opportunity!)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    f.email,
    ft.description AS facility_type
FROM facilities f
LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data ft 
    ON ft.reference_type = 'facility_type' 
    AND ft.code = f.facility_type_code
WHERE f.deactivation_reason_code IS NULL
    AND fe.facility_id IS NULL
    AND f.facility_type_code NOT IN ('01', '02')  -- Exclude tiny posts
ORDER BY f.trade_name
LIMIT 100;

-- ============================================================================
-- DEACTIVATION / CHURN TRACKING
-- ============================================================================

-- 21. Recently deactivated facilities (why did they close?)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    rd.description AS deactivation_reason,
    f.last_updated_date
FROM facilities f
JOIN reference_data rd 
    ON rd.reference_type = 'deactivation_reason' 
    AND rd.code = f.deactivation_reason_code
WHERE f.deactivation_reason_code IS NOT NULL
ORDER BY f.last_updated_date DESC
LIMIT 100;

-- 22. Professionals who left facilities (rehire/contact opportunities)
SELECT 
    p.full_name,
    f.trade_name AS former_facility,
    fp.termination_date,
    fp.occupation_code
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN facilities f ON fp.facility_id = f.facility_id
WHERE fp.termination_date IS NOT NULL
    AND fp.termination_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY fp.termination_date DESC
LIMIT 100;

-- ============================================================================
-- REPORTING / ANALYTICS
-- ============================================================================

-- 23. Facilities by state (territory planning)
SELECT 
    s.state_name,
    COUNT(f.facility_id) AS facility_count,
    COUNT(CASE WHEN f.deactivation_reason_code IS NULL THEN 1 END) AS active_count,
    COUNT(CASE WHEN f.deactivation_reason_code IS NOT NULL THEN 1 END) AS inactive_count
FROM states s
LEFT JOIN municipalities m ON s.state_code = m.state_code
LEFT JOIN facilities f ON m.municipality_id = f.municipality_id
GROUP BY s.state_code, s.state_name
ORDER BY active_count DESC;

-- 24. Equipment distribution analysis
SELECT 
    rc.description AS equipment_category,
    COUNT(DISTINCT f.facility_id) AS facilities_with_equipment,
    SUM(fe.quantity) AS total_units
FROM facility_equipment fe
JOIN facilities f ON fe.facility_id = f.facility_id
JOIN reference_data rc 
    ON rc.reference_type = 'equipment_category' 
    AND rc.code = fe.equipment_category_code
WHERE f.deactivation_reason_code IS NULL
    AND fe.quantity > 0
GROUP BY rc.description
ORDER BY total_units DESC;

-- 25. Professional distribution by council
SELECT 
    rd.description AS professional_council,
    COUNT(DISTINCT p.professional_id) AS professional_count
FROM professionals p
JOIN professional_workload pw ON p.professional_id = pw.professional_id
JOIN reference_data rd 
    ON rd.reference_type = 'professional_council' 
    AND rd.code = pw.professional_council_code
GROUP BY rd.description
ORDER BY professional_count DESC;

-- ============================================================================
-- COMBINED / COMPLEX QUERIES
-- ============================================================================

-- 26. Complete facility profile (for account detail page)
SELECT 
    f.facility_id,
    f.trade_name,
    f.legal_name,
    f.phone_number,
    f.email,
    f.website_url,
    f.street_address || ' ' || f.street_number AS full_address,
    f.neighborhood,
    m.municipality_name,
    s.state_name,
    f.postal_code,
    ft.description AS facility_type,
    f.is_24_7,
    f.latitude,
    f.longitude,
    COUNT(DISTINCT fs.service_code) AS service_count,
    COUNT(DISTINCT fe.equipment_code) AS equipment_count,
    COUNT(DISTINCT fp.professional_id) AS professional_count
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
LEFT JOIN reference_data ft 
    ON ft.reference_type = 'facility_type' 
    AND ft.code = f.facility_type_code
LEFT JOIN facility_services fs ON f.facility_id = fs.facility_id AND fs.is_active = TRUE
LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id AND fe.quantity > 0
LEFT JOIN facility_professionals fp ON f.facility_id = fp.facility_id AND fp.termination_date IS NULL
WHERE f.facility_id = 'FACILITY_ID_HERE'
GROUP BY 
    f.facility_id, f.trade_name, f.legal_name, f.phone_number, f.email, 
    f.website_url, f.street_address, f.street_number, f.neighborhood,
    m.municipality_name, s.state_name, f.postal_code, ft.description,
    f.is_24_7, f.latitude, f.longitude;

-- 27. Sales lead scoring (multi-factor ranking)
WITH facility_scores AS (
    SELECT 
        f.facility_id,
        f.trade_name,
        f.phone_number,
        COUNT(DISTINCT fs.service_code) * 2 AS service_score,
        COUNT(DISTINCT fe.equipment_code) * 3 AS equipment_score,
        COUNT(DISTINCT fp.professional_id) AS staff_score,
        CASE WHEN f.email IS NOT NULL THEN 5 ELSE 0 END AS contact_score,
        CASE WHEN f.latitude IS NOT NULL THEN 3 ELSE 0 END AS location_score
    FROM facilities f
    LEFT JOIN facility_services fs ON f.facility_id = fs.facility_id AND fs.is_active = TRUE
    LEFT JOIN facility_equipment fe ON f.facility_id = fe.facility_id AND fe.quantity > 0
    LEFT JOIN facility_professionals fp ON f.facility_id = fp.facility_id AND fp.termination_date IS NULL
    WHERE f.deactivation_reason_code IS NULL
    GROUP BY f.facility_id, f.trade_name, f.phone_number, f.email, f.latitude
)
SELECT 
    facility_id,
    trade_name,
    phone_number,
    (service_score + equipment_score + staff_score + contact_score + location_score) AS total_score,
    service_score,
    equipment_score,
    staff_score
FROM facility_scores
ORDER BY total_score DESC
LIMIT 100;

-- ============================================================================
-- SEARCH QUERIES (Full-Text)
-- ============================================================================

-- 28. Search facilities by name (using trigram similarity)
-- Requires: CREATE EXTENSION pg_trgm;
SELECT 
    facility_id,
    trade_name,
    phone_number,
    similarity(trade_name, 'Hospital Santa') AS sim_score
FROM facilities
WHERE trade_name % 'Hospital Santa'  -- % is similarity operator
    AND deactivation_reason_code IS NULL
ORDER BY sim_score DESC
LIMIT 20;

-- 29. Search professionals by name
SELECT 
    professional_id,
    full_name,
    similarity(full_name, 'João Silva') AS sim_score
FROM professionals
WHERE full_name % 'João Silva'
ORDER BY sim_score DESC
LIMIT 20;

-- ============================================================================
-- BATCH OPERATIONS
-- ============================================================================

-- 30. Export facility list for sales team (CSV-ready)
SELECT 
    f.facility_id,
    f.trade_name,
    f.phone_number,
    f.email,
    m.municipality_name || ', ' || s.state_code AS location,
    f.street_address || ' ' || COALESCE(f.street_number, '') AS address
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
WHERE f.deactivation_reason_code IS NULL
    AND f.phone_number IS NOT NULL
ORDER BY s.state_name, m.municipality_name, f.trade_name;

-- ============================================================================
-- END OF SAMPLE QUERIES
-- ============================================================================

-- Notes:
-- - Replace 'FACILITY_ID_HERE' with actual facility IDs
-- - Adjust date intervals as needed
-- - CBO codes (occupation_code) vary; research specific codes for your needs
-- - All queries filter for active facilities unless specifically looking at deactivated
-- - Use LIMIT clauses to avoid returning too many results
