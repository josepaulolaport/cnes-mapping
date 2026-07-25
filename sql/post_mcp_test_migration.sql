-- Post-migration: analyze and sanity-check row counts
SET search_path TO mcp_test, public;

ANALYZE;

SELECT 'states' AS table_name, COUNT(*) AS row_count FROM states
UNION ALL SELECT 'municipalities', COUNT(*) FROM municipalities
UNION ALL SELECT 'facility_types', COUNT(*) FROM facility_types
UNION ALL SELECT 'deactivation_reasons', COUNT(*) FROM deactivation_reasons
UNION ALL SELECT 'service_specialties', COUNT(*) FROM service_specialties
UNION ALL SELECT 'equipment_categories', COUNT(*) FROM equipment_categories
UNION ALL SELECT 'equipment_catalog', COUNT(*) FROM equipment_catalog
UNION ALL SELECT 'professional_councils', COUNT(*) FROM professional_councils
UNION ALL SELECT 'service_classifications', COUNT(*) FROM service_classifications
UNION ALL SELECT 'facility_owners', COUNT(*) FROM facility_owners
UNION ALL SELECT 'facilities', COUNT(*) FROM facilities
UNION ALL SELECT 'professionals', COUNT(*) FROM professionals
UNION ALL SELECT 'facility_professionals', COUNT(*) FROM facility_professionals
UNION ALL SELECT 'facility_services', COUNT(*) FROM facility_services
UNION ALL SELECT 'facility_equipment', COUNT(*) FROM facility_equipment
UNION ALL SELECT 'professional_workload', COUNT(*) FROM professional_workload
ORDER BY table_name;
