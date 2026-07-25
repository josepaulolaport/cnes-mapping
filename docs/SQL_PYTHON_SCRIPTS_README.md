# 🗄️ SQL & Python Scripts - Quick Start

Complete scripts to create and populate your Sales App database from CNES data.

## 📦 What's Included

### 1. **create_sales_app_schema.sql**
PostgreSQL DDL script that creates:
- 11 tables with clear English names
- Foreign key relationships
- Indexes for performance
- 3 helpful views
- 2 utility functions

**Features:**
- ✅ Modern naming (no Portuguese abbreviations)
- ✅ Proper data types (BOOLEAN, DATE, DECIMAL)
- ✅ Comprehensive comments/documentation
- ✅ Optimized indexes for sales queries
- ✅ Full-text search support

### 2. **import_cnes_data.py**
Python ETL script that:
- Reads CNES CSV files with automatic encoding detection
- Transforms column names to new schema
- Converts data types properly
- Imports ~13 million records
- Shows progress bars
- Handles errors gracefully

**Features:**
- ✅ Batch processing for large tables
- ✅ Respects foreign key dependencies
- ✅ Creates consolidated reference_data table
- ✅ Comprehensive logging
- ✅ Automatic validation

### 3. **setup_database.sh**
Automated setup script that:
- Creates database and user
- Runs SQL schema creation
- Executes data import
- Verifies results

**Features:**
- ✅ One-command setup
- ✅ Color-coded output
- ✅ Error checking at each step
- ✅ Interactive confirmations

---

## 🚀 Quick Start (3 Steps)

### Step 1: Prepare CSV Files
```bash
# Create directory and place CNES CSV files
mkdir csv_files
# Download from: ftp://ftp.datasus.gov.br/cnes/
# Place all .csv files in csv_files/
```

### Step 2: Run Automated Setup
```bash
# Make script executable (if not already)
chmod +x setup_database.sh

# Run setup (will prompt for confirmation)
./setup_database.sh
```

### Step 3: Connect Your App
```python
from sqlalchemy import create_engine

engine = create_engine(
    'postgresql://sales_app_user:your_password@localhost:5432/sales_app_db'
)

# Query active facilities
query = """
    SELECT facility_id, trade_name, phone_number
    FROM facilities
    WHERE deactivation_reason_code IS NULL
    LIMIT 10
"""
```

**That's it!** 🎉

---

## 📋 Manual Setup (Step-by-Step)

If you prefer manual control:

### 1. Install Dependencies
```bash
pip install pandas sqlalchemy psycopg2-binary python-dotenv tqdm
```

### 2. Create Database
```bash
psql -U postgres -c "CREATE DATABASE sales_app_db;"
psql -U postgres -c "CREATE USER sales_app_user WITH PASSWORD 'your_password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE sales_app_db TO sales_app_user;"
```

### 3. Create Schema
```bash
psql -U sales_app_user -d sales_app_db -f create_sales_app_schema.sql
```

### 4. Import Data
```bash
python import_cnes_data.py \
    --csv-dir ./csv_files \
    --db-url "postgresql://sales_app_user:your_password@localhost:5432/sales_app_db"
```

---

## 🎯 What Gets Created

### Tables (11)

| Table | Purpose | Rows (approx) |
|-------|---------|---------------|
| **facilities** | Health establishments | 620,000 |
| **professionals** | Healthcare workers | 7,700,000 |
| **facility_professionals** | Employment records | 870,000 |
| **facility_services** | Services offered | 1,400,000 |
| **facility_equipment** | Equipment inventory | 1,300,000 |
| **professional_workload** | Working hours/credentials | 1,200,000 |
| **municipalities** | Brazilian cities | 5,600 |
| **states** | Brazilian states | 27 |
| **reference_data** | Lookup codes (consolidated) | 2,000 |
| **service_classifications** | Service hierarchy | varies |
| **facility_owners** | Facility owners | varies |

### Views (3)

