# Schema Renaming Project - README

## 📋 Overview

The CNES (Cadastro Nacional de Estabelecimentos de Saúde) database uses cryptic Portuguese abbreviations and date-suffixed table names that are difficult to work with. This project provides a complete renaming strategy to transform the CNES schema into a clear, modern, English-based schema suitable for a sales application.

## 🎯 Goals Achieved

✅ **Clear English names** - No more Portuguese abbreviations  
✅ **Self-documenting** - Column names explain their purpose  
✅ **Modern conventions** - Follows industry best practices  
✅ **Complete mapping** - Every table and column documented  
✅ **Developer tools** - Python helper for ETL/migrations  
✅ **Quick reference** - Cheat sheet for daily use  

## 📂 Files Created

### 1. **SCHEMA_RENAMING_GUIDE.md** 📖
The comprehensive documentation covering everything:
- Complete table name mappings
- Complete column name mappings for all sales app tables
- Naming pattern explanations
- Data type standardization
- SQL migration examples
- Before/after query comparisons
- Benefits and rationale

**Use this when:** You need full details, examples, or want to understand the reasoning.

### 2. **schema_mapping.json** 🗂️
Machine-readable JSON file containing:
- All table mappings
- All column mappings with types
- Foreign key information
- Primary key information
- Naming pattern documentation

**Use this when:** Building ETL pipelines, generating code, or need programmatic access to mappings.

### 3. **schema_mapper.py** 🐍
Python utility class providing:
- `CNESSchemaMapper` - Main class for transformations
- DataFrame column renaming
- Table name lookups
- Column name lookups
- Type information retrieval
- Foreign key detection
- SQL migration script generation

**Use this when:** Writing ETL scripts, transforming data, or migrating databases.

**Example:**
```python
from schema_mapper import CNESSchemaMapper

mapper = CNESSchemaMapper('schema_mapping.json')

# Rename DataFrame columns
df_renamed = mapper.rename_dataframe_columns(
    df, 
    'tbEstabelecimento202605.csv'
)

# Get new names
new_table = mapper.get_new_table_name('tbEstabelecimento202605.csv')
new_col = mapper.get_new_column_name('tbEstabelecimento202605.csv', 'NO_FANTASIA')
```

### 4. **SCHEMA_QUICK_REF.md** 📄
One-page cheat sheet with:
- Most common table renames
- Most common column renames
- Critical status fields
- Naming patterns
- Quick Python examples
- Query translation examples

**Use this when:** Coding, writing queries, or need quick lookups without opening full docs.

## 🔄 Key Transformations

### Table Names

| Category | Old Pattern | New Pattern |
|----------|-------------|-------------|
| Main tables | `tbEstabelecimento202605.csv` | `facilities` |
| Relationship tables | `rlEstabEquipeProf202605.csv` | `facility_professionals` |
| Lookup tables | Multiple small `tb*` files | Consolidated `reference_data` |

**Benefits:**
- No date suffixes (version controlled separately)
- No Portuguese prefixes (tb, rl)
- Clear, descriptive names
- Easier to remember and type

### Column Names

#### Old CNES Pattern:
```
CO_UNIDADE          <- What does CO_ mean?
NO_FANTASIA         <- What does NO_ mean?
NU_TELEFONE         <- What does NU_ mean?
DT_DESLIGAMENTO     <- What does DT_ mean?
```

#### New Sales App Pattern:
```
facility_id         <- Clearly an ID
trade_name          <- Obviously a name
phone_number        <- Obviously a phone number
termination_date    <- Obviously a date
```

**Benefits:**
- Self-documenting
- No need to memorize prefix meanings
- Better IDE autocomplete
- International team friendly

### Common Prefixes Removed

