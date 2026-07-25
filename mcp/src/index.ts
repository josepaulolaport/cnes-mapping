import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListResourcesRequestSchema,
  ListToolsRequestSchema,
  ReadResourceRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { withClient, loadManifest, SCHEMA } from "./db.js";
import {
  listTables,
  describeTable,
  getRelationships,
  searchSchema,
  executeQuery,
} from "./tools/queries.js";
import {
  runAnalysis,
  listAnalysisRuns,
  getAnalysisGuide,
  type RunAnalysisInput,
} from "./tools/analysisRunner.js";
import {
  assessRequest,
  buildServerInstructions,
  formatAgentPolicyMarkdown,
} from "./agentPolicy.js";

const server = new Server(
  { name: "cnes-mcp-test", version: "1.0.0" },
  {
    capabilities: { tools: {}, resources: {} },
    instructions: buildServerInstructions(),
  }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "get_agent_policy",
      description:
        "Full operating rules: when to ask clarifying questions, execute_query vs run_analysis, CNES filters. " +
        "Call this first on complex or ambiguous requests.",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "assess_request",
      description:
        "Given the user's natural-language request, return clarifying questions to ask, recommended tool, " +
        "and a suggested plan. Call BEFORE execute_query or run_analysis when the request is non-trivial.",
      inputSchema: {
        type: "object",
        properties: {
          user_request: { type: "string", description: "The user's question or analysis request" },
          known_context: {
            type: "string",
            description: "Optional context already established (e.g. 'SP only, active facilities')",
          },
        },
        required: ["user_request"],
      },
    },
    {
      name: "list_tables",
      description: "List all tables and views in mcp_test schema with row counts and descriptions",
      inputSchema: { type: "object", properties: {} },
    },
    {
      name: "describe_table",
      description: "Full metadata for a table or view: columns, types, PK, FKs, comments, sample rows",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Table or view name (e.g. facilities)" },
        },
        required: ["table_name"],
      },
    },
    {
      name: "get_relationships",
      description: "Foreign key relationships in mcp_test schema, optionally filtered by table",
      inputSchema: {
        type: "object",
        properties: {
          table_name: { type: "string", description: "Optional table name filter" },
        },
      },
    },
    {
      name: "search_schema",
      description: "Search table and column names/descriptions by keyword",
      inputSchema: {
        type: "object",
        properties: {
          keyword: { type: "string", description: "Search term (e.g. equipment, deactivation)" },
        },
        required: ["keyword"],
      },
    },
    {
      name: "execute_query",
      description:
        "Run a read-only SELECT against mcp_test (auto-LIMIT 500). ONLY for small lookups: samples, " +
        "single-entity search, sanity checks. NOT for GROUP BY over large tables or exports — use run_analysis. " +
        "If scope/format is unclear, call assess_request first.",
      inputSchema: {
        type: "object",
        properties: {
          sql: { type: "string", description: "SELECT query (schema: mcp_test)" },
        },
        required: ["sql"],
      },
    },
    {
      name: "run_analysis",
      description:
        "Python analysis runner (pandas + read-only SQL). Use for aggregations, rankings, multi-step analysis, " +
        "and Excel/CSV/report exports. NOT for simple ≤500-row lookups (use execute_query). " +
        "Before running: call assess_request if unclear; state a brief plan; call get_analysis_guide for helpers.",
      inputSchema: {
        type: "object",
        properties: {
          code: {
            type: "string",
            description: "Python code body using query(), save_excel(), write_report(), etc.",
          },
          description: {
            type: "string",
            description: "Short label for this analysis run",
          },
          output_format: {
            type: "string",
            enum: ["text", "excel", "csv", "json", "auto"],
            description: "Hint for expected output (code should call matching save_* helper)",
          },
        },
        required: ["code"],
      },
    },
    {
      name: "list_analysis_runs",
      description: "List recent analysis runs and their output artifact files",
      inputSchema: {
        type: "object",
        properties: {
          limit: { type: "number", description: "Max runs to return (default 20)" },
        },
      },
    },
    {
      name: "get_analysis_guide",
      description:
        "Documentation for writing analysis code: helpers, rules, and examples for Excel vs written reports",
      inputSchema: { type: "object", properties: {} },
    },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    if (name === "get_agent_policy") {
      return { content: [{ type: "text", text: formatAgentPolicyMarkdown() }] };
    }

    if (name === "assess_request") {
      const a = args as { user_request?: string; known_context?: string };
      const result = assessRequest({
        user_request: String(a?.user_request || ""),
        known_context: a?.known_context,
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }

    if (name === "list_tables") {
      const data = await withClient(listTables);
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }

    if (name === "describe_table") {
      const tableName = String((args as { table_name?: string })?.table_name || "");
      const data = await withClient((c) => describeTable(c, tableName));
      const manifest = loadManifest();
      const extra = manifest?.tables[tableName] || manifest?.views[tableName];
      const merged = extra ? { ...data, manifest: extra } : data;
      return { content: [{ type: "text", text: JSON.stringify(merged, null, 2) }] };
    }

    if (name === "get_relationships") {
      const tableName = (args as { table_name?: string })?.table_name;
      const data = await withClient((c) => getRelationships(c, tableName));
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }

    if (name === "search_schema") {
      const keyword = String((args as { keyword?: string })?.keyword || "");
      const data = await withClient((c) => searchSchema(c, keyword));
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }

    if (name === "execute_query") {
      const sql = String((args as { sql?: string })?.sql || "");
      const data = await withClient((c) => executeQuery(c, sql));
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }

    if (name === "run_analysis") {
      const a = args as { code?: string; description?: string; output_format?: string };
      const result = await runAnalysis({
        code: String(a?.code || ""),
        description: a?.description,
        output_format: a?.output_format as RunAnalysisInput["output_format"],
      });
      return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
    }

    if (name === "list_analysis_runs") {
      const limit = Number((args as { limit?: number })?.limit) || 20;
      const data = listAnalysisRuns(limit);
      return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
    }

    if (name === "get_analysis_guide") {
      return { content: [{ type: "text", text: JSON.stringify(getAnalysisGuide(), null, 2) }] };
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { content: [{ type: "text", text: `Error: ${message}` }], isError: true };
  }
});

