# 🎯 QUICK START GUIDE

## ✨ Everything is Ready!

Your project is now **fully organized**, **converted to SQLite**, and **enhanced with powerful search views**.

---

## 📂 New Directory Structure

```
cnes_mapping/
│
├── 📄 README.md                      ← START HERE!
├── 📄 PROJECT_OVERVIEW.md            ← Complete documentation
├── 📄 DIRECTORY_INDEX.md             ← File navigation guide
├── 📄 COMPLETION_REPORT.md           ← What was completed
├── 🔧 setup_sqlite.sh               ← Run this to set up!
│
├── 📂 docs/                          ← All documentation
│   ├── START_HERE.md
│   ├── SCHEMA_RENAMING_GUIDE.md
│   ├── SALES_APP_TABLES.md
│   ├── IMPORT_PLAN.md
│   └── ... (20+ documentation files)
│
├── 📂 scripts/                       ← Python scripts
│   ├── import_sqlite_full.py        ⭐ Main import script
│   ├── analyze_csv_files.py
│   ├── analyze_relationships.py
│   └── ...
│
├── 📂 sql/                           ← SQL files
│   ├── create_sales_app_schema_sqlite.sql  ⭐ SQLite schema
│   ├── sample_queries.sql
│   └── ...
│
├── 📂 data/                          ← JSON/HTML outputs
│   ├── csv_analysis_report.json
│   ├── relationships_report.json
│   └── ...
│
├── 📂 logs/                          ← Import logs
├── 📂 import_errors/                 ← Error logs (per table)
├── 📂 output/                        ← Database files
│   └── cnes_data.db                 (created after import)
│
└── 📂 BASE_DE_DADOS_CNES_202605/    ← Source CSV files
```

---

## 🚀 3-Step Setup

### Step 1: Read the Overview
```bash
cat README.md
```

### Step 2: Set Up Database
```bash
./setup_sqlite.sh
```

This will:
- Create the SQLite database
- Prompt you to import data
- Show progress

### Step 3: Start Querying!
```bash
sqlite3 output/cnes_data.db
```

**That's it!** ✅

---

## 🎯 What's New

### ✅ **Organized**
Everything is in logical folders:
- Documentation → `docs/`
- Scripts → `scripts/`
- SQL → `sql/`
- Data → `data/`
- Logs → `logs/`

### ✅ **SQLite Database**
No PostgreSQL server needed:
- Single file database
- Portable and fast
- Easy to backup
- Simple to query

### ✅ **Enhanced Search Views**
Two powerful views for sales:

#### `professional_search_view`
Find professionals with:
- Employment history
- Active facilities
- Locations
- Licenses & credentials
- Specialties
- Work hours

#### `facility_search_view`
Find facilities with:
- Full contact info
- Staff counts
- Services offered
- Equipment inventory
- Capacity metrics
- Status tracking

---

## 💡 Quick Examples

### Find Active Facilities in São Paulo
```sql
SELECT 
    trade_name,
    municipality_name,
    phone_number,
    active_professionals_count,
    specialties
FROM facility_search_view
WHERE state_code = 'SP' AND status = 'ACTIVE'
ORDER BY active_professionals_count DESC
LIMIT 10;
```

### Find Professionals with Multiple Facilities
```sql
SELECT 
    full_name,
    active_facilities_count,
    current_facilities,
    current_locations,
    licenses
FROM professional_search_view
WHERE active_facilities_count > 1
ORDER BY active_facilities_count DESC
LIMIT 10;
```

### Find Facilities with Specific Equipment
```sql
SELECT 
    trade_name,
    municipality_name,
    equipment_types_count,
    total_equipment_count
FROM facility_search_view
WHERE equipment_types_count > 50
ORDER BY equipment_types_count DESC;
```

---

## 📊 What Data You Have

### Reference Tables:
- States (27)
- Municipalities (~5,600)
- Facility Types (~100)
- Equipment Catalog (~300)
- And more...

### Main Tables:
- Facilities (~623,000)
- Professionals (~7,761,000)
- Facility-Professional Links (~10M+)
- Services, Equipment, Workload

