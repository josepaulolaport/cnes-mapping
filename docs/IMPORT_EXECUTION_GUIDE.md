# CNES Data Import - Execution Guide

## Quick Start

### Option 1: Run Everything Automatically (Recommended)
```bash
./run_import.sh
```
This script will:
- Create the `import_errors/` directory
- Recreate the database schema
- Import all 15 tables in the correct order
- Log all errors to individual files
- Display a summary at the end

Estimated time: **45-60 minutes**

---

### Option 2: Run Tables Individually

First, prepare the environment:
```bash
# 1. Create error logs directory
mkdir -p import_errors

# 2. Enable required PostgreSQL extension
psql postgresql://user:password@localhost:5432/atlasmed_test -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# 3. Recreate the schema
psql postgresql://user:password@localhost:5432/atlasmed_test -f create_sales_app_schema.sql
```

Then run each table import:

#### Small Reference Tables (1-2 minutes total)
```bash
python import_modular.py --table states 2>&1 | tee import_errors/states.log
python import_modular.py --table municipalities 2>&1 | tee import_errors/municipalities.log
python import_modular.py --table facility_types 2>&1 | tee import_errors/facility_types.log
python import_modular.py --table deactivation_reasons 2>&1 | tee import_errors/deactivation_reasons.log
python import_modular.py --table service_specialties 2>&1 | tee import_errors/service_specialties.log
python import_modular.py --table equipment_catalog 2>&1 | tee import_errors/equipment_catalog.log
python import_modular.py --table professional_councils 2>&1 | tee import_errors/professional_councils.log
python import_modular.py --table equipment_categories 2>&1 | tee import_errors/equipment_categories.log
python import_modular.py --table service_classifications 2>&1 | tee import_errors/service_classifications.log
```

#### Large Tables (40-60 minutes total)
```bash
python import_modular.py --table facilities 2>&1 | tee import_errors/facilities.log
python import_modular.py --table professionals 2>&1 | tee import_errors/professionals.log
python import_modular.py --table facility_professionals 2>&1 | tee import_errors/facility_professionals.log
python import_modular.py --table facility_services 2>&1 | tee import_errors/facility_services.log
python import_modular.py --table facility_equipment 2>&1 | tee import_errors/facility_equipment.log
python import_modular.py --table professional_workload 2>&1 | tee import_errors/professional_workload.log
```

---

## Error Handling

The import process is **fault-tolerant**:
- If a batch fails, it tries importing row-by-row
- Failed records are logged to `import_errors/TABLE_NAME.log`
- The import continues even with errors
- You can retry specific tables without re-importing everything

### Checking for Errors

```bash
# List error logs that have content
find import_errors -name "*.log" -type f ! -size 0

# View a specific error log
cat import_errors/facilities.log

# Count errors in a log
grep -c "Error:" import_errors/facilities.log
```

---

## Validation

### Check Record Counts
```bash
psql postgresql://user:password@localhost:5432/atlasmed_test -c "
SELECT 
    table_name,
    to_char(record_count, '999,999,999') as records
FROM (
    SELECT 'states' as table_name, COUNT(*) as record_count FROM states
    UNION ALL SELECT 'municipalities', COUNT(*) FROM municipalities
    UNION ALL SELECT 'facility_types', COUNT(*) FROM facility_types
    UNION ALL SELECT 'deactivation_reasons', COUNT(*) FROM deactivation_reasons
    UNION ALL SELECT 'service_specialties', COUNT(*) FROM service_specialties
    UNION ALL SELECT 'equipment_catalog', COUNT(*) FROM equipment_catalog
    UNION ALL SELECT 'professional_councils', COUNT(*) FROM professional_councils
    UNION ALL SELECT 'equipment_categories', COUNT(*) FROM equipment_categories
    UNION ALL SELECT 'service_classifications', COUNT(*) FROM service_classifications
    UNION ALL SELECT 'facilities', COUNT(*) FROM facilities
    UNION ALL SELECT 'professionals', COUNT(*) FROM professionals
    UNION ALL SELECT 'facility_professionals', COUNT(*) FROM facility_professionals
    UNION ALL SELECT 'facility_services', COUNT(*) FROM facility_services
    UNION ALL SELECT 'facility_equipment', COUNT(*) FROM facility_equipment
    UNION ALL SELECT 'professional_workload', COUNT(*) FROM professional_workload
) counts
ORDER BY table_name;
"
```

