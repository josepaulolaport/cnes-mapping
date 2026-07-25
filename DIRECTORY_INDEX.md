# CNES Mapping Project - File Index

## Quick Navigation

### 🚀 **START HERE**
- **`PROJECT_OVERVIEW.md`** - Main documentation, read this first!
- **`setup_sqlite.sh`** - Run this to set up everything

---

## 📁 Directory Guide

### `docs/` - Documentation
All markdown documentation files explaining the project, schema, and processes.

**Key Files:**
- `START_HERE.md` - Quick start guide
- `SCHEMA_RENAMING_GUIDE.md` - How column names were transformed
- `SALES_APP_TABLES.md` - Tables relevant for sales application
- `IMPORT_PLAN.md` - Detailed import execution plan

### `scripts/` - Python Scripts
All executable Python scripts for data processing.

**Main Scripts:**
- **`import_sqlite.py`** ⭐ - Main import script (USE THIS)
- `analyze_csv_files.py` - Analyze CSV structure
- `analyze_relationships.py` - Detect table relationships
- `generate_descriptions.py` - Generate table descriptions
- `schema_mapper.py` - Schema transformation utility

### `sql/` - SQL Files
Database schema definitions and queries.

**Main Files:**
- **`create_sales_app_schema_sqlite.sql`** ⭐ - SQLite schema (USE THIS)
- `create_sales_app_schema.sql` - PostgreSQL schema (legacy)
- `sample_queries.sql` - Example queries
- `run_import.sh` - PostgreSQL import script (legacy)

### `data/` - Analysis Output
JSON and HTML files containing analysis results.

**Generated Files:**
- `csv_analysis_report.json` - CSV structure analysis
- `relationships_report.json` - Table relationships
- `table_descriptions.json` - Table descriptions
- `table_descriptions.html` - HTML version
- `schema_mapping.json` - Column name mappings

### `logs/` - Log Files
Import and process execution logs.

**Log Files:**
- `import_sqlite.log` - Current import log
- Other `.log` files from various runs

### `import_errors/` - Error Logs
Detailed error logs for failed imports (per table).

**Structure:**
- `table_name.log` - Errors for specific table imports

### `output/` - Generated Databases
Final SQLite database files.

**Files:**
- **`cnes_data.db`** - Main SQLite database (created after import)

### `BASE_DE_DADOS_CNES_202605/` - Source Data
Original CNES CSV files (do not modify).

---

## 🎯 Workflow

### First Time Setup:
1. Read `PROJECT_OVERVIEW.md`
2. Run `./setup_sqlite.sh`
3. Wait for import to complete
4. Query database: `sqlite3 output/cnes_data.db`

### Importing Data:
```bash
# Import all tables
cd scripts
python import_sqlite.py --table all

# Import specific table
python import_sqlite.py --table facilities

# Re-import with force
python import_sqlite.py --table facilities --force
```

### Querying Data:
```bash
# Open database
sqlite3 output/cnes_data.db

# Run sample queries
sqlite3 output/cnes_data.db < sql/sample_queries.sql

# Use enhanced views
sqlite3 output/cnes_data.db "SELECT * FROM facility_search_view LIMIT 10"
```

---

## 📊 Enhanced Views

The database includes powerful pre-built views:

1. **`professional_search_view`**
   - Aggregated professional data with employment history
   - Includes: facilities, locations, licenses, specialties

2. **`facility_search_view`**
   - Aggregated facility data with all related info
   - Includes: staff counts, services, equipment, capacity

3. **`active_facilities`**
   - Simple view of active facilities only

4. **`active_facility_professionals`**
   - Currently employed professionals at active facilities

5. **`facility_equipment_in_use`**
   - Equipment currently in use at facilities

---

## 🔧 Troubleshooting

### Check Import Status:
```bash
tail -f logs/import_sqlite.log
```

### Check for Errors:
```bash
ls -lh import_errors/
cat import_errors/facilities.log
```

### Database Size:
```bash
du -h output/cnes_data.db
```

### Verify Tables:
```bash
sqlite3 output/cnes_data.db ".tables"
```

---

## 📝 Notes

- **PostgreSQL files** (in `sql/`) are kept for reference but not used
- **Original import script** (`scripts/import_modular.py`) is PostgreSQL-specific
- **Use SQLite versions** for all new work
- **Views are pre-created** in the schema, no need to run separately

---

**Last Updated:** 2026-06-18
**Database Format:** SQLite 3
**Data Version:** CNES 202605
