# Schema Migration Checklist

> Step-by-step guide to migrate from CNES schema to Sales App schema

## 🎯 Overview

This checklist will guide you through transforming your database from the cryptic CNES schema to the clear, modern Sales App schema. Follow these steps in order.

---

## Phase 1: Preparation ✅

### 1.1 Review Documentation
- [ ] Read `SCHEMA_RENAMING_README.md` (overview)
- [ ] Review `SCHEMA_QUICK_REF.md` (quick reference)
- [ ] Skim `SCHEMA_RENAMING_GUIDE.md` (detailed guide)
- [ ] Review `SCHEMA_BEFORE_AFTER.md` (see the improvements)

**Estimated time:** 1 hour

### 1.2 Setup Tools
- [ ] Copy `schema_mapping.json` to your project
- [ ] Copy `schema_mapper.py` to your project
- [ ] Install required Python packages:
  ```bash
  pip install pandas
  ```
- [ ] Test the schema mapper:
  ```bash
  python schema_mapper.py
  ```

**Estimated time:** 15 minutes

### 1.3 Backup Data
- [ ] Backup all CNES CSV files
- [ ] Backup current database (if exists)
- [ ] Verify backups are complete
- [ ] Document current data volume

**Estimated time:** 30 minutes

---

## Phase 2: Database Design 🗂️

### 2.1 Create New Database
- [ ] Create new database (e.g., `sales_app_db`)
- [ ] Set up database user/permissions
- [ ] Configure connection strings
- [ ] Test database connectivity

**Estimated time:** 30 minutes

### 2.2 Create Tables - Core Entities
Create these tables first (most important):

- [ ] **facilities** (from `tbEstabelecimento202605`)
  ```sql
  CREATE TABLE facilities (
      facility_id VARCHAR(20) PRIMARY KEY,
      cnes_code VARCHAR(20),
      legal_name VARCHAR(200),
      trade_name VARCHAR(200),
      -- ... see SCHEMA_RENAMING_GUIDE.md for full DDL
  );
  ```

- [ ] **professionals** (from `tbDadosProfissionalSus202605`)
  ```sql
  CREATE TABLE professionals (
      professional_id VARCHAR(20) PRIMARY KEY,
      full_name VARCHAR(200),
      -- ... see guide
  );
  ```

- [ ] **municipalities** (from `tbMunicipio202605`)
- [ ] **states** (from `tbEstado202605`)
- [ ] **reference_data** (consolidated lookup table)

**Estimated time:** 2 hours

### 2.3 Create Tables - Relationships
- [ ] **facility_professionals** (from `rlEstabEquipeProf202605`)
- [ ] **facility_services** (from `rlEstabServClass202605`)
- [ ] **facility_equipment** (from `rlEstabEquipamento202605`)

**Estimated time:** 1 hour

### 2.4 Create Tables - Supporting
- [ ] **professional_workload** (from `tbCargaHorariaSus202605`)
- [ ] **service_classifications** (from `tbClassificacaoServico202605`)

**Estimated time:** 30 minutes

### 2.5 Create Indexes
- [ ] Primary key indexes (auto-created)
- [ ] Foreign key indexes:
  - [ ] `facilities.municipality_id`
  - [ ] `facilities.facility_type_code`
  - [ ] `facilities.deactivation_reason_code`
  - [ ] `facility_professionals.facility_id`
  - [ ] `facility_professionals.professional_id`
  - [ ] `municipalities.state_code`
- [ ] Status field indexes:
  - [ ] `facilities.deactivation_reason_code` (for filtering active)
  - [ ] `facility_professionals.termination_date` (for filtering active)
  - [ ] `facility_services.is_active`

**Estimated time:** 30 minutes

---

## Phase 3: Data Migration 📦

### 3.1 Setup ETL Scripts

Create Python ETL script using `schema_mapper.py`:

```python
from schema_mapper import CNESSchemaMapper
import pandas as pd

mapper = CNESSchemaMapper('schema_mapping.json')

def migrate_table(csv_file, table_name):
    """Migrate a single table"""
    # Read CSV
    df = pd.read_csv(csv_file, encoding='latin1', delimiter=';')
    
    # Transform column names
    df_new = mapper.rename_dataframe_columns(df, csv_file)
    
    # Load to database (customize for your DB)
    df_new.to_sql(table_name, engine, if_exists='append', index=False)
    
    print(f"✅ Migrated {table_name}: {len(df_new)} rows")
```

