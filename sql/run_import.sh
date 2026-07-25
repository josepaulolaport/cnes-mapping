#!/bin/bash
# CNES Data Import Script
# Imports all tables in correct order with error logging

set -e  # Exit on error

echo "=========================================="
echo "CNES Data Import Process"
echo "=========================================="
echo ""
echo "Start time: $(date)"
echo ""

# Create error logs directory
echo "Creating error logs directory..."
mkdir -p import_errors

# Recreate database schema
echo ""
echo "=========================================="
echo "Step 1: Recreating database schema..."
echo "=========================================="
echo "Enabling PostgreSQL extensions..."
psql postgresql://user:password@localhost:5432/atlasmed_test -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
echo "Running schema creation script..."
psql postgresql://user:password@localhost:5432/atlasmed_test -f create_sales_app_schema.sql

echo ""
echo "=========================================="
echo "Step 2: Importing Reference Data..."
echo "=========================================="

echo ""
echo "[1/15] Importing states..."
python import_modular.py --table states 2>&1 | tee import_errors/states.log

echo ""
echo "[2/15] Importing municipalities..."
python import_modular.py --table municipalities 2>&1 | tee import_errors/municipalities.log

echo ""
echo "[3/15] Importing facility_types..."
python import_modular.py --table facility_types 2>&1 | tee import_errors/facility_types.log

echo ""
echo "[4/15] Importing deactivation_reasons..."
python import_modular.py --table deactivation_reasons 2>&1 | tee import_errors/deactivation_reasons.log

echo ""
echo "[5/15] Importing service_specialties..."
python import_modular.py --table service_specialties 2>&1 | tee import_errors/service_specialties.log

echo ""
echo "[6/15] Importing equipment_catalog..."
python import_modular.py --table equipment_catalog 2>&1 | tee import_errors/equipment_catalog.log

echo ""
echo "[7/15] Importing professional_councils..."
python import_modular.py --table professional_councils 2>&1 | tee import_errors/professional_councils.log

echo ""
echo "[8/15] Importing equipment_categories..."
python import_modular.py --table equipment_categories 2>&1 | tee import_errors/equipment_categories.log

echo ""
echo "[9/15] Importing service_classifications..."
python import_modular.py --table service_classifications 2>&1 | tee import_errors/service_classifications.log

echo ""
echo "=========================================="
echo "Step 3: Importing Large Tables..."
echo "=========================================="

echo ""
echo "[10/15] Importing facilities (~2-3 minutes)..."
python import_modular.py --table facilities 2>&1 | tee import_errors/facilities.log

echo ""
echo "[11/15] Importing professionals (~7-10 minutes)..."
python import_modular.py --table professionals 2>&1 | tee import_errors/professionals.log

echo ""
echo "[12/15] Importing facility_professionals (~10-15 minutes)..."
python import_modular.py --table facility_professionals 2>&1 | tee import_errors/facility_professionals.log

echo ""
echo "[13/15] Importing facility_services (~5-8 minutes)..."
python import_modular.py --table facility_services 2>&1 | tee import_errors/facility_services.log

echo ""
echo "[14/15] Importing facility_equipment (~3-5 minutes)..."
python import_modular.py --table facility_equipment 2>&1 | tee import_errors/facility_equipment.log

echo ""
echo "[15/15] Importing professional_workload (~8-12 minutes)..."
python import_modular.py --table professional_workload 2>&1 | tee import_errors/professional_workload.log

echo ""
echo "=========================================="
echo "Step 4: Post-Import Validation"
echo "=========================================="

echo ""
echo "Checking record counts..."
psql postgresql://user:password@localhost:5432/atlasmed_test << 'EOF'
SELECT 
    table_name,
    to_char(record_count, '999,999,999') as records
FROM (
    SELECT 'states' as table_name, COUNT(*) as record_count FROM cnes.states
    UNION ALL SELECT 'municipalities', COUNT(*) FROM cnes.municipalities
    UNION ALL SELECT 'facility_types', COUNT(*) FROM cnes.facility_types
    UNION ALL SELECT 'deactivation_reasons', COUNT(*) FROM cnes.deactivation_reasons
    UNION ALL SELECT 'service_specialties', COUNT(*) FROM cnes.service_specialties
    UNION ALL SELECT 'equipment_catalog', COUNT(*) FROM cnes.equipment_catalog
    UNION ALL SELECT 'professional_councils', COUNT(*) FROM cnes.professional_councils
    UNION ALL SELECT 'equipment_categories', COUNT(*) FROM cnes.equipment_categories
    UNION ALL SELECT 'service_classifications', COUNT(*) FROM cnes.service_classifications
    UNION ALL SELECT 'facilities', COUNT(*) FROM cnes.facilities
    UNION ALL SELECT 'professionals', COUNT(*) FROM cnes.professionals
    UNION ALL SELECT 'facility_professionals', COUNT(*) FROM cnes.facility_professionals
    UNION ALL SELECT 'facility_services', COUNT(*) FROM cnes.facility_services
    UNION ALL SELECT 'facility_equipment', COUNT(*) FROM cnes.facility_equipment
    UNION ALL SELECT 'professional_workload', COUNT(*) FROM cnes.professional_workload
) counts
ORDER BY table_name;
EOF

echo ""
echo "Checking for errors..."
echo "Error logs with issues:"
find import_errors -name "*.log" -type f ! -size 0 -exec bash -c 'echo "  - $1 ($(wc -l < "$1") lines)"' _ {} \;

echo ""
echo "=========================================="
echo "Import Complete!"
echo "=========================================="
echo ""
echo "End time: $(date)"
echo ""
echo "Check import_errors/ directory for any error details"