### Expected Record Counts
- **states**: ~27
- **municipalities**: ~5,600
- **facility_types**: ~100
- **deactivation_reasons**: ~20
- **service_specialties**: ~150
- **equipment_catalog**: ~300
- **professional_councils**: ~15
- **equipment_categories**: ~40
- **service_classifications**: ~460
- **facilities**: ~623,000
- **professionals**: ~7,761,000
- **facility_professionals**: ~10,000,000+
- **facility_services**: ~2,000,000+
- **facility_equipment**: ~1,000,000+
- **professional_workload**: ~5,000,000+

---

## Troubleshooting

### Problem: Table import fails completely
**Solution:**
```bash
# Check the error log
cat import_errors/TABLE_NAME.log

# Try re-importing with --force
python import_modular.py --table TABLE_NAME --force 2>&1 | tee import_errors/TABLE_NAME_retry.log
```

### Problem: Import is too slow
**Cause:** Database may need tuning for bulk inserts

**Solutions:**
1. Temporarily disable constraints during import
2. Increase PostgreSQL `work_mem` and `maintenance_work_mem`
3. Consider using `COPY` instead of `INSERT` for very large tables

### Problem: Foreign key violations
**Solution:** Tables must be imported in order. Use the `run_import.sh` script which imports in correct dependency order.

### Problem: Duplicate key violations
**Solution:** The script now automatically deduplicates data before import. If you still see errors, check the error log for specific issues.

---

## Import Order (Dependency-Based)

1. **states** (no dependencies)
2. **municipalities** (depends on: states)
3. **facility_types** (no dependencies)
4. **deactivation_reasons** (no dependencies)
5. **service_specialties** (no dependencies)
6. **equipment_catalog** (no dependencies)
7. **professional_councils** (no dependencies)
8. **equipment_categories** (no dependencies)
9. **service_classifications** (depends on: service_specialties)
10. **facilities** (depends on: states, municipalities, facility_types, deactivation_reasons, facility_owners)
11. **professionals** (no dependencies)
12. **facility_professionals** (depends on: facilities, professionals)
13. **facility_services** (depends on: facilities)
14. **facility_equipment** (depends on: facilities, equipment_catalog, equipment_categories)
15. **professional_workload** (depends on: facilities, professionals, professional_councils)

---

## Files Created

### Import Scripts
- `run_import.sh` - Automated full import script
- `import_modular.py` - Modular Python import script

### Documentation
- `IMPORT_PLAN.md` - Detailed execution plan
- `IMPORT_EXECUTION_GUIDE.md` - This file
- `IMPORT_ERRORS_README.md` - Error handling documentation

### Logs
- `import_errors/*.log` - Individual table error logs
- `import_modular.log` - General import log

---

## Performance Tips

### During Import:
- Close other database connections
- Don't run queries against the database during import
- Monitor disk space (imports require ~10-15 GB)

### After Import:
```bash
# Analyze tables for query optimization
psql postgresql://user:password@localhost:5432/atlasmed_test -c "ANALYZE;"

# Vacuum to reclaim space
psql postgresql://user:password@localhost:5432/atlasmed_test -c "VACUUM ANALYZE;"
```

---

## Next Steps After Import

1. **Verify Data Integrity**
   - Check record counts match expectations
   - Spot-check some records for data quality

2. **Run Sample Queries**
   ```bash
   psql postgresql://user:password@localhost:5432/atlasmed_test -f sample_queries.sql
   ```

3. **Set Up Application**
   - Update connection strings
   - Run your application tests
   - Create additional indexes if needed

4. **Create Backup**
   ```bash
   pg_dump postgresql://user:password@localhost:5432/atlasmed_test > atlasmed_backup.sql
   ```

---

## Support

For issues or questions:
1. Check the error logs in `import_errors/`
2. Review the detailed plan in `IMPORT_PLAN.md`
3. Consult `SCHEMA_RENAMING_GUIDE.md` for schema details