- [ ] Create `migrate.py` script
- [ ] Test on small sample first
- [ ] Add error handling
- [ ] Add progress logging

**Estimated time:** 2 hours

### 3.2 Migrate Lookup Tables First
Small tables without dependencies:

- [ ] **states** (27 rows)
  ```python
  migrate_table('tbEstado202605.csv', 'states')
  ```
- [ ] **municipalities** (5,607 rows)
- [ ] **reference_data** (consolidated from multiple small tables)
  - [ ] Facility types
  - [ ] Deactivation reasons
  - [ ] Service specialties
  - [ ] Equipment catalog
  - [ ] Professional councils
  - [ ] Equipment categories

**Estimated time:** 1 hour

### 3.3 Migrate Core Entities
Large main tables:

- [ ] **facilities** (~620K rows)
  - Verify: `SELECT COUNT(*) FROM facilities`
  - Spot check: Review 10 random records
  - Active count: `SELECT COUNT(*) FROM facilities WHERE deactivation_reason_code IS NULL`

- [ ] **professionals** (~7.7M rows - this will take time!)
  - Use batching (100K rows at a time)
  - Monitor progress
  - Verify counts match source

**Estimated time:** 4-6 hours (mostly waiting for large import)

### 3.4 Migrate Relationship Tables
Tables linking entities:

- [ ] **facility_professionals** (~870K rows)
  - Verify foreign keys exist
  - Check for orphaned records
  - Validate active vs terminated

- [ ] **facility_services** (~1.4M rows)
- [ ] **facility_equipment** (~1.3M rows)

**Estimated time:** 3-4 hours

### 3.5 Migrate Supporting Tables
- [ ] **professional_workload** (~1.2M rows)
- [ ] **service_classifications** (varies)

**Estimated time:** 2 hours

---

## Phase 4: Data Validation ✔️

### 4.1 Row Count Validation
Compare row counts between source CSVs and new tables:

```sql
-- Example
SELECT 
    'facilities' as table_name,
    COUNT(*) as row_count,
    MIN(last_updated_date) as oldest_record,
    MAX(last_updated_date) as newest_record
FROM facilities;
```

- [ ] All tables have expected row counts
- [ ] No missing data
- [ ] Date ranges look correct

**Estimated time:** 30 minutes

### 4.2 Relationship Validation
Check foreign key integrity:

```sql
-- Check for orphaned facility_professionals
SELECT COUNT(*) 
FROM facility_professionals fp
WHERE NOT EXISTS (
    SELECT 1 FROM facilities f 
    WHERE f.facility_id = fp.facility_id
);
-- Should return 0 (or document expected orphans)
```

- [ ] No unexpected orphaned records
- [ ] Foreign keys are valid
- [ ] Self-references work correctly

**Estimated time:** 1 hour

### 4.3 Business Logic Validation
Test critical queries:

```sql
-- Test 1: Active facilities in São Paulo
SELECT COUNT(*) 
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
WHERE f.deactivation_reason_code IS NULL
    AND s.state_name = 'SÃO PAULO';

-- Test 2: Currently employed doctors
SELECT COUNT(*) 
FROM facility_professionals
WHERE termination_date IS NULL;

-- Test 3: Facilities with MRI equipment
SELECT COUNT(DISTINCT f.facility_id)
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data rd ON rd.code = fe.equipment_code 
    AND rd.reference_type = 'equipment_catalog'
WHERE rd.description LIKE '%RESSONANCIA%'
    AND f.deactivation_reason_code IS NULL;
```

- [ ] Query results match expectations
- [ ] Active/deactivated filtering works
- [ ] Join performance is acceptable
- [ ] Complex queries return correct data

**Estimated time:** 2 hours

### 4.4 Sample Data Review
- [ ] Manually review 20 random facilities
- [ ] Check all fields are populated correctly
- [ ] Verify data types (booleans, dates, numbers)
- [ ] Test geolocation data (lat/long)
- [ ] Validate contact information

