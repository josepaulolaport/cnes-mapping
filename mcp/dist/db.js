import pg from "pg";
import { readFileSync, existsSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
const __dirname = dirname(fileURLToPath(import.meta.url));
export const SCHEMA = "mcp_test";
export function getPool() {
    const url = process.env.CNES_DATABASE_URL || process.env.MCP_TEST_DATABASE_URL;
    if (!url) {
        throw new Error("CNES_DATABASE_URL or MCP_TEST_DATABASE_URL must be set");
    }
    return new pg.Pool({ connectionString: url, max: 5 });
}
export async function withClient(fn) {
    const pool = getPool();
    const client = await pool.connect();
    try {
        await client.query(`SET search_path TO ${SCHEMA}, public`);
        await client.query("SET statement_timeout = '30s'");
        return await fn(client);
    }
    finally {
        client.release();
        await pool.end();
    }
}
export function loadManifest() {
    const path = join(__dirname, "..", "schema_manifest.json");
    if (!existsSync(path))
        return null;
    return JSON.parse(readFileSync(path, "utf-8"));
}
