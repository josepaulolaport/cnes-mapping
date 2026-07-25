# CNES Import - Ready to Run

## ✅ All tables in CNES schema

All data tables are now properly created in the `cnes` schema for better organization!

## Issues Fixed ✅

The PostgreSQL `pg_trgm` extension has been enabled, and the schema now creates successfully without errors.

## What Was Fixed

1. **Extension enabled**: `pg_trgm` extension is now active in your database
2. **CNES schema**: All tables now create in `cnes` schema (not `public`)
3. **Import script updated**: Python script targets `cnes.TABLE_NAME`  
4. **Scripts updated**: `run_import.sh` ensures everything uses the correct schema

## You're Ready to Import!

### Quick Start (Recommended)

```bash
cd /Users/josepaulolaport/Documents/projects/cnes_mapping
./run_import.sh
```

This will automatically:
- Create `import_errors/` directory
- Enable the `pg_trgm` extension (if not already enabled)
- Drop and recreate all tables
- Import all 15 tables in the correct order
- Log any errors to individual files
- Show you a summary at the end

**Estimated time**: 45-60 minutes

### Manual Import (If You Prefer Control)

```bash
# 1. Prepare
mkdir -p import_errors
psql postgresql://user:password@localhost:5432/atlasmed_test -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql postgresql://user:password@localhost:5432/atlasmed_test -f create_sales_app_schema.sql

# 2. Import reference tables (fast)
python import_modular.py --table states 2>&1 | tee import_errors/states.log
python import_modular.py --table municipalities 2>&1 | tee import_errors/municipalities.log
python import_modular.py --table facility_types 2>&1 | tee import_errors/facility_types.log
python import_modular.py --table deactivation_reasons 2>&1 | tee import_errors/deactivation_reasons.log
python import_modular.py --table service_specialties 2>&1 | tee import_errors/service_specialties.log
python import_modular.py --table equipment_catalog 2>&1 | tee import_errors/equipment_catalog.log
python import_modular.py --table professional_councils 2>&1 | tee import_errors/professional_councils.log
python import_modular.py --table equipment_categories 2>&1 | tee import_errors/equipment_categories.log
python import_modular.py --table service_classifications 2>&1 | tee import_errors/service_classifications.log

# 3. Import large tables (slower - can take 5-15 min each)
python import_modular.py --table facilities 2>&1 | tee import_errors/facilities.log
python import_modular.py --table professionals 2>&1 | tee import_errors/professionals.log
python import_modular.py --table facility_professionals 2>&1 | tee import_errors/facility_professionals.log
python import_modular.py --table facility_services 2>&1 | tee import_errors/facility_services.log
python import_modular.py --table facility_equipment 2>&1 | tee import_errors/facility_equipment.log
python import_modular.py --table professional_workload 2>&1 | tee import_errors/professional_workload.log
```

## What to Expect

### Progress Indicators
- Each table shows a progress bar with `it/s` (iterations per second)
- Larger tables use batch processing (10,000 records per batch)
- You'll see messages like:
  - `✓ Read tbEstado202605.csv: 27 rows, 3 columns`
  - `✅ Imported 27 states`

### Error Handling
- If errors occur, they're logged to `import_errors/TABLE_NAME.log`
- The script continues importing other records
- Failed records don't stop the entire import

### Time Estimates by Table
- **states**: < 1 second
- **municipalities**: < 5 seconds
- **facility_types**: < 1 second
- **deactivation_reasons**: < 1 second
- **service_specialties**: < 1 second
- **equipment_catalog**: < 2 seconds
- **professional_councils**: < 1 second
- **equipment_categories**: < 1 second
- **service_classifications**: < 2 seconds
- **facilities**: 2-3 minutes (623K records)
- **professionals**: 7-10 minutes (7.7M records)
- **facility_professionals**: 10-15 minutes (10M+ records)
- **facility_services**: 5-8 minutes (2M+ records)
- **facility_equipment**: 3-5 minutes (1M+ records)
- **professional_workload**: 8-12 minutes (5M+ records)

## After Import

### Check Results
```bash
# View record counts
psql postgresql://user:password@localhost:5432/atlasmed_test -c "
SELECT table_name, to_char(COUNT(*), '999,999,999') as records 
FROM (
    SELECT 'facilities' as table_name FROM facilities
    UNION ALL SELECT 'professionals' FROM professionals
    UNION ALL SELECT 'facility_professionals' FROM facility_professionals
) t 
GROUP BY table_name;
"

# Check for errors
find import_errors -name "*.log" -type f ! -size 0
```

### Run Sample Queries
```bash
# Example: Find orthopedic facilities in Rio de Janeiro
psql postgresql://user:password@localhost:5432/atlasmed_test -c "
SELECT 
    f.facility_id,
    f.trade_name,
    m.municipality_name
FROM cnes.facilities f
JOIN cnes.municipalities m ON f.municipality_id = m.municipality_id
WHERE m.state_code = 'RJ'
  AND f.deactivation_reason_code IS NULL
LIMIT 10;
"
```

## Documentation

- **IMPORT_EXECUTION_GUIDE.md** - Detailed execution guide with troubleshooting
- **IMPORT_PLAN.md** - Comprehensive import plan with all details
- **SCHEMA_RENAMING_GUIDE.md** - Schema documentation
- **sample_queries.sql** - 30 ready-to-use queries

## Need Help?

1. **Schema errors**: Make sure `pg_trgm` extension is enabled
2. **Permission errors**: Check PostgreSQL user has CREATE privileges
3. **Disk space**: Import needs ~10-15 GB free space
4. **Import errors**: Check `import_errors/*.log` files

---

**Ready to start?** Run: `./run_import.sh`