**Estimated time:** 1 hour

---

## Phase 5: Application Integration 🔌

### 5.1 Update Connection Strings
- [ ] Point application to new database
- [ ] Update connection pooling settings
- [ ] Test database connectivity from app
- [ ] Configure read-only connections if needed

**Estimated time:** 30 minutes

### 5.2 Update Data Access Layer
- [ ] Update all SQL queries to use new schema
- [ ] Replace old table names with new names
- [ ] Replace old column names with new names
- [ ] Use `SCHEMA_QUICK_REF.md` for quick lookups
- [ ] Test each query individually

**Example changes:**
```python
# Before
query = "SELECT CO_UNIDADE, NO_FANTASIA FROM tbEstabelecimento202605"

# After
query = "SELECT facility_id, trade_name FROM facilities"
```

**Estimated time:** 1-2 days (depends on codebase size)

### 5.3 Update ORM Models (if using ORM)
If using SQLAlchemy, Django ORM, etc.:

```python
# Before
class Estabelecimento(Base):
    __tablename__ = 'tbEstabelecimento202605'
    CO_UNIDADE = Column(String, primary_key=True)
    NO_FANTASIA = Column(String)

# After
class Facility(Base):
    __tablename__ = 'facilities'
    facility_id = Column(String, primary_key=True)
    trade_name = Column(String)
```

- [ ] Update all model classes
- [ ] Update field names
- [ ] Update relationships
- [ ] Run ORM tests

**Estimated time:** 1 day (if using ORM)

### 5.4 Update API Endpoints
- [ ] Update API response field names
- [ ] Update API documentation
- [ ] Version your API if needed (v1 vs v2)
- [ ] Test all endpoints

```json
// Before
{ "CO_UNIDADE": "123", "NO_FANTASIA": "Hospital A" }

// After
{ "facility_id": "123", "trade_name": "Hospital A" }
```

**Estimated time:** 1 day

---

## Phase 6: Testing 🧪

### 6.1 Unit Tests
- [ ] Write tests for new schema queries
- [ ] Test active/deactivated filtering
- [ ] Test foreign key relationships
- [ ] Test edge cases (null values, etc.)

**Estimated time:** 1-2 days

### 6.2 Integration Tests
- [ ] Test full user workflows
- [ ] Test search functionality
- [ ] Test filtering and sorting
- [ ] Test pagination

**Estimated time:** 1 day

### 6.3 Performance Tests
- [ ] Benchmark common queries
- [ ] Test with large result sets
- [ ] Verify index usage
- [ ] Optimize slow queries

```sql
-- Check if indexes are being used
EXPLAIN ANALYZE
SELECT * FROM facilities 
WHERE deactivation_reason_code IS NULL;
```

**Estimated time:** 1 day

### 6.4 User Acceptance Testing
- [ ] Have business users test the app
- [ ] Verify data accuracy
- [ ] Check report outputs
- [ ] Validate calculations

**Estimated time:** 2-3 days

---

## Phase 7: Documentation 📚

### 7.1 Update Technical Documentation
- [ ] Database schema diagram
- [ ] Table relationship diagram
- [ ] Data dictionary (use `schema_mapping.json`)
- [ ] ETL process documentation

**Estimated time:** 1 day

### 7.2 Update Developer Documentation
- [ ] Code examples with new schema
- [ ] Common query patterns
- [ ] API documentation
- [ ] Keep `SCHEMA_QUICK_REF.md` accessible

**Estimated time:** 4 hours

### 7.3 Update User Documentation
- [ ] Update user guides
- [ ] Update training materials
- [ ] Create FAQ for schema changes
- [ ] Record video tutorials (if needed)

**Estimated time:** 1 day

---

## Phase 8: Deployment 🚀

### 8.1 Staging Environment
- [ ] Deploy to staging
- [ ] Run full test suite
- [ ] Performance test with production data volume
- [ ] Security audit
- [ ] Backup staging database

**Estimated time:** 2-3 days

### 8.2 Production Deployment Plan
- [ ] Schedule deployment window
- [ ] Prepare rollback plan
- [ ] Notify stakeholders
- [ ] Document deployment steps
- [ ] Prepare monitoring/alerts

