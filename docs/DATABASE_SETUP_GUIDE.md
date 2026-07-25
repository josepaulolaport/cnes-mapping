# Database Setup and Import Guide

Complete guide to set up your Sales App database and import CNES data.

## 📋 Overview

This guide walks you through:
1. Setting up the PostgreSQL database
2. Creating the schema with the SQL script
3. Importing CNES CSV data with the Python script

## 🔧 Prerequisites

### 1. PostgreSQL Database
- PostgreSQL 12 or higher
- Access to create databases and tables

### 2. Python Environment
- Python 3.8 or higher
- pip for package installation

### 3. CNES CSV Files
- Download from [CNES FTP](ftp://ftp.datasus.gov.br/cnes/)
- Place all CSV files in a directory (e.g., `./csv_files/`)

Required files:
- `tbEstabelecimento202605.csv`
- `tbDadosProfissionalSus202605.csv`
- `rlEstabEquipeProf202605.csv`
- `rlEstabServClass202605.csv`
- `rlEstabEquipamento202605.csv`
- `tbCargaHorariaSus202605.csv`
- `tbMunicipio202605.csv`
- `tbEstado202605.csv`
- `tbTipoEstabelecimento202605.csv`
- `tbMotivoDesativacao202605.csv`
- `tbServicoEspecializado202605.csv`
- `tbEquipamento202605.csv`
- `tbConselhoClasse202605.csv`
- `tbTipoEquipamento202605.csv`
- `tbClassificacaoServico202605.csv`

---

## 📦 Step 1: Install Python Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install pandas sqlalchemy psycopg2-binary python-dotenv tqdm

# Verify installation
python -c "import pandas; import sqlalchemy; print('✅ All packages installed')"
```

---

## 🗄️ Step 2: Create Database

### Option A: Using psql Command Line

```bash
# Connect to PostgreSQL
psql -U postgres

# In psql prompt:
CREATE DATABASE sales_app_db;
CREATE USER sales_app_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE sales_app_db TO sales_app_user;
\q
```

### Option B: Using pgAdmin
1. Open pgAdmin
2. Right-click "Databases" → Create → Database
3. Name: `sales_app_db`
4. Owner: Create/select user
5. Save

---

## 🏗️ Step 3: Create Schema

Run the SQL script to create all tables:

```bash
# Using psql
psql -U sales_app_user -d sales_app_db -f create_sales_app_schema.sql

# Or connect and run
psql -U sales_app_user -d sales_app_db
\i create_sales_app_schema.sql
```

**Expected output:**
```
CREATE TABLE
CREATE TABLE
...
NOTICE: ========================================
NOTICE: Sales App Schema Created Successfully!
NOTICE: ========================================
```

**Verify tables were created:**
```sql
-- In psql
\dt

-- You should see:
-- states
-- municipalities
-- reference_data
-- facilities
-- professionals
-- facility_professionals
-- facility_services
-- facility_equipment
-- professional_workload
-- service_classifications
-- facility_owners
```

---

## 📥 Step 4: Import CNES Data

### Prepare CSV Files

Ensure all CSV files are in one directory:
```bash
ls csv_files/
# Should show all required CSV files
```

### Run Import Script

```bash
# Full command
python import_cnes_data.py \
    --csv-dir ./csv_files \
    --db-url "postgresql://sales_app_user:your_password@localhost:5432/sales_app_db"

# With CNES version specified (optional)
python import_cnes_data.py \
    --csv-dir ./csv_files \
    --db-url "postgresql://sales_app_user:your_password@localhost:5432/sales_app_db" \
    --cnes-version 202605
```

### Using Environment Variables (Recommended)

Create a `.env` file:
```bash
# .env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=sales_app_db
DB_USER=sales_app_user
DB_PASSWORD=your_secure_password
CSV_DIR=./csv_files
```

Then modify script to use:
```bash
python import_cnes_data.py \
    --csv-dir $CSV_DIR \
    --db-url "postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
```

---

## ⏱️ Expected Import Time

| Table | Rows | Estimated Time |
|-------|------|----------------|
| states | 27 | < 1 second |
| municipalities | 5,607 | < 5 seconds |
| reference_data | ~2,000 | < 10 seconds |
| facilities | ~620,000 | 2-5 minutes |
| professionals | ~7,700,000 | **15-30 minutes** |
| facility_professionals | ~870,000 | 3-5 minutes |
| facility_services | ~1,400,000 | 5-8 minutes |
| facility_equipment | ~1,300,000 | 5-8 minutes |
| professional_workload | ~1,200,000 | 5-8 minutes |
| **TOTAL** | **~13,000,000** | **40-70 minutes** |

*Times vary based on hardware and database configuration*

---

## 🎯 Step 5: Verify Import

### Check Row Counts

```sql
-- Connect to database
psql -U sales_app_user -d sales_app_db

-- Check all table counts
SELECT 
    schemaname,
    tablename,
    n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

Expected results (approximate):
```
 tablename               | row_count
-------------------------+------------
 professionals           | 7,761,583
 facility_services       | 1,442,080
 facility_equipment      | 1,348,380
 professional_workload   | 1,200,000
 facility_professionals  | 870,453
 facilities              | 623,208
 municipalities          | 5,607
 reference_data          | 2,000
 service_classifications | varies
 facility_owners         | varies
 states                  | 27
```

### Test Critical Queries

```sql
-- 1. Active facilities
SELECT COUNT(*) as active_facilities
FROM facilities
WHERE deactivation_reason_code IS NULL;
-- Should return ~600,000+

-- 2. Currently employed professionals
SELECT COUNT(DISTINCT professional_id) as active_professionals
FROM facility_professionals
WHERE termination_date IS NULL;
-- Should return ~800,000+

-- 3. Facilities in São Paulo state
SELECT COUNT(*) as sp_facilities
FROM facilities f
JOIN municipalities m ON f.municipality_id = m.municipality_id
JOIN states s ON m.state_code = s.state_code
WHERE s.state_name = 'SÃO PAULO'
    AND f.deactivation_reason_code IS NULL;

-- 4. Test a complex query (facilities with equipment)
SELECT 
    f.trade_name,
    f.phone_number,
    COUNT(DISTINCT fe.equipment_code) as equipment_count
FROM facilities f
JOIN facility_equipment fe ON f.facility_id = fe.facility_id
WHERE f.deactivation_reason_code IS NULL
    AND fe.quantity > 0
GROUP BY f.facility_id, f.trade_name, f.phone_number
LIMIT 10;
```

### Test Views

```sql
-- Active facilities view
SELECT * FROM active_facilities LIMIT 5;

-- Active professionals view
SELECT * FROM active_facility_professionals LIMIT 5;

-- Equipment in use view
SELECT * FROM facility_equipment_in_use LIMIT 5;
```

---

## 🐛 Troubleshooting

### Import Fails with "Permission Denied"

```sql
-- Grant necessary permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO sales_app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO sales_app_user;
```

### Import Fails with "Foreign Key Constraint"

This usually means tables are being imported out of order. The script handles this automatically, but if you're running manually:

**Import order:**
1. states
2. municipalities
3. reference_data
4. service_classifications
5. facility_owners (extracted from facilities)
6. facilities
7. professionals
8. facility_professionals
9. facility_services
10. facility_equipment
11. professional_workload

### "Out of Memory" Error

If importing large tables fails:

1. **Increase batch size** in script:
   ```python
   BATCH_SIZE = 5000  # Reduce from 10000
   ```

2. **Increase PostgreSQL memory**:
   Edit `postgresql.conf`:
   ```
   shared_buffers = 256MB
   work_mem = 64MB
   maintenance_work_mem = 256MB
   ```

3. **Import tables separately**:
   Comment out large tables in script and run multiple times.

### CSV Encoding Errors

The script tries multiple encodings automatically. If it still fails:

1. Check file encoding:
   ```bash
   file -i csv_files/tbEstabelecimento202605.csv
   ```

2. Convert if needed:
   ```bash
   iconv -f ISO-8859-1 -t UTF-8 input.csv > output.csv
   ```

### Slow Import

**Speed up import:**

1. **Disable indexes temporarily** (for initial import only):
   ```sql
   DROP INDEX IF EXISTS idx_facilities_active;
   -- ... drop other indexes
   -- Run import
   -- Recreate indexes after
   ```

2. **Tune PostgreSQL for bulk loading**:
   ```sql
   SET maintenance_work_mem = '1GB';
   SET checkpoint_timeout = '30min';
   ```

3. **Use COPY instead of INSERT** (advanced):
   Modify script to use PostgreSQL COPY command for faster bulk loading.

---

## 🔒 Security Best Practices

### 1. Use Strong Passwords
```bash
# Generate strong password
openssl rand -base64 32
```

### 2. Don't Commit Credentials
Add to `.gitignore`:
```
.env
*.log
__pycache__/
venv/
```

### 3. Use Connection Pooling
For production, use connection pooling:
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    db_url,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10
)
```

### 4. Restrict Database Access
```sql
-- Revoke public access
REVOKE ALL ON DATABASE sales_app_db FROM PUBLIC;

