import { SCHEMA } from "../db.js";
const FORBIDDEN = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "GRANT", "REVOKE", "COPY", "CREATE", "REPLACE", "MERGE",
    "CALL", "EXECUTE", "DO", "SET", "RESET",
];
export function validateSelectQuery(sql) {
    const trimmed = sql.trim().replace(/;+\s*$/, "");
    const upper = trimmed.toUpperCase();
    if (!upper.startsWith("SELECT") && !upper.startsWith("WITH")) {
        throw new Error("Only SELECT queries (including WITH/CTE) are allowed");
    }
    for (const kw of FORBIDDEN) {
        const re = new RegExp(`\\b${kw}\\b`, "i");
        if (re.test(trimmed)) {
            throw new Error(`Forbidden keyword in query: ${kw}`);
        }
    }
    if (!/\bLIMIT\s+\d+/i.test(trimmed)) {
        return `${trimmed} LIMIT 500`;
    }
    return trimmed;
}
export async function listTables(client) {
    const result = await client.query(`
    SELECT
      t.table_name,
      t.table_type,
      obj_description((quote_ident(t.table_schema)||'.'||quote_ident(t.table_name))::regclass) AS description,
      (SELECT COUNT(*)::text FROM information_schema.columns c
       WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name) AS column_count
    FROM information_schema.tables t
    WHERE t.table_schema = $1
    ORDER BY t.table_type, t.table_name
    `, [SCHEMA]);
    const counts = {};
    for (const row of result.rows) {
        try {
            const c = await client.query(`SELECT COUNT(*)::int AS n FROM "${SCHEMA}"."${row.table_name}"`);
            counts[row.table_name] = c.rows[0].n;
        }
        catch {
            counts[row.table_name] = -1;
        }
    }
    return result.rows.map((r) => ({
        name: r.table_name,
        type: r.table_type === "VIEW" ? "view" : "table",
        description: r.description || "",
        column_count: Number(r.column_count),
        row_count: counts[r.table_name],
    }));
}
export async function describeTable(client, tableName) {
    const safeName = tableName.replace(/[^a-z0-9_]/gi, "");
    const meta = await client.query(`
    SELECT column_name, data_type, is_nullable, column_default,
           col_description((quote_ident($1)||'.'||quote_ident($2))::regclass, ordinal_position) AS comment
    FROM information_schema.columns
    WHERE table_schema = $1 AND table_name = $2
    ORDER BY ordinal_position
    `, [SCHEMA, safeName]);
    if (meta.rows.length === 0) {
        throw new Error(`Table or view not found: ${SCHEMA}.${safeName}`);
    }
    const pk = await client.query(`
    SELECT a.attname
    FROM pg_index i
    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
    JOIN pg_class c ON c.oid = i.indrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE i.indisprimary AND n.nspname = $1 AND c.relname = $2
    `, [SCHEMA, safeName]);
    const fks = await client.query(`
    SELECT kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = $1 AND tc.table_name = $2
    `, [SCHEMA, safeName]);
    const countResult = await client.query(`SELECT COUNT(*)::int AS n FROM "${SCHEMA}"."${safeName}"`);
    let sampleRows = [];
    try {
        const sample = await client.query(`SELECT * FROM "${SCHEMA}"."${safeName}" LIMIT 3`);
        sampleRows = sample.rows;
    }
    catch {
        sampleRows = [];
    }
    const tableComment = await client.query(`SELECT obj_description((quote_ident($1)||'.'||quote_ident($2))::regclass) AS comment`, [SCHEMA, safeName]);
    return {
        schema: SCHEMA,
        table: safeName,
        description: tableComment.rows[0]?.comment || "",
        row_count: countResult.rows[0].n,
        primary_key: pk.rows.map((r) => r.attname),
        foreign_keys: fks.rows.map((r) => ({
            column: r.column_name,
            references: `${r.foreign_table}.${r.foreign_column}`,
        })),
        columns: meta.rows.map((r) => ({
            name: r.column_name,
            type: r.data_type,
            nullable: r.is_nullable === "YES",
            default: r.column_default,
            comment: r.comment || "",
        })),
        sample_rows: sampleRows,
    };
}
export async function getRelationships(client, tableName) {
    const params = [SCHEMA];
    let filter = "";
    if (tableName) {
        const safe = tableName.replace(/[^a-z0-9_]/gi, "");
        filter = "AND tc.table_name = $2";
        params.push(safe);
    }
    const result = await client.query(`
    SELECT
      tc.table_name AS from_table,
      kcu.column_name AS from_column,
      ccu.table_name AS to_table,
      ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
      ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = $1
      ${filter}
    ORDER BY tc.table_name, kcu.column_name
    `, params);
    return result.rows.map((r) => ({
        from: `${r.from_table}.${r.from_column}`,
        to: `${r.to_table}.${r.to_column}`,
        join: `${r.from_table}.${r.from_column} = ${r.to_table}.${r.to_column}`,
    }));
}
export async function searchSchema(client, keyword) {
    const pattern = `%${keyword}%`;
    const tables = await client.query(`
    SELECT table_name, obj_description((quote_ident($1)||'.'||quote_ident(table_name))::regclass) AS description
    FROM information_schema.tables
    WHERE table_schema = $1
      AND (table_name ILIKE $2 OR obj_description((quote_ident($1)||'.'||quote_ident(table_name))::regclass) ILIKE $2)
    `, [SCHEMA, pattern]);
    const columns = await client.query(`
    SELECT c.table_name, c.column_name, c.data_type,
           col_description((quote_ident($1)||'.'||quote_ident(c.table_name))::regclass, c.ordinal_position) AS comment
    FROM information_schema.columns c
    WHERE c.table_schema = $1
      AND (c.column_name ILIKE $2 OR col_description((quote_ident($1)||'.'||quote_ident(c.table_name))::regclass, c.ordinal_position) ILIKE $2)
    LIMIT 50
    `, [SCHEMA, pattern]);
    return { tables: tables.rows, columns: columns.rows };
}
export async function executeQuery(client, sql) {
    const safeSql = validateSelectQuery(sql);
    const result = await client.query(safeSql);
    return {
        row_count: result.rowCount,
        columns: result.fields.map((f) => f.name),
        rows: result.rows,
    };
}