| Old Prefix | Meaning | New Pattern |
|------------|---------|-------------|
| `CO_` | Código (Code) | `*_id` or `*_code` |
| `NO_` | Nome (Name) | `*_name` |
| `NU_` | Número (Number) | `*_number` |
| `DS_` | Descrição (Description) | descriptive name |
| `TP_` | Tipo (Type) | `*_type` |
| `ST_` | Status | `is_*` or `has_*` |
| `DT_` | Data (Date) | `*_date` |
| `IND_` | Indicador (Indicator) | `is_*` |
| `QT_` | Quantidade (Quantity) | `quantity` or `count` |

## 🎨 New Naming Conventions

### Identifiers
- Pattern: `*_id`
- Examples: `facility_id`, `professional_id`, `municipality_id`

### Reference Codes
- Pattern: `*_code`
- Examples: `facility_type_code`, `equipment_code`, `occupation_code`

### Names
- Pattern: `*_name`
- Examples: `trade_name`, `legal_name`, `full_name`

### Dates
- Pattern: `*_date`
- Examples: `start_date`, `termination_date`, `last_updated_date`

### Booleans
- Pattern: `is_*` or `has_*`
- Examples: `is_active`, `is_24_7`, `has_internet`

### Quantities
- Pattern: `quantity` or specific name
- Examples: `quantity`, `weekly_hours_ambulatory`

## 🚨 Critical Fields for Sales App

### 1. Deactivation Status (Facilities)
```sql
-- Old:
WHERE CO_MOTIVO_DESAB IS NULL  -- Active

-- New:
WHERE deactivation_reason_code IS NULL  -- Active (much clearer!)
```

### 2. Employment Status (Professionals)
```sql
-- Old:
WHERE DT_DESLIGAMENTO IS NULL  -- Currently employed

-- New:
WHERE termination_date IS NULL  -- Currently employed (crystal clear!)
```

### 3. Service Status
```sql
-- Old:
WHERE ST_ATIVO_SN = 'S'  -- Active service

-- New:
WHERE is_active = true  -- Active service (proper boolean!)
```

## 🛠️ How to Use This in Your Project

### Option 1: Direct Migration (Recommended for New Projects)
1. Create new database tables with new names
2. Use `schema_mapper.py` to transform CSV data
3. Import transformed data into new tables
4. Write all new code using new schema

### Option 2: View Layer (For Existing Systems)
1. Keep original CNES tables as-is
2. Create database views with new names/columns
3. Use views in your application
4. Gradually migrate to new schema

### Option 3: ETL Pipeline
1. Import CNES CSVs to staging tables (old names)
2. Use `schema_mapper.py` in transformation step
3. Load into production tables (new names)
4. Application uses only new schema

## 📊 Example Migrations

### Simple Column Rename
```python
# Load CNES CSV
df = pd.read_csv('tbEstabelecimento202605.csv', encoding='latin1', delimiter=';')

# Transform using mapper
mapper = CNESSchemaMapper('schema_mapping.json')
df_new = mapper.rename_dataframe_columns(df, 'tbEstabelecimento202605.csv')

# df_new now has: facility_id, trade_name, phone_number, etc.
```

### Full Database Migration
```python
from schema_mapper import CNESSchemaMapper, create_sql_migration_script

# Generate SQL script
mapper = CNESSchemaMapper('schema_mapping.json')
create_sql_migration_script(mapper, 'migration.sql')

# Review migration.sql and run it on your database
```

### Query Translation
```python
# Old query (hard to read)
query_old = """
    SELECT CO_UNIDADE, NO_FANTASIA, NU_TELEFONE
    FROM tbEstabelecimento202605
    WHERE CO_MOTIVO_DESAB IS NULL
"""

# New query (crystal clear)
query_new = """
    SELECT facility_id, trade_name, phone_number
    FROM facilities
    WHERE deactivation_reason_code IS NULL
"""
```

## 📈 Benefits Summary

### For Developers
- ✅ Faster onboarding (no Portuguese dictionary needed)
- ✅ Better IDE support (descriptive names)
- ✅ Fewer bugs (self-documenting fields)
- ✅ Easier code reviews (readable queries)