| View | Purpose |
|------|---------|
| **active_facilities** | Active facilities with location |
| **active_facility_professionals** | Currently employed professionals |
| **facility_equipment_in_use** | Equipment in operation |

### Functions (2)

| Function | Purpose |
|----------|---------|
| `is_facility_active(facility_id)` | Check if facility is active |
| `is_professional_active_at_facility(...)` | Check employment status |

---

## ⏱️ Expected Runtime

| Phase | Time |
|-------|------|
| Schema creation | < 1 minute |
| Small tables | 5 minutes |
| Facilities | 5 minutes |
| Professionals | **30 minutes** |
| Relationships | 15 minutes |
| Validation | 2 minutes |
| **TOTAL** | **~60 minutes** |

---

## 🔍 Verify Installation

```sql
-- Connect to database
psql -U sales_app_user -d sales_app_db

-- Check table counts
SELECT tablename, n_live_tup 
FROM pg_stat_user_tables 
ORDER BY n_live_tup DESC;

-- Test active facilities
SELECT COUNT(*) FROM facilities 
WHERE deactivation_reason_code IS NULL;

-- Test view
SELECT * FROM active_facilities LIMIT 5;
```

---

## 🎨 Schema Highlights

### Before (CNES):
```sql
SELECT CO_UNIDADE, NO_FANTASIA, NU_TELEFONE
FROM tbEstabelecimento202605
WHERE CO_MOTIVO_DESAB IS NULL;
```

### After (Sales App):
```sql
SELECT facility_id, trade_name, phone_number
FROM facilities
WHERE deactivation_reason_code IS NULL;
```

**Much clearer!** ✨

---

## 📊 Key Features

### 1. Active Status Tracking
```sql
-- Active facilities
WHERE deactivation_reason_code IS NULL

-- Active professionals
WHERE termination_date IS NULL
```

### 2. Geographic Queries
```sql
SELECT f.*, m.municipality_name, s.state_name
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
WHERE s.state_name = 'SÃO PAULO';
```

### 3. Equipment Inventory
```sql
SELECT f.trade_name, COUNT(*) as equipment_count
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
WHERE fe.quantity > 0
GROUP BY f.facility_id;
```

### 4. Professional Search
```sql
SELECT p.full_name, f.trade_name, fp.occupation_code
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN facilities f ON fp.facility_id = f.facility_id
WHERE fp.termination_date IS NULL;
```

---

## 🔧 Configuration Options

### Environment Variables

Create a `.env` file:
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sales_app_db
DB_USER=sales_app_user
DB_PASSWORD=your_secure_password
CSV_DIR=./csv_files
CNES_VERSION=202605
```

### Script Parameters

**setup_database.sh:**
```bash
# Customize via environment
export DB_NAME=my_custom_db
export DB_USER=my_user
export CSV_DIR=/path/to/csvs
./setup_database.sh
```

**import_cnes_data.py:**
```bash
python import_cnes_data.py \
    --csv-dir /path/to/csvs \
    --db-url "postgresql://user:pass@host:port/db" \
    --cnes-version 202605  # Optional
```

---

## 🐛 Troubleshooting

### Import Fails

**Check log file:**
```bash
tail -100 import_cnes_data.log
```

**Common issues:**
- CSV files not found → Check `--csv-dir` path
- Permission denied → Grant database permissions
- Out of memory → Reduce `BATCH_SIZE` in script
- Encoding errors → Script tries multiple encodings automatically

### Schema Creation Fails

**Check PostgreSQL version:**
```bash
psql --version  # Need 12+
```

**Check if tables exist:**
```sql
\dt  -- In psql
```

**Drop and recreate:**
```bash
psql -U postgres -c "DROP DATABASE sales_app_db;"
# Then rerun setup
```

### Slow Performance

**Add indexes:**
```sql
CREATE INDEX idx_custom ON table_name(column_name);
```

**Analyze tables:**
```sql
ANALYZE facilities;
ANALYZE professionals;
```

**Check query plans:**
```sql
EXPLAIN ANALYZE SELECT ...
```

---

## 📈 Performance Tips

### 1. Tune PostgreSQL
```
# postgresql.conf
shared_buffers = 256MB
work_mem = 64MB
maintenance_work_mem = 256MB
effective_cache_size = 1GB
```

### 2. Batch Import
Script already uses batching (10,000 rows per batch).

### 3. Connection Pooling
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    db_url,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10
)
```