### Views:
- **professional_search_view** - 16 aggregated fields
- **facility_search_view** - 29 aggregated fields
- **active_facilities** - Simple active facilities
- **active_facility_professionals** - Current employment
- **facility_equipment_in_use** - Operational equipment

---

## 🔧 Common Tasks

### Import All Data
```bash
cd scripts
python import_sqlite_full.py --table all
```

### Import Specific Table
```bash
cd scripts
python import_sqlite_full.py --table facilities
```

### Re-import (Force)
```bash
cd scripts
python import_sqlite_full.py --table facilities --force
```

### Check Import Progress
```bash
tail -f logs/import_sqlite_full.log
```

### Check for Errors
```bash
cat import_errors/facilities.log
```

### Backup Database
```bash
cp output/cnes_data.db output/backup_$(date +%Y%m%d).db
```

---

## 📚 Documentation Quick Reference

| Need | Read This |
|------|-----------|
| Overview | **README.md** |
| Detailed guide | **PROJECT_OVERVIEW.md** |
| File locations | **DIRECTORY_INDEX.md** |
| What changed | **COMPLETION_REPORT.md** |
| Schema details | **docs/SCHEMA_RENAMING_GUIDE.md** |
| Sales tables | **docs/SALES_APP_TABLES.md** |
| Import details | **docs/IMPORT_PLAN.md** |

---

## ✅ Verification

Check everything is working:

```bash
# 1. Check database exists after import
ls -lh output/cnes_data.db

# 2. Check table count
sqlite3 output/cnes_data.db "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"

# 3. Check view count
sqlite3 output/cnes_data.db "SELECT COUNT(*) FROM sqlite_master WHERE type='view'"

# 4. Test a view
sqlite3 output/cnes_data.db "SELECT COUNT(*) FROM facility_search_view"
```

---

## 🎉 You Now Have

✅ **Organized Project** - Clean folder structure  
✅ **SQLite Database** - No server needed  
✅ **Enhanced Views** - Powerful search capabilities  
✅ **Complete Documentation** - Everything explained  
✅ **Working Scripts** - Import and analysis tools  
✅ **Error Handling** - Robust import process  

---

## 🆘 Need Help?

### Import Issues
```bash
# Check the log
cat logs/import_sqlite_full.log

# Check specific errors
cat import_errors/tablename.log
```

### Database Issues
```bash
# Verify database
sqlite3 output/cnes_data.db ".tables"

# Check schema
sqlite3 output/cnes_data.db ".schema facility_search_view"
```

### Path Issues
All scripts assume you run them from their respective folders:
- Run `setup_sqlite.sh` from project root
- Run `import_sqlite_full.py` from `scripts/` folder
- Or use `cd scripts && python import_sqlite_full.py ...`

---

## 🎓 Pro Tips

1. **Start Small**: Import reference tables first to test
2. **Check Logs**: Always check logs after import
3. **Use Views**: Views are pre-optimized for searches
4. **Backup Often**: SQLite is a single file, easy to backup
5. **Read Docs**: Lots of examples in the documentation

---

## 🚦 Next Actions

### Option 1: Quick Test
```bash
./setup_sqlite.sh  # Choose "Import reference tables only"
```

### Option 2: Full Import
```bash
./setup_sqlite.sh  # Choose "Import all tables"
# Go get coffee ☕ (takes ~1 hour)
```

### Option 3: Manual Control
```bash
# Create schema
sqlite3 output/cnes_data.db < sql/create_sales_app_schema_sqlite.sql

# Import selectively
cd scripts
python import_sqlite_full.py --table states
python import_sqlite_full.py --table facilities
```

---

## 📞 Summary

**Status**: ✅ Everything is ready!  
**Database Type**: SQLite 3  
**Location**: `output/cnes_data.db` (after import)  
**Views**: 5 pre-built search views  
**Tables**: 15 tables  
**Documentation**: Comprehensive  

**To start**: Run `./setup_sqlite.sh`

---

**Last Updated**: 2026-06-18  
**Version**: 2.0 (Reorganized + SQLite)  
**Ready**: ✅ Yes!