server.setRequestHandler(ListResourcesRequestSchema, async () => {
  const manifest = loadManifest();
  const resources = [
    {
      uri: "schema://overview",
      name: "Schema Overview",
      description: "CNES mcp_test domain summary and critical query rules",
      mimeType: "application/json",
    },
    {
      uri: "schema://sample-queries",
      name: "Sample Queries",
      description: "Example SQL queries for common sales use cases",
      mimeType: "application/json",
    },
    {
      uri: "analysis://guide",
      name: "Analysis Code Guide",
      description: "How to write Python analysis scripts for deep dives and Excel exports",
      mimeType: "application/json",
    },
    {
      uri: "policy://agent",
      name: "Agent Policy",
      description: "When to ask clarifying questions and how to choose execute_query vs run_analysis",
      mimeType: "text/markdown",
    },
  ];

  if (manifest) {
    for (const name of Object.keys(manifest.tables)) {
      resources.push({
        uri: `schema://table/${name}`,
        name: `Table: ${name}`,
        description: manifest.tables[name].description || "",
        mimeType: "application/json",
      });
    }
    for (const name of Object.keys(manifest.views)) {
      resources.push({
        uri: `schema://view/${name}`,
        name: `View: ${name}`,
        description: manifest.views[name].description || "",
        mimeType: "application/json",
      });
    }
  }

  return { resources };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const manifest = loadManifest();
  const uri = request.params.uri;

  if (uri === "schema://overview") {
    const overview = {
      schema: SCHEMA,
      domain: manifest?.domain || "Brazilian CNES health registry",
      critical_rules: manifest?.critical_rules || [
        "Active facility: deactivation_reason_code IS NULL",
        "Active professional: termination_date IS NULL",
      ],
      tables: manifest ? Object.keys(manifest.tables) : [],
      views: manifest ? Object.keys(manifest.views) : [],
    };
    return {
      contents: [{ uri, mimeType: "application/json", text: JSON.stringify(overview, null, 2) }],
    };
  }

  if (uri === "schema://sample-queries") {
    const queries = manifest
      ? Object.fromEntries(
          [...Object.entries(manifest.tables), ...Object.entries(manifest.views)]
            .filter(([, v]) => v.example_queries?.length)
            .map(([k, v]) => [k, v.example_queries])
        )
      : {};
    return {
      contents: [{ uri, mimeType: "application/json", text: JSON.stringify(queries, null, 2) }],
    };
  }

  if (uri === "analysis://guide") {
    return {
      contents: [{ uri, mimeType: "application/json", text: JSON.stringify(getAnalysisGuide(), null, 2) }],
    };
  }

  if (uri === "policy://agent") {
    return {
      contents: [{ uri, mimeType: "text/markdown", text: formatAgentPolicyMarkdown() }],
    };
  }

  const tableMatch = uri.match(/^schema:\/\/table\/(.+)$/);
  if (tableMatch && manifest?.tables[tableMatch[1]]) {
    return {
      contents: [{
        uri,
        mimeType: "application/json",
        text: JSON.stringify(manifest.tables[tableMatch[1]], null, 2),
      }],
    };
  }

  const viewMatch = uri.match(/^schema:\/\/view\/(.+)$/);
  if (viewMatch && manifest?.views[viewMatch[1]]) {
    return {
      contents: [{
        uri,
        mimeType: "application/json",
        text: JSON.stringify(manifest.views[viewMatch[1]], null, 2),
      }],
    };
  }

  throw new Error(`Resource not found: ${uri}`);
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
