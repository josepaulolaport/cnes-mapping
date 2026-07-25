#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

: "${DATABASE_URL:?Set DATABASE_URL in .env or environment}"

SQLITE_DB="${SQLITE_DB:-$ROOT/output/cnes_data.db}"
LOAD_FILE="$ROOT/scripts/migrate_sqlite_to_mcp_test.load"
LOAD_FILE_GENERATED="$ROOT/scripts/migrate_sqlite_to_mcp_test.generated.load"

if [[ ! -f "$SQLITE_DB" ]]; then
    echo "ERROR: SQLite database not found: $SQLITE_DB" >&2
    exit 1
fi

if ! command -v pgloader >/dev/null 2>&1; then
    echo "ERROR: pgloader not found. Install with: brew install pgloader" >&2
    exit 1
fi

echo "==> Phase 1: Apply mcp_test schema"
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql "$DATABASE_URL" -f sql/create_mcp_test_schema.sql

echo "==> Phase 2: Generate pgloader config from DATABASE_URL"
python3 - "$DATABASE_URL" "$SQLITE_DB" "$LOAD_FILE_GENERATED" <<'PY'
import sys
from urllib.parse import urlparse

db_url = sys.argv[1]
sqlite_path = sys.argv[2]
out_path = sys.argv[3]

parsed = urlparse(db_url)
pg_url = (
    f"postgresql://{parsed.username}:{parsed.password}@"
    f"{parsed.hostname}:{parsed.port or 5432}{parsed.path}"
)

tables = [
    "states", "municipalities", "facility_types", "deactivation_reasons",
    "service_specialties", "equipment_catalog", "professional_councils",
    "equipment_categories", "service_classifications", "facility_owners",
    "facilities", "professionals", "facility_professionals", "facility_services",
    "facility_equipment", "professional_workload",
]

cast_lines = [
    " CAST type datetime to timestamp using sqlite-timestamp-to-timestamp,",
    "      type integer to integer drop typemod,",
]
for table in tables:
    cast_lines.append(
        f"      column {table}.created_at to timestamp using sqlite-timestamp-to-timestamp,"
    )
    cast_lines.append(
        f"      column {table}.updated_at to timestamp using sqlite-timestamp-to-timestamp,"
    )
cast_lines.append("      type text to text drop typemod")

content = f"""LOAD DATABASE
     FROM sqlite:///{sqlite_path}
     INTO {pg_url}

 WITH data only,
      disable triggers,
      create no foreign keys,
      reset sequences

  SET maintenance_work_mem to '512MB',
      work_mem to '256MB',
      search_path to 'mcp_test, public'

{chr(10).join(cast_lines)}

 ALTER SCHEMA 'main' RENAME TO 'mcp_test';
"""

with open(out_path, "w") as f:
    f.write(content)
print(f"Generated {out_path}")
PY

echo "==> Phase 2: pgloader (data only)"
pgloader "$LOAD_FILE_GENERATED" 2>&1 | tee logs/mcp_test_migration.log

echo "==> Phase 3: Post-migration analyze + counts"
psql "$DATABASE_URL" -f sql/post_mcp_test_migration.sql

echo "==> Phase 3b: Clean orphans and apply foreign keys"
psql "$DATABASE_URL" -f sql/apply_mcp_test_foreign_keys.sql

echo "==> Phase 3: Create views"
psql "$DATABASE_URL" -f sql/create_mcp_test_views.sql

echo "==> Phase 1b: Apply read-only role"
psql "$DATABASE_URL" -f sql/mcp_test_roles.sql

echo "==> Phase 4: Generate schema manifest"
python3 scripts/generate_mcp_schema_manifest.py \
    --schema mcp_test \
    --database-url "$DATABASE_URL" \
    --output mcp/schema_manifest.json

echo "==> Done."
