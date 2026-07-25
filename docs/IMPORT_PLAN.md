# CNES Data Import Execution Plan

## Overview
This plan provides step-by-step commands to recreate the database schema and import all CNES data tables in the correct order.

## Preparation

### 1. Create Error Logs Directory
```bash
mkdir -p import_errors
```

### 2. Recreate Database Schema
```bash
# Drop and recreate all tables
psql postgresql://user:password@localhost:5432/atlasmed_test -f create_sales_app_schema.sql
```

## Data Import Commands

Run each command in sequence. Each will log errors to `import_errors/TABLE_NAME.log` without stopping the import.

### Phase 1: Reference Data (Small Tables)

```bash
# 1. States (27 records)
python import_modular.py --table states 2>&1 | tee import_errors/states.log

# 2. Municipalities (~5,600 records)
python import_modular.py --table municipalities 2>&1 | tee import_errors/municipalities.log

# 3. Facility Types (~100 records)
python import_modular.py --table facility_types 2>&1 | tee import_errors/facility_types.log

# 4. Deactivation Reasons (~20 records)
python import_modular.py --table deactivation_reasons 2>&1 | tee import_errors/deactivation_reasons.log

# 5. Service Specialties (~150 records)
python import_modular.py --table service_specialties 2>&1 | tee import_errors/service_specialties.log

# 6. Equipment Catalog (~300 records)
python import_modular.py --table equipment_catalog 2>&1 | tee import_errors/equipment_catalog.log

# 7. Professional Councils (~15 records)
python import_modular.py --table professional_councils 2>&1 | tee import_errors/professional_councils.log

# 8. Equipment Categories (~40 records)
python import_modular.py --table equipment_categories 2>&1 | tee import_errors/equipment_categories.log

# 9. Service Classifications (~460 records)
python import_modular.py --table service_classifications 2>&1 | tee import_errors/service_classifications.log
```

### Phase 2: Large Tables (Time estimates included)

```bash
# 10. Facilities (~623,000 records - ~2-3 minutes)
python import_modular.py --table facilities 2>&1 | tee import_errors/facilities.log

# 11. Professionals (~7.7M records - ~7-10 minutes)
python import_modular.py --table professionals 2>&1 | tee import_errors/professionals.log

# 12. Facility-Professional Relationships (~10M+ records - ~10-15 minutes)
python import_modular.py --table facility_professionals 2>&1 | tee import_errors/facility_professionals.log

# 13. Facility Services (~2M+ records - ~5-8 minutes)
python import_modular.py --table facility_services 2>&1 | tee import_errors/facility_services.log

# 14. Facility Equipment (~1M+ records - ~3-5 minutes)
python import_modular.py --table facility_equipment 2>&1 | tee import_errors/facility_equipment.log

# 15. Professional Workload (~5M+ records - ~8-12 minutes)
python import_modular.py --table professional_workload 2>&1 | tee import_errors/professional_workload.log
```

## Alternative: Import All at Once

```bash
# Import all tables in correct order (Est. 45-60 minutes total)
python import_modular.py --table all 2>&1 | tee import_errors/full_import.log
```

## Post-Import Validation

### Check Import Status
```bash
# Count records in each table
psql postgresql://user:password@localhost:5432/atlasmed_test << 'EOF'
SELECT 
    'states' as table_name, 
    COUNT(*) as record_count 
FROM states
UNION ALL
SELECT 'municipalities', COUNT(*) FROM municipalities
UNION ALL
SELECT 'facility_types', COUNT(*) FROM facility_types
UNION ALL
SELECT 'deactivation_reasons', COUNT(*) FROM deactivation_reasons
UNION ALL
SELECT 'service_specialties', COUNT(*) FROM service_specialties
UNION ALL
SELECT 'equipment_catalog', COUNT(*) FROM equipment_catalog
UNION ALL
SELECT 'professional_councils', COUNT(*) FROM professional_councils
UNION ALL
SELECT 'equipment_categories', COUNT(*) FROM equipment_categories
UNION ALL
SELECT 'service_classifications', COUNT(*) FROM service_classifications
UNION ALL
SELECT 'facilities', COUNT(*) FROM facilities
UNION ALL
SELECT 'professionals', COUNT(*) FROM professionals
UNION ALL
SELECT 'facility_professionals', COUNT(*) FROM facility_professionals
UNION ALL
SELECT 'facility_services', COUNT(*) FROM facility_services
UNION ALL
SELECT 'facility_equipment', COUNT(*) FROM facility_equipment
UNION ALL
SELECT 'professional_workload', COUNT(*) FROM professional_workload
ORDER BY table_name;
EOF
```

### Check for Errors
```bash
# List all error logs with non-zero size
find import_errors -name "*.log" -type f -size +0 -exec ls -lh {} \;

# View specific error log
# Example: cat import_errors/facilities.log
```

### Recreate Views (if needed)
```bash
# Recreate the views that were dropped earlier
psql postgresql://user:password@localhost:5432/atlasmed_test << 'EOF'
-- Active facilities view
CREATE OR REPLACE VIEW active_facilities AS
SELECT 
    f.*,
    ft.type_name as facility_type_name,
    m.municipality_name,
    m.state_code
FROM facilities f
LEFT JOIN facility_types ft ON f.facility_type_code = ft.type_code
LEFT JOIN municipalities m ON f.municipality_id = m.municipality_id
WHERE f.deactivation_reason_code IS NULL;

-- Facility equipment in use view
CREATE OR REPLACE VIEW facility_equipment_in_use AS
SELECT 
    fe.*,
    ec.equipment_name,
    cat.category_name as equipment_category_name,
    f.trade_name as facility_name
FROM facility_equipment fe
JOIN equipment_catalog ec ON fe.equipment_code = ec.equipment_code
JOIN equipment_categories cat ON fe.equipment_category_code = cat.category_code
JOIN facilities f ON fe.facility_id = f.facility_id
WHERE fe.operational_status = '1';  -- Only operational equipment
EOF
```

## Troubleshooting

### If a specific table import fails completely:

1. Check the error log:
   ```bash
   cat import_errors/TABLE_NAME.log
   ```

2. Re-import that specific table with --force:
   ```bash
   python import_modular.py --table TABLE_NAME --force 2>&1 | tee import_errors/TABLE_NAME_retry.log
   ```

### If you need to restart from a specific point:

The commands are idempotent (except for already-populated tables). To re-import:
```bash
python import_modular.py --table TABLE_NAME --force
```

## Estimated Total Time

- **Phase 1 (Reference Data)**: ~1-2 minutes
- **Phase 2 (Large Tables)**: ~40-60 minutes
- **Total**: ~45-65 minutes

## Success Criteria

After import completion:
- All 15 tables should have data
- Error logs should be empty or contain only warnings
- Record counts should match expectations (~7.7M professionals, ~623K facilities, etc.)
