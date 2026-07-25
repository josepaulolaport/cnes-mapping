import pg from "pg";
import { readFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export const SCHEMA = "mcp_test";

export function getPool(): pg.Pool {
  const url = process.env.CNES_DATABASE_URL || process.env.MCP_TEST_DATABASE_URL;
  if (!url) {
    throw new Error("CNES_DATABASE_URL or MCP_TEST_DATABASE_URL must be set");
  }
  return new pg.Pool({ connectionString: url, max: 5 });
}

export async function withClient<T>(fn: (client: pg.PoolClient) => Promise<T>): Promise<T> {
  const pool = getPool();
  const client = await pool.connect();
  try {
    await client.query(`SET search_path TO ${SCHEMA}, public`);
    await client.query("SET statement_timeout = '30s'");
    return await fn(client);
  } finally {
    client.release();
    await pool.end();
  }
}

export interface SchemaManifest {
  schema: string;
  domain: string;
  critical_rules: string[];
  tables: Record<string, ManifestEntry>;
  views: Record<string, ManifestEntry>;
}

export interface ManifestEntry {
  type?: string;
  description?: string;
  row_count?: number;
  primary_key?: string[];
  foreign_keys?: Array<{ column: string; references: string }>;
  columns?: Array<{ name: string; type: string; nullable: boolean; comment: string }>;
  joins?: Record<string, string>;
  common_filters?: string[];
  example_queries?: string[];
  use_when?: string;
}

export function loadManifest(): SchemaManifest | null {
  const path = join(__dirname, "..", "schema_manifest.json");
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, "utf-8")) as SchemaManifest;
}