**Estimated time:** 1 day (planning)

### 8.3 Production Deployment
- [ ] Backup production database
- [ ] Run migration scripts
- [ ] Validate data
- [ ] Deploy application updates
- [ ] Monitor for errors
- [ ] Test critical workflows

**Estimated time:** 4-6 hours (depends on data volume)

### 8.4 Post-Deployment
- [ ] Monitor application logs
- [ ] Monitor database performance
- [ ] Check error rates
- [ ] Verify scheduled jobs run correctly
- [ ] Collect user feedback

**Estimated time:** 1 week (ongoing monitoring)

---

## Phase 9: Maintenance 🔧

### 9.1 Monthly CNES Updates
When new CNES data is released:

- [ ] Download new CSV files (e.g., `tbEstabelecimento202607.csv`)
- [ ] Run same ETL scripts (update file references)
- [ ] Compare row counts
- [ ] Check for schema changes in CNES files
- [ ] Update `schema_mapping.json` if needed

**Estimated time:** 2-4 hours per month

### 9.2 Performance Monitoring
- [ ] Monitor query performance
- [ ] Optimize slow queries
- [ ] Review and add indexes as needed
- [ ] Archiving strategy for old data

**Estimated time:** Ongoing

---

## Timeline Summary ⏱️

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| 1. Preparation | 2 hours | None |
| 2. Database Design | 4 hours | Phase 1 |
| 3. Data Migration | 10-15 hours | Phase 2 |
| 4. Validation | 4.5 hours | Phase 3 |
| 5. Application Integration | 3-5 days | Phase 4 |
| 6. Testing | 4-6 days | Phase 5 |
| 7. Documentation | 2-3 days | Phase 6 |
| 8. Deployment | 1 week | Phase 7 |
| **Total** | **~3-4 weeks** | - |

*Note: Timeline assumes 1-2 developers working full-time*

---

## Risk Mitigation 🛡️

### High Risk Items
1. **Large data migration (7.7M professionals)**
   - Mitigation: Use batching, monitor progress, have rollback plan
   
2. **Application breaks after schema change**
   - Mitigation: Comprehensive testing, gradual rollout, feature flags
   
3. **Performance degradation**
   - Mitigation: Index properly, benchmark queries, load testing

4. **Data loss during migration**
   - Mitigation: Multiple backups, validation scripts, dry runs

### Rollback Plan
If issues occur:
1. Stop application
2. Restore database backup
3. Revert application to old version
4. Investigate issues
5. Fix and retry

---

## Success Criteria ✅

Migration is successful when:
- [ ] All data migrated correctly (verified row counts)
- [ ] No data loss or corruption
- [ ] All foreign keys validated
- [ ] Application works with new schema
- [ ] Query performance is acceptable
- [ ] Tests pass (unit, integration, UAT)
- [ ] Documentation updated
- [ ] Team trained on new schema
- [ ] Production running smoothly for 1 week

---

## Support & Resources 📞

### Documentation Files
- `SCHEMA_RENAMING_README.md` - Main overview
- `SCHEMA_RENAMING_GUIDE.md` - Detailed guide
- `SCHEMA_QUICK_REF.md` - Quick reference
- `SCHEMA_BEFORE_AFTER.md` - Visual comparisons
- `schema_mapping.json` - Machine-readable mapping
- `schema_mapper.py` - Python ETL helper

### Quick Help
```python
# Quick column lookup
from schema_mapper import quick_lookup
quick_lookup('tbEstabelecimento202605.csv', 'NO_FANTASIA')
```

---

## Notes 📝

### Important Reminders
- Always backup before major operations
- Test on sample data first
- Monitor long-running operations
- Keep stakeholders informed
- Document any issues encountered
- Celebrate when done! 🎉

### Lessons Learned
(Fill this in as you go through the migration)

- [ ] What went well?
- [ ] What took longer than expected?
- [ ] What would you do differently?
- [ ] Tips for next migration?

---

**Good luck with your migration!** 🚀

Remember: This is a one-time effort that will pay dividends for years to come. Your future self (and your team) will thank you for having a clean, understandable schema!