### For Business
- ✅ Lower maintenance costs
- ✅ Easier to hire developers (standard naming)
- ✅ Better documentation
- ✅ Faster feature development

### For Data Team
- ✅ Clear ETL pipelines
- ✅ Easier data quality checks
- ✅ Better error messages
- ✅ Simpler training materials

## 🎓 Training & Documentation

### New Team Members
1. Read `SCHEMA_QUICK_REF.md` (5 minutes)
2. Skim `SCHEMA_RENAMING_GUIDE.md` (15 minutes)
3. Keep `SCHEMA_QUICK_REF.md` open while coding

### Writing Queries
1. Check `SCHEMA_QUICK_REF.md` for common fields
2. Use `schema_mapper.py` for programmatic lookups
3. Refer to `SCHEMA_RENAMING_GUIDE.md` for full mappings

### Building ETL Pipelines
1. Import `schema_mapper.py`
2. Use `CNESSchemaMapper` class
3. Reference `schema_mapping.json` for types and relationships

## 📝 Maintenance

### When CNES Updates (New Month's Data)
1. New CSVs will have new date suffix (e.g., `202607`)
2. Column names should remain the same
3. Use same `schema_mapper.py` (just update file references)
4. No need to update mappings unless CNES changes column names

### When Adding New Tables
1. Add to `schema_mapping.json`
2. Update `SCHEMA_RENAMING_GUIDE.md`
3. Update `SCHEMA_QUICK_REF.md` if commonly used
4. `schema_mapper.py` automatically picks up changes

## 🤝 Recommendations

### For Sales App Development
1. ✅ **Use new schema from day 1** - Don't build on old names
2. ✅ **Start with Phase 1 tables** - Core 7 tables (see SALES_APP_TABLES.md)
3. ✅ **Use reference_data consolidation** - Simpler than many lookup tables
4. ✅ **Always filter by deactivation status** - Critical for accurate leads

### Database Setup
1. ✅ **Create new tables with new names** - Clean start
2. ✅ **Use proper data types** - BOOLEAN instead of CHAR(1), etc.
3. ✅ **Add indexes on foreign keys** - Performance
4. ✅ **Add indexes on status fields** - Frequent WHERE clauses

### Code Standards
1. ✅ **Never use old column names in application code**
2. ✅ **Use transformation layer (schema_mapper.py) for imports**
3. ✅ **Keep cheat sheet handy for quick lookups**
4. ✅ **Document any custom transformations**

## 📞 Quick Support

### "What's the new name for X?"
→ Check `SCHEMA_QUICK_REF.md` or use `schema_mapper.py`:
```python
mapper.get_new_column_name('table_name', 'old_column_name')
```

### "How do I transform my DataFrame?"
→ Use `schema_mapper.py`:
```python
df_new = mapper.rename_dataframe_columns(df, 'old_table_name')
```

### "I need the full mapping details"
→ Check `SCHEMA_RENAMING_GUIDE.md`

### "I need to write ETL code"
→ Use `schema_mapping.json` with `schema_mapper.py`

## 🎉 Summary

You now have a complete, production-ready schema renaming strategy that transforms cryptic CNES names into clear, modern, English-based names. The included tools make it easy to implement this in your sales application.

**Key files:**
- 📖 `SCHEMA_RENAMING_GUIDE.md` - Full documentation
- 🗂️ `schema_mapping.json` - Machine-readable mappings
- 🐍 `schema_mapper.py` - Python transformation utility
- 📄 `SCHEMA_QUICK_REF.md` - Daily cheat sheet

**Next steps:**
1. Review the quick reference
2. Run example in `schema_mapper.py`
3. Start building with new schema names
4. Never look back at cryptic names again! 🚀

---

**Created:** 2026-06-18  
**Version:** 1.0  
**Status:** Production Ready ✅