---

## 🔄 Monthly Updates

When new CNES data is released:

```bash
# 1. Backup current database
pg_dump sales_app_db > backup_$(date +%Y%m%d).sql

# 2. Download new CSV files to new directory
mkdir csv_files_202607

# 3. Truncate tables
psql -d sales_app_db -c "TRUNCATE TABLE facilities CASCADE;"

# 4. Re-import
python import_cnes_data.py \
    --csv-dir ./csv_files_202607 \
    --db-url "postgresql://..." \
    --cnes-version 202607
```

---

## 📚 Related Documentation

- **DATABASE_SETUP_GUIDE.md** - Complete setup guide
- **SCHEMA_RENAMING_GUIDE.md** - Schema design details
- **SCHEMA_QUICK_REF.md** - Quick reference for column names
- **schema_mapping.json** - Machine-readable mapping
- **schema_mapper.py** - Python transformation utility

---

## 🎯 Example Queries

### Find Active Orthopedic Clinics in São Paulo
```sql
SELECT 
    f.trade_name,
    f.phone_number,
    f.email,
    m.municipality_name
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
JOIN facility_services fs ON f.facility_id = fs.facility_id
WHERE f.deactivation_reason_code IS NULL
    AND s.state_name = 'SÃO PAULO'
    AND fs.service_code LIKE '%ORTOPED%'
    AND fs.is_active = TRUE;
```

### Find Cardiologists with Contact Info
```sql
SELECT 
    p.full_name,
    f.trade_name AS facility_name,
    f.phone_number,
    pw.license_number
FROM professionals p
JOIN facility_professionals fp ON p.professional_id = fp.professional_id
JOIN facilities f ON fp.facility_id = f.facility_id
LEFT JOIN professional_workload pw 
    ON p.professional_id = pw.professional_id
    AND pw.professional_council_code = 'CRM'
WHERE fp.termination_date IS NULL
    AND f.deactivation_reason_code IS NULL
    AND fp.occupation_code IN ('225120', '225125')  -- Cardiologist codes
LIMIT 100;
```

### Facilities with MRI Equipment
```sql
SELECT 
    f.trade_name,
    f.phone_number,
    fe.quantity,
    rd.description AS equipment_name
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
JOIN reference_data rd 
    ON rd.reference_type = 'equipment_catalog' 
    AND rd.code = fe.equipment_code
WHERE f.deactivation_reason_code IS NULL
    AND rd.description LIKE '%RESSONANCIA%'
    AND fe.quantity > 0
    AND fe.operational_status = 'E';
```

---

## ✅ Success Checklist

- [ ] PostgreSQL installed and running
- [ ] Python 3.8+ installed
- [ ] All CSV files downloaded
- [ ] `create_sales_app_schema.sql` present
- [ ] `import_cnes_data.py` present
- [ ] `schema_mapping.json` present
- [ ] Run `./setup_database.sh` or manual steps
- [ ] Verify table counts
- [ ] Test example queries
- [ ] Connect application successfully

---

## 🎉 You're Done!

Your Sales App database is ready with:
- ✅ Clean, modern schema
- ✅ ~13 million records imported
- ✅ Optimized indexes
- ✅ Helpful views
- ✅ Clear English names

**Start building your app!** 🚀

---

**Questions?** Check the logs:
- `import_cnes_data.log` - Import details
- PostgreSQL logs - Database errors

**Need help?** Review:
- `DATABASE_SETUP_GUIDE.md` - Detailed guide
- `SCHEMA_QUICK_REF.md` - Quick reference
