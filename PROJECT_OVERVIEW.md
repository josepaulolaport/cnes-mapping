# CNES Sales App Database - Project Organization

## 📁 Directory Structure

```
cnes_mapping/
├── BASE_DE_DADOS_CNES_202605/    # Raw CSV data files (source data)
├── docs/                          # All documentation files
│   ├── README.md                  # Main project documentation
│   ├── START_HERE.md              # Quick start guide
│   ├── SCHEMA_RENAMING_GUIDE.md   # Schema transformation details
│   ├── IMPORT_PLAN.md             # Import execution plan
│   └── *.md                       # Other documentation files
├── scripts/                       # Python scripts
│   ├── import_sqlite.py           # Main import script (SQLite)
│   ├── analyze_csv_files.py       # CSV analysis tool
│   ├── analyze_relationships.py   # Relationship detection
│   ├── generate_descriptions.py   # Table description generator
│   └── schema_mapper.py           # Schema transformation utility
├── sql/                           # SQL files
│   ├── create_sales_app_schema_sqlite.sql  # SQLite schema (USE THIS)
│   ├── create_sales_app_schema.sql        # PostgreSQL schema (legacy)
│   ├── sample_queries.sql                  # Example queries
│   └── run_import.sh                       # Import automation script
├── data/                          # Analysis output files (JSON/HTML)
│   ├── csv_analysis_report.json
│   ├── relationships_report.json
│   ├── table_descriptions.json
│   └── *.json, *.html
├── logs/                          # Import and process logs
│   └── *.log
├── import_errors/                 # Error logs from imports
│   └── *.log
└── output/                        # Generated database files
    └── cnes_data.db              # SQLite database (created on import)
```

## 🚀 Quick Start Guide

### Prerequisites

```bash
# Install required Python packages
pip install pandas sqlalchemy tqdm
```

### 1. Create the SQLite Database

```bash
# Create the schema
sqlite3 output/cnes_data.db < sql/create_sales_app_schema_sqlite.sql
```

### 2. Import Data

```bash
# Import all tables (recommended for first time)
cd scripts
python import_sqlite.py --table all

# OR import specific tables
python import_sqlite.py --table states
python import_sqlite.py --table municipalities
python import_sqlite.py --table facilities
```

### 3. Verify Import

```bash
# Check record counts
sqlite3 output/cnes_data.db "
SELECT 'States' as table_name, COUNT(*) as count FROM states
UNION ALL SELECT 'Municipalities', COUNT(*) FROM municipalities
UNION ALL SELECT 'Facilities', COUNT(*) FROM facilities
UNION ALL SELECT 'Professionals', COUNT(*) FROM professionals;
"
```

## 🔍 Enhanced Search Views

The database includes two powerful search views:

### **professional_search_view**
Comprehensive professional search with aggregated data:
- All professional details
- Current employment locations
- Active facilities count
- Professional licenses and councils
- Occupation codes and specialties
- Work hours and characteristics

**Example Query:**
```sql
SELECT 
    full_name,
    active_facilities_count,
    current_facilities,
    current_locations,
    licenses
FROM professional_search_view
WHERE active_facilities_count > 0
ORDER BY full_name
LIMIT 10;
```

### **facility_search_view**
Comprehensive facility search with aggregated data:
- All facility details with full address
- Location information (state, municipality)
- Contact information
- Staff counts and occupation types
- Services and specialties offered
- Equipment types and quantities
- Capacity information

**Example Query:**
```sql
SELECT 
    trade_name,
    full_address,
    municipality_name,
    state_code,
    status,
    active_professionals_count,
    specialties,
    equipment_types_count
FROM facility_search_view
WHERE status = 'ACTIVE'
  AND state_code = 'SP'
  AND active_professionals_count > 10
ORDER BY active_professionals_count DESC;
```

## 📊 Common Queries

### Find Active Facilities in a State
```sql
SELECT 
    trade_name,
    municipality_name,
    phone_number,
    active_professionals_count
FROM facility_search_view
WHERE state_code = 'RJ' AND status = 'ACTIVE'
ORDER BY trade_name;
```

### Find Professionals by Specialty
```sql
SELECT 
    full_name,
    current_facilities,
    current_locations,
    occupation_codes
FROM professional_search_view
WHERE occupation_codes LIKE '%2231%'  -- Example occupation code
ORDER BY full_name;
```

### Find Facilities with Specific Equipment
```sql
SELECT DISTINCT
    f.trade_name,
    f.municipality_name,
    f.state_code,
    fe.equipment_name,
    fe.quantity
FROM facility_search_view f
JOIN facility_equipment_in_use fe ON f.facility_id = fe.facility_id
WHERE fe.equipment_name LIKE '%RAIO%X%'
ORDER BY f.state_code, f.trade_name;
```

## 📝 Data Import Status

Check import progress:
```bash
# View import log
tail -f logs/import_sqlite.log

# Check for errors
ls -lh import_errors/*.log

# View specific error log
cat import_errors/facilities.log
```

## 🔧 Maintenance

### Re-import a Specific Table
```bash
python scripts/import_sqlite.py --table facilities --force
```

### Backup Database
```bash
cp output/cnes_data.db output/cnes_data_backup_$(date +%Y%m%d).db
```

### Optimize Database
```bash
sqlite3 output/cnes_data.db "VACUUM; ANALYZE;"
```

## 📚 Documentation Files

| File | Description |
|------|-------------|
| `docs/START_HERE.md` | Quick start guide |
| `docs/SCHEMA_RENAMING_GUIDE.md` | Column name transformations |
| `docs/SALES_APP_TABLES.md` | Tables relevant for sales app |
| `docs/SCHEMA_QUICK_REF.md` | Quick reference cheat sheet |
| `docs/IMPORT_PLAN.md` | Detailed import plan |

## 🎯 Schema Benefits

### SQLite Advantages
- ✅ **No server required** - Single file database
- ✅ **Portable** - Easy to copy and share
- ✅ **Fast** - Excellent for read-heavy workloads
- ✅ **Simple** - No complex setup or configuration
- ✅ **Reliable** - ACID compliant, battle-tested

### Schema Improvements
- ✅ **English names** instead of Portuguese abbreviations
- ✅ **Self-documenting** column names
- ✅ **Proper data types** (INTEGER, REAL, TEXT)
- ✅ **Indexed for search** performance
- ✅ **Enhanced views** for common queries

## 🐛 Troubleshooting

### Import fails with encoding errors
```bash
# The script tries multiple encodings automatically
# Check logs/import_sqlite.log for details
```

### Database locked error
```bash
# Close any open SQLite connections
# Only one process can write at a time
```

### View shows NULL values
```bash
# Views use LEFT JOINs - NULL is expected for missing data
# Use COALESCE() or IFNULL() to handle NULLs in queries
```

## 📞 Support

For issues or questions:
1. Check `logs/import_sqlite.log`
2. Review `import_errors/` directory
3. Consult documentation in `docs/`

## 🔄 Version Information

- **CNES Data**: 202605 (May 2026)
- **Database**: SQLite 3
- **Python**: 3.7+
- **Dependencies**: pandas, sqlalchemy, tqdm

---

**Last Updated**: 2026-06-18