-- Grant specific access
GRANT CONNECT ON DATABASE sales_app_db TO sales_app_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sales_app_readonly;
```

---

## 📊 Post-Import Optimization

### Create Additional Indexes

```sql
-- For name searches (requires pg_trgm extension)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_facilities_trade_name_trgm 
    ON facilities USING gin(trade_name gin_trgm_ops);

CREATE INDEX idx_professionals_name_trgm 
    ON professionals USING gin(full_name gin_trgm_ops);
```

### Analyze Tables

```sql
-- Update statistics for query planner
ANALYZE facilities;
ANALYZE professionals;
ANALYZE facility_professionals;
ANALYZE facility_services;
ANALYZE facility_equipment;
```

### Vacuum Database

```sql
-- Reclaim space and update statistics
VACUUM ANALYZE;
```

---

## 🔄 Monthly Updates

When new CNES data is released:

### Option 1: Full Refresh (Recommended)

```bash
# 1. Backup current database
pg_dump -U sales_app_user sales_app_db > backup_$(date +%Y%m%d).sql

# 2. Truncate tables (in reverse order)
psql -U sales_app_user -d sales_app_db -c "
    TRUNCATE professional_workload CASCADE;
    TRUNCATE facility_equipment CASCADE;
    TRUNCATE facility_services CASCADE;
    TRUNCATE facility_professionals CASCADE;
    TRUNCATE professionals CASCADE;
    TRUNCATE facilities CASCADE;
    TRUNCATE municipalities CASCADE;
    TRUNCATE states CASCADE;
    TRUNCATE reference_data CASCADE;
