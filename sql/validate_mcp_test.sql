-- Validation queries for mcp_test migration
SET search_path TO mcp_test, public;

-- Expected from SQLite (approximate)
-- states: 27, facilities: 623208, professionals: ~7540800, facility_professionals: ~863664

SELECT 'facilities' AS check_name,
       COUNT(*) AS actual,
       623208 AS expected
FROM facilities;

SELECT 'professionals' AS check_name,
       COUNT(*) AS actual,
       7540800 AS expected_approx
FROM professionals;

SELECT 'facility_professionals' AS check_name,
       COUNT(*) AS actual,
       863664 AS expected_approx
FROM facility_professionals;

SELECT 'states' AS check_name,
       COUNT(*) AS actual,
       27 AS expected
FROM states;

-- FK integrity (should be 0)
SELECT 'orphan_facilities_municipality' AS check_name, COUNT(*) AS violations
FROM facilities f
LEFT JOIN municipalities m ON f.municipality_id = m.municipality_id
WHERE f.municipality_id IS NOT NULL AND m.municipality_id IS NULL;

SELECT 'orphan_facility_professionals_facility' AS check_name, COUNT(*) AS violations
FROM facility_professionals fp
LEFT JOIN facilities f ON fp.facility_id = f.facility_id
WHERE f.facility_id IS NULL;

SELECT 'orphan_facility_professionals_professional' AS check_name, COUNT(*) AS violations
FROM facility_professionals fp
LEFT JOIN professionals p ON fp.professional_id = p.professional_id
WHERE p.professional_id IS NULL;

-- Active facility rule
SELECT 'active_facilities' AS check_name, COUNT(*) AS count
FROM facilities
WHERE deactivation_reason_code IS NULL;

-- Views
SELECT 'facility_search_view' AS check_name, COUNT(*) AS count FROM facility_search_view;
SELECT 'professional_search_view' AS check_name, COUNT(*) AS count FROM professional_search_view LIMIT 1;
