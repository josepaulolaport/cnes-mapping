# Table Descriptions Summary

## Overview

Generated comprehensive descriptions for all 109 tables in the CNES (Cadastro Nacional de Estabelecimentos de Saúde) database from May 2026.

## Files Created

1. **`table_descriptions.json`** (63.7 KB)
   - JSON file with structured descriptions for each table
   - Includes metadata: row counts, column counts, table type, PK/FK information
   - Machine-readable format for integration with other tools

2. **`table_descriptions.html`**
   - Interactive web viewer for browsing all table descriptions
   - Features:
     - Search functionality (by name or description)
     - Filter by table type (main/relationship)
     - Filter by PK presence
     - Statistics dashboard
     - Responsive design

3. **`generate_descriptions.py`**
   - Script that generated the descriptions
   - Can be rerun if new analysis data is available

## Description Quality

Descriptions are generated based on:
- **Table names** and naming conventions (tb* = main tables, rl* = relationships)
- **Column names** and patterns (CO_ = codes, NO_ = names, DT_ = dates, etc.)
- **Primary key analysis** (single vs composite keys)
- **Foreign key relationships** (what tables are connected)
- **CNES domain knowledge** (healthcare terminology and structures)

### Specific Descriptions for Key Tables

The generator includes specific, hand-crafted descriptions for important tables:
- `tbEstabelecimento` - Master establishment/facility table
- `tbDadosProfissionalSus` - Healthcare professionals master table
- `tbEquipe` - Healthcare teams (ESF, NASF, etc.)
- `tbMunicipio` - Brazilian municipalities reference
- `rlEstabEquipeProf` - Links establishments, teams, and professionals
- And many more...

### Generic Pattern-Based Descriptions

For tables without specific descriptions, the generator uses intelligent pattern matching:
- Junction tables describe what entities they link
- Type tables describe their classification purpose
- Service tables describe healthcare service offerings
- Equipment tables describe medical equipment tracking

## Table Categories

### Main Tables (71 tables)
- Store core data entities
- Examples: establishments, professionals, teams, equipment
- Typically have their own primary keys
- Referenced by relationship tables

### Relationship Tables (38 tables)
- Link multiple entities together
- Enable many-to-many relationships
- Often have composite primary keys
- Essential for understanding data connections

## Statistics

- **Total Tables**: 109
- **Total Rows**: ~27.8 million
- **Total Columns**: 959
- **Tables with PKs**: 95 (87%)
- **Tables without PKs**: 14 (13%)
- **Foreign Keys Detected**: 3,393

## Usage

### View in Browser
Open `table_descriptions.html` in any web browser to interactively explore all table descriptions.

### Query Programmatically
```python
import json

with open('table_descriptions.json') as f:
    data = json.load(f)

# Get specific table
estab_info = data['descriptions']['tbEstabelecimento202605.csv']
print(estab_info['description'])

# Find all main tables
main_tables = [
    t for t in data['descriptions'].values() 
    if t['type'] == 'main'
]

# Find large tables (>1M rows)
large_tables = [
    t for t in data['descriptions'].values() 
    if t['row_count'] > 1000000
]
```

### Search for Topics
```python
# Find all tables related to "equipment"
equipment_tables = [
    t for t in data['descriptions'].values()
    if 'equipment' in t['description'].lower()
]

# Find all tables about teams
team_tables = [
    t for t in data['descriptions'].values()
    if 'team' in t['description'].lower() or 'equipe' in t['table_name'].lower()
]
```

## Sample Descriptions

### Main Data Table
**tbEstabelecimento202605.csv** (623,208 rows, 56 columns)
> Master table containing comprehensive information about all registered health establishments (facilities) in Brazil. Stores administrative details, addresses, contact information, type of facility, legal status, and operational characteristics.

### Junction Table
**rlEstabEquipeProf202605.csv** (870,453 rows, 21 columns)
> Junction table linking health establishments, teams, and professionals. Maps which professionals work in which teams at which facilities, including their occupation code (CBO) and whether they serve SUS or private patients.

### Reference Table
**tbMunicipio202605.csv** (5,607 rows, 13 columns)
> Reference table of all Brazilian municipalities. Contains municipality codes, names, state associations, and administrative configurations for health system management.

### Lookup Table
**tbTipoEquipamento202605.csv** (12 rows, 2 columns)
> Reference/lookup table defining types or categories for TipoEquipamento. Provides standardized classifications used throughout the CNES system.

## Key Tables by Function

### Geographic
- `tbEstado` - Brazilian states
- `tbMunicipio` - Municipalities
- `tbArea` - Service areas
- `tbAldeia` - Indigenous villages

### Establishments
- `tbEstabelecimento` - Main facility data
- `tbTipoEstabelecimento` - Facility types
- `tbMantenedora` - Facility maintainers/managers

### Human Resources
- `tbDadosProfissionalSus` - Healthcare professionals
- `tbEquipe` - Healthcare teams
- `tbCargaHorariaSus` - Working hours
- `rlEstabEquipeProf` - Professional-team-facility links

### Equipment & Infrastructure
- `tbEquipamento` - Equipment types
- `rlEstabEquipamento` - Equipment at facilities
- `tbLeito` - Hospital beds

### Services
- `tbAtividade` - Healthcare activities
- `tbServicoEspecializado` - Specialized services
- `tbServicoApoio` - Support services

### Administrative
- `tbConvenio` - Insurance agreements
- `tbIncentivos` - Financial incentives
- `tbAvaliacao` - Quality evaluations

## Next Steps

1. **Database Design**: Use descriptions to understand table purposes when designing your database schema
2. **Documentation**: Include these descriptions in your database documentation
3. **ETL Planning**: Understand data flows and relationships for ETL processes
4. **Query Development**: Know which tables contain what information for query writing
5. **Data Quality**: Use relationship information to validate referential integrity

## Notes

- Descriptions are inferred from structure and naming patterns
- Some tables may have more nuanced purposes than described
- For authoritative definitions, consult official CNES documentation
- Table relationships detected automatically may need validation
- Orphaned records (FK violations) are documented in `relationships_report.json`
