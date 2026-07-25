#!/usr/bin/env bash
# Load CNES CSV data directly into PostgreSQL (mcp_test schema).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${DATABASE_URL:?Set DATABASE_URL in .env or environment}"
DB_URL="$DATABASE_URL"
SCHEMA="${CNES_SCHEMA:-mcp_test}"
CSV_DIR="${CNES_CSV_DIR:-$ROOT/BASE_DE_DADOS_CNES_202605}"

mkdir -p logs import_errors

echo "==> Recreating PostgreSQL schema: $SCHEMA"
psql "$DB_URL" -f sql/create_mcp_test_schema.sql

echo "==> Importing all tables from CSV into $SCHEMA"
cd scripts
python3 import_modular.py \
  --csv-dir "$CSV_DIR" \
  --db-url "$DB_URL" \
  --schema "$SCHEMA" \
  --table all \
  --force \
  2>&1 | tee ../logs/postgres_csv_import.log

echo "==> Row counts"
psql "$DB_URL" -c "
SET search_path TO $SCHEMA, public;
SELECT 'states' AS tbl, COUNT(*) FROM states
UNION ALL SELECT 'municipalities', COUNT(*) FROM municipalities
UNION ALL SELECT 'facilities', COUNT(*) FROM facilities
UNION ALL SELECT 'professionals', COUNT(*) FROM professionals
UNION ALL SELECT 'facility_professionals', COUNT(*) FROM facility_professionals
UNION ALL SELECT 'facility_services', COUNT(*) FROM facility_services
UNION ALL SELECT 'facility_equipment', COUNT(*) FROM facility_equipment
UNION ALL SELECT 'professional_workload', COUNT(*) FROM professional_workload
ORDER BY 1;
"

echo "==> Done. Log: logs/postgres_csv_import.log"
