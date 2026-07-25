-- Incremental migration: facility_representatives (rlEstabRepresentante)
-- Apply: psql "$DATABASE_URL" -f sql/add_facility_representatives.sql

SET search_path TO mcp_test, public;

CREATE TABLE IF NOT EXISTS facility_representatives (
    facility_id TEXT PRIMARY KEY,
    representative_name TEXT NOT NULL,
    role_title TEXT,
    email TEXT,
    tax_id TEXT,
    updated_by_user TEXT,
    last_updated_date TEXT,
    origin_updated_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
);

COMMENT ON TABLE facility_representatives IS 'Official legal representatives at facilities. From rlEstabRepresentante.';
COMMENT ON COLUMN facility_representatives.tax_id IS 'CPF when provided; CNES often masks as literal CO_CPF (stored NULL).';

CREATE INDEX IF NOT EXISTS idx_facility_representatives_name ON facility_representatives(representative_name);
CREATE INDEX IF NOT EXISTS idx_facility_representatives_email ON facility_representatives(email)
    WHERE email IS NOT NULL AND email <> '';
