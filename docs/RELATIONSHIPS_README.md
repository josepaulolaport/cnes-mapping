# CNES Relationship Analyzer

Enhanced analyzer that detects nullability, primary keys, and foreign key relationships in CNES database files.

## Features

### 1. Nullability Detection
- Analyzes all rows to determine if columns accept NULL values
- Treats empty strings (`""`) as NULL
- Reports null count and percentage for each column

### 2. Primary Key Detection
- Checks single-column and composite keys (up to 3 columns)
- Uses uniqueness testing and naming pattern scoring
- Detects composite keys common in relationship tables
- Confidence levels: high, medium

### 3. Foreign Key Detection (Hybrid Approach)
- **Phase 1**: Name-based matching (instant)
  - Matches column names across tables
  - Handles CNES naming conventions (CO_, NU_, etc.)
  
- **Phase 2**: Value sampling (10k rows per column)
  - Validates that values exist in referenced table
  - Filters false positives
  
- **Phase 3**: Match rate calculation
  - Reports actual match percentage
  - Detects orphaned records
  - Supports multiple FK references per column
  - Supports self-referential FKs (hierarchical data)

## Output Format

Creates `relationships_report.json` with:

```json
{
  "summary": {
    "total_tables": 109,
    "tables_with_primary_keys": 95,
    "total_foreign_keys_detected": 150,
    "warnings_count": 25
  },
  "tables": [
    {
      "filename": "tbMunicipio202605.csv",
      "primary_key": {
        "columns": ["CO_MUNICIPIO"],
        "is_composite": false,
        "uniqueness_rate": 1.0,
        "confidence": "high"
      },
      "columns": [
        {
          "column_name": "CO_MUNICIPIO",
          "nullable": false,
          "null_count": 0,
          "is_primary_key": true
        },
        {
          "column_name": "CO_ESTADO",
          "nullable": false,
          "is_foreign_key": true,
          "foreign_key_references": [
            {
              "table": "tbEstado202605.csv",
              "column": "CO_ESTADO",
              "match_rate": 1.0,
              "confidence": "high"
            }
          ]
        }
      ],
      "foreign_keys": [
        {
          "column": "CO_ESTADO",
          "references_table": "tbEstado202605.csv",
          "references_column": "CO_ESTADO",
          "match_rate": 1.0,
          "confidence": "high",
          "sample_size": 5570
        }
      ]
    }
  ],
  "warnings": [
    {
      "table": "rlEstabEquipe202605.csv",
      "column": "CO_UNIDADE",
      "severity": "medium",
      "issue": "Foreign key has 127 orphaned records (2.3% of sampled data)",
      "references": "tbEstabelecimento202605.csv.CO_UNIDADE",
      "sample_orphaned_values": ["9999999999999", "0000000000000"]
    }
  ]
}
```

## Usage

```bash
python3 analyze_relationships.py
```

## Analysis Process

The script runs in 3 phases:

**Phase 1: Loading Data** (2-3 minutes)
- Loads all 109 CSV files into memory
- Detects encoding and delimiters
- Total memory usage: ~5-6GB

**Phase 2: Structure Analysis** (10-15 minutes)
- Analyzes nullability for all columns
- Detects primary keys (1-3 column combinations)
- Marks PK columns

**Phase 3: Foreign Key Detection** (20-30 minutes)
- Builds indices for efficient lookup
- Name-based candidate matching
- Value sampling and validation (10k rows per column)
- Generates match rates and orphaned record reports

**Total Runtime: ~35-50 minutes**

## Key Improvements from Basic Analyzer

1. **Nullability tracking** - Essential for database schema design
2. **Primary key detection** - Automatically identifies unique identifiers
3. **Composite key support** - Handles many-to-many relationship tables
4. **Foreign key relationships** - Maps data relationships between tables
5. **Orphaned record detection** - Identifies data quality issues
6. **Multiple FK support** - Columns can reference multiple tables
7. **Self-referential FKs** - Detects hierarchical relationships
8. **Smart sampling** - Balances speed and accuracy

## Understanding the Results

### Confidence Levels

- **High**: Match rate ≥ 95% and strong naming patterns
- **Medium**: Match rate 80-95% or weaker naming patterns

### Primary Keys in Relationship Tables

Many `rl*` (relationship) tables have composite primary keys that are also foreign keys:

```
rlEstabEquipe:
  PK: (CO_UNIDADE, CO_EQUIPE)  ← Composite PK
  FK: CO_UNIDADE → tbEstabelecimento.CO_UNIDADE
  FK: CO_EQUIPE → tbEquipe.CO_EQUIPE
```

This is normal for many-to-many relationships!

### Orphaned Records

Records with FK values that don't exist in the referenced table. Common causes:
- Data quality issues
- Soft deletes (referenced record was deleted)
- Referential integrity not enforced
- Timing issues in data export

### Warnings

- **High severity**: No PK detected, or >5% orphaned records
- **Medium severity**: 0-5% orphaned records

## Memory Considerations

The analyzer loads all data into memory for performance. With 27M+ rows:
- Estimated memory usage: 5-6GB RAM
- If you run out of memory, close other applications
- Alternative: Run on a machine with more RAM

## Next Steps for Database Design

1. Review `relationships_report.json`
2. Validate detected PKs and FKs (especially medium confidence)
3. Investigate tables without PKs
4. Review orphaned records warnings
5. Design database schema based on relationships
6. Create DDL statements with proper constraints
7. Plan data cleaning for orphaned records

## Technical Notes

- Uses random sampling (10k rows) for FK validation
- Self-referential FKs enabled (finds parent-child relationships)
- PK columns can also be FKs (junction tables)
- Empty strings treated as NULL
- Match threshold: 80% for FK detection
- Supports CNES naming conventions: CO_, NU_, ID_, DS_, TP_, ST_, DT_, NO_
