-- ============================================================================
-- MCP TEST READ-ONLY ROLE
-- Run as superuser or schema owner after schema + data + views are loaded.
-- Re-run after creating new views (ALL TABLES picks up existing tables + views).
-- ============================================================================

SET search_path TO mcp_test, public;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mcp_test_reader') THEN
        CREATE ROLE mcp_test_reader LOGIN PASSWORD 'mcp_test_reader_change_me';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA mcp_test TO mcp_test_reader;

-- Includes all tables AND views currently in the schema (no need to list views by name).
GRANT SELECT ON ALL TABLES IN SCHEMA mcp_test TO mcp_test_reader;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA mcp_test FROM mcp_test_reader;

-- Future tables/views created by this role in mcp_test.
ALTER DEFAULT PRIVILEGES IN SCHEMA mcp_test
    GRANT SELECT ON TABLES TO mcp_test_reader;