"

# 3. Re-import with new files
python import_cnes_data.py \
    --csv-dir ./csv_files_202607 \
    --db-url "postgresql://sales_app_user:password@localhost:5432/sales_app_db" \
    --cnes-version 202607
```

### Option 2: Incremental Update (Advanced)

Track changes between versions and update only modified records (requires custom logic).

---

## 📈 Monitoring

### Check Database Size

```sql
SELECT 
    pg_size_pretty(pg_database_size('sales_app_db')) as db_size;
```

### Check Table Sizes

```sql
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - 
                   pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Monitor Import Progress

```bash
# Watch import log in real-time
tail -f import_cnes_data.log

# Or check recent errors
tail -100 import_cnes_data.log | grep ERROR
```

---

## ✅ Success Checklist

- [ ] PostgreSQL installed and running
- [ ] Database `sales_app_db` created
- [ ] User `sales_app_user` created with proper permissions
- [ ] Python dependencies installed
- [ ] All CNES CSV files downloaded
- [ ] Schema created successfully (11 tables + 3 views)
- [ ] All data imported successfully (~13M records)
- [ ] Row counts verified
- [ ] Test queries run successfully
- [ ] Views working correctly
- [ ] Database backed up
- [ ] Application can connect and query

---

## 📞 Support

### Log Files
- Check `import_cnes_data.log` for detailed import logs
- All errors are logged with full stack traces

### Common Issues
- **Out of disk space**: Check with `df -h`, need ~10GB free
- **Connection refused**: Check PostgreSQL is running: `sudo systemctl status postgresql`
- **Authentication failed**: Verify credentials in connection string

### Performance Issues
- Run `EXPLAIN ANALYZE` on slow queries
- Check if indexes are being used
- Consider partitioning very large tables

---

## 🎉 Next Steps

After successful import:

1. **Connect your application** to the database
2. **Test key workflows** (search facilities, find professionals, etc.)
3. **Set up backups** (daily recommended)
4. **Monitor performance** and create indexes as needed
5. **Document** any custom modifications

---

**Database is ready!** You can now use the clean, modern schema for your Sales App! 🚀
