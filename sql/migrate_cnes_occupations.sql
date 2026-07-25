-- ============================================================================
-- Add occupations (CBO) lookup from tbAtividadeProfissional
-- Run BEFORE import; FKs applied via apply_mcp_test_foreign_keys.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

SET search_path TO mcp_test, public;

CREATE TABLE IF NOT EXISTS occupations (
    occupation_code TEXT PRIMARY KEY,
    occupation_name TEXT NOT NULL,
    professional_classification TEXT,
    is_health_occupation TEXT,
    is_regulated TEXT,
    reference_year TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE occupations IS 'CBO occupation/specialty lookup. From tbAtividadeProfissional.';
COMMENT ON COLUMN occupations.occupation_code IS 'Brazilian CBO code (CO_CBO)';
COMMENT ON COLUMN occupations.occupation_name IS 'Occupation label (DS_ATIVIDADE_PROFISSIONAL)';
COMMENT ON COLUMN occupations.is_health_occupation IS 'S=health occupation, N=non-health (TP_CBO_SAUDE)';

CREATE INDEX IF NOT EXISTS idx_occupations_name_trgm
    ON occupations USING gin (occupation_name gin_trgm_ops);
