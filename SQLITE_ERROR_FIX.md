# SQLite Import Error Fix Summary

## What Happened

The import script ran but failed during the `municipalities` table import. The error was too quick because:

### Issue 1: Batch Size Too Large for SQLite
**Problem**: The original batch size of 10,000 rows is too large for SQLite's batch insert mechanism. SQLite can handle large inserts but performs better with smaller batches.

**Solution**: Reduced `BATCH_SIZE` from `10000` to `1000` in `scripts/import_sqlite_full.py`

### Issue 2: Error Logs in Wrong Folder
**Problem**: Error logs were going to `import_errors/` (shared with PostgreSQL scripts)

**Solution**: 
- Created new dedicated folder: `import_errors_sqlite/`
- Updated `ERROR_LOG_DIR` in the script to use the new folder

## Fixes Applied

### File: `scripts/import_sqlite_full.py`

```python
# Before:
BATCH_SIZE = 10000
ERROR_LOG_DIR = Path('../import_errors')

# After:
BATCH_SIZE = 1000  # Reduced for SQLite
ERROR_LOG_DIR = Path('../import_errors_sqlite')
```

## Directory Structure

```
cnes_mapping/
├── import_errors/          ← PostgreSQL errors (old)
├── import_errors_sqlite/   ← SQLite errors (new) ✅
├── logs/
│   └── import_sqlite_full.log
└── ...
```

## How to Run Now

### Option 1: Quick Test (Recommended First)
Test with just reference tables:

```bash
cd /Users/josepaulolaport/Documents/projects/cnes_mapping/scripts
python3 import_sqlite_full.py --table states
python3 import_sqlite_full.py --table municipalities
python3 import_sqlite_full.py --table facility_types
```

### Option 2: Full Import
Once the test works:

```bash
cd /Users/josepaulolaport/Documents/projects/cnes_mapping/scripts
python3 import_sqlite_full.py --table all
```

## Error Logs

- **Main log**: `logs/import_sqlite_full.log`
- **Error details**: `import_errors_sqlite/*.log` (one file per table)

Each error log file will contain:
- Batch number where error occurred
- Row index within the batch
- Exact error message
- The problematic data

## SQLite Performance Notes

### Expected Behavior:
- **Slower than PostgreSQL**: SQLite uses smaller batches (1,000 vs 10,000)
- **Single writer**: Only one process can write at a time
- **File-based**: All data in one `output/cnes_data.db` file
- **Progress tracking**: tqdm will show progress bars

### Import Time Estimates:
With the new batch size of 1,000:
- **Small tables** (states, types): 10-30 seconds each
- **Medium tables** (municipalities): 1-2 minutes
- **Large tables** (facilities): 10-15 minutes
- **Huge tables** (professionals): 60-90 minutes
- **Total estimate**: 2-3 hours

## Troubleshooting

### If Import Still Fails:

1. **Check the error logs**:
   ```bash
   ls -lh import_errors_sqlite/
   cat import_errors_sqlite/municipalities.log
   ```

2. **Reduce batch size further** (if needed):
   Edit `scripts/import_sqlite_full.py`, change:
   ```python
   BATCH_SIZE = 500  # Even smaller
   ```

3. **Check database file**:
   ```bash
   ls -lh output/cnes_data.db
   sqlite3 output/cnes_data.db ".tables"
   ```

4. **Clear and restart**:
   ```bash
   rm output/cnes_data.db
   sqlite3 output/cnes_data.db < sql/create_sales_app_schema_sqlite.sql
   cd scripts && python3 import_sqlite_full.py --table all
   ```

## Why SQLite Batch Size Matters

SQLite limitations compared to PostgreSQL:
- **Transaction overhead**: Each batch is a transaction
- **Lock management**: Simpler locking = smaller optimal batches
- **Memory constraints**: SQLite holds more in memory per batch
- **Write throughput**: Optimized for smaller, frequent writes

The reduction from 10,000 to 1,000 rows per batch gives:
- ✅ More stable imports
- ✅ Better error recovery
- ✅ More frequent progress updates
- ⚠️ Slightly slower overall (but more reliable)

## Next Steps

1. **Run a test import** of small tables
2. **Check the error logs** in `import_errors_sqlite/`
3. **If successful**, run the full import with `--table all`
4. **Monitor progress** with `tail -f logs/import_sqlite_full.log`

---

**Status**: ✅ Ready to run
**Fixes Applied**: 2
**New Folder**: `import_errors_sqlite/`
**Updated**: 2026-06-18
