import { spawn } from "child_process";
import { randomUUID } from "crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";
import { SCHEMA } from "../db.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MCP_ROOT = resolve(__dirname, "../..");
const RUNS_DIR = join(MCP_ROOT, "analysis_runs");
const RUNTIME_PATH = join(MCP_ROOT, "analysis", "runtime.py");
const MAX_CODE_LENGTH = 50_000;
const TIMEOUT_MS = 300_000;

const FORBIDDEN_PATTERNS = [
  /\bos\.system\b/i,
  /\bsubprocess\b/i,
  /\beval\s*\(/i,
  /\bexec\s*\(/i,
  /\b__import__\s*\(/i,
  /\bimportlib\b/i,
  /\bsocket\b/i,
  /\brequests\b/i,
  /\burllib\b/i,
  /\bhttpx\b/i,
  /\bshutil\.rmtree\b/i,
  /\bos\.remove\b/i,
  /\bos\.unlink\b/i,
];

export interface RunAnalysisInput {
  code: string;
  description?: string;
  output_format?: "text" | "excel" | "csv" | "json" | "auto";
}

export interface RunAnalysisResult {
  run_id: string;
  description: string;
  status: "success" | "error";
  stdout: string;
  stderr: string;
  artifacts: Array<{ path: string; absolute_path: string; size_bytes: number }>;
  output_dir: string;
  duration_ms: number;
}

function validateCode(code: string): void {
  if (!code.trim()) throw new Error("Analysis code cannot be empty");
  if (code.length > MAX_CODE_LENGTH) {
    throw new Error(`Analysis code exceeds ${MAX_CODE_LENGTH} characters`);
  }
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (pattern.test(code)) {
      throw new Error(`Forbidden construct in analysis code: ${pattern.source}`);
    }
  }
}

function dedent(code: string): string {
  const lines = code.replace(/\r\n/g, "\n").split("\n");
  const indents = lines
    .filter((l) => l.trim().length > 0)
    .map((l) => l.match(/^(\s*)/)?.[1].length ?? 0);
  if (indents.length === 0) return code.trim();

  let strip = Math.min(...indents);
  // When first line is flush-left but body is indented (common from AI/chat), strip body indent.
  if (strip === 0) {
    const nonZero = indents.filter((i) => i > 0);
    if (nonZero.length > 0) strip = Math.min(...nonZero);
  }

  return lines
    .map((l) => {
      if (!l.trim()) return "";
      const lead = l.match(/^(\s*)/)?.[1].length ?? 0;
      return lead >= strip ? l.slice(strip) : l;
    })
    .join("\n")
    .trim();
}

function buildScript(userCode: string): string {
  const code = dedent(userCode);
  return `# Auto-generated CNES analysis script
import textwrap
from runtime import (
    query, save_excel, save_csv, save_json, write_report,
    print_summary, OUTPUT_DIR, SCHEMA, ARTIFACTS
)

_user_script = ${JSON.stringify(code)}
exec(compile(textwrap.dedent(_user_script), "<analysis>", "exec"), globals())

# Write manifest of artifacts for the MCP runner
import json
from pathlib import Path
(Path(OUTPUT_DIR) / "artifacts.json").write_text(
    json.dumps({"artifacts": ARTIFACTS}, indent=2), encoding="utf-8"
)
`;
}

function findPython(): string {
  return process.env.ANALYSIS_PYTHON || "python3";
}

export async function runAnalysis(input: RunAnalysisInput): Promise<RunAnalysisResult> {
  validateCode(input.code);

  if (!existsSync(RUNTIME_PATH)) {
    throw new Error(`Analysis runtime not found: ${RUNTIME_PATH}`);
  }

  const runId = randomUUID().slice(0, 8);
  const outputDir = join(RUNS_DIR, runId);
  mkdirSync(outputDir, { recursive: true });

  const scriptPath = join(outputDir, "analysis.py");
  writeFileSync(scriptPath, buildScript(input.code), "utf-8");

  const dbUrl = process.env.CNES_DATABASE_URL || process.env.MCP_TEST_DATABASE_URL;
  if (!dbUrl) throw new Error("CNES_DATABASE_URL not configured");

  const start = Date.now();
  const { stdout, stderr, exitCode } = await execPython(scriptPath, outputDir, dbUrl);
  const durationMs = Date.now() - start;

  const artifacts = collectArtifacts(outputDir);

  return {
    run_id: runId,
    description: input.description || "CNES analysis",
    status: exitCode === 0 ? "success" : "error",
    stdout: truncate(stdout, 32_000),
    stderr: truncate(stderr, 16_000),
    artifacts,
    output_dir: outputDir,
    duration_ms: durationMs,
  };
}

function execPython(
  scriptPath: string,
  outputDir: string,
  dbUrl: string
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return new Promise((resolvePromise) => {
    const python = findPython();
    const proc = spawn(
      python,
      [scriptPath],
      {
        cwd: outputDir,
        env: {
          ...process.env,
          PYTHONPATH: join(MCP_ROOT, "analysis"),
          ANALYSIS_OUTPUT_DIR: outputDir,
          CNES_DATABASE_URL: dbUrl,
          CNES_SCHEMA: SCHEMA,
          PYTHONDONTWRITEBYTECODE: "1",
        },
      }
    );

    let stdout = "";
    let stderr = "";
    let killed = false;

    const timer = setTimeout(() => {
      killed = true;
      proc.kill("SIGTERM");
    }, TIMEOUT_MS);

    proc.stdout.on("data", (d) => { stdout += d.toString(); });
    proc.stderr.on("data", (d) => { stderr += d.toString(); });

    proc.on("close", (code) => {
      clearTimeout(timer);
      if (killed) {
        stderr += `\nAnalysis timed out after ${TIMEOUT_MS / 1000}s`;
      }
      resolvePromise({ stdout, stderr, exitCode: killed ? 1 : (code ?? 1) });
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      resolvePromise({ stdout, stderr: err.message, exitCode: 1 });
    });
  });
}

function collectArtifacts(outputDir: string): RunAnalysisResult["artifacts"] {
  const manifestPath = join(outputDir, "artifacts.json");
  const paths: string[] = [];

  if (existsSync(manifestPath)) {
    try {
      const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as { artifacts?: string[] };
      paths.push(...(manifest.artifacts || []));
    } catch {
      /* scan directory below */
    }
  }

  if (paths.length === 0) {
    for (const name of readdirSync(outputDir)) {
      if (name === "analysis.py" || name === "artifacts.json") continue;
      paths.push(name);
    }
  }

  return paths.map((rel) => {
    const abs = join(outputDir, rel);
    const size = existsSync(abs) ? statSync(abs).size : 0;
    return { path: rel, absolute_path: abs, size_bytes: size };
  });
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s;
  return s.slice(0, max) + `\n... [truncated ${s.length - max} chars]`;
}

export function listAnalysisRuns(limit = 20): Array<{
  run_id: string;
  created_at: string;
  artifacts: string[];
}> {
  if (!existsSync(RUNS_DIR)) return [];

  const runs = readdirSync(RUNS_DIR)
    .filter((d) => statSync(join(RUNS_DIR, d)).isDirectory())
    .map((runId) => {
      const dir = join(RUNS_DIR, runId);
      const stat = statSync(dir);
      const artifacts = readdirSync(dir).filter(
        (f) => !f.endsWith(".py") && f !== "artifacts.json"
      );
      return {
        run_id: runId,
        created_at: stat.mtime.toISOString(),
        artifacts,
      };
    })
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit);

  return runs;
}

export function getAnalysisGuide(): object {
  return {
    purpose:
      "For deep analysis over large CNES datasets, write Python code instead of pulling rows via execute_query.",
    when_to_use: [
      "Aggregations (GROUP BY, COUNT, SUM) over millions of rows",
      "Multi-step analysis pipelines",
      "Export to Excel/CSV for the user",
      "Statistical summaries that would exceed token limits",
    ],
    when_not_to_use: [
      "Simple lookups under 500 rows — use execute_query",
      "Schema exploration — use describe_table",
    ],
    helpers: {
      query: "query('SELECT ...') -> pandas DataFrame. Read-only SELECT only.",
      save_excel: "save_excel(df, 'report.xlsx') -> path. Use when user wants Excel.",
      save_csv: "save_csv(df, 'report.csv') -> path",
      save_json: "save_json({'key': value}, 'summary.json') -> path",
      write_report: "write_report('# Title\\n...', 'report.md') -> path for narrative analysis",
      print_summary: "print_summary('Title', df) -> prints compact preview to stdout",
    },
    rules: [
      "Active facility: deactivation_reason_code IS NULL",
      "Active professional link: termination_date IS NULL",
      `Schema: ${SCHEMA} (tables are in search_path)`,
      "Always aggregate in SQL when possible before loading into pandas",
      "Use save_excel() when user asks for spreadsheet output",
      "Use write_report() + print_summary() for written analysis",
    ],
    example_excel: `df = query("""
  SELECT s.state_code, COUNT(*) AS active_facilities
  FROM facilities f
  JOIN municipalities m ON f.municipality_id = m.municipality_id
  JOIN states s ON m.state_code = s.state_code
  WHERE f.deactivation_reason_code IS NULL
  GROUP BY s.state_code
  ORDER BY active_facilities DESC
""")
save_excel(df, "active_facilities_by_state.xlsx")
print_summary("Active facilities by state", df)`,
    example_report: `df = query("""
  SELECT ft.facility_type_name, COUNT(*) AS cnt
  FROM facilities f
  JOIN facility_types ft ON f.facility_type_code = ft.facility_type_code
  WHERE f.deactivation_reason_code IS NULL
  GROUP BY ft.facility_type_name
  ORDER BY cnt DESC
  LIMIT 20
""")
report = "# Top facility types (active)\\n\\n" + df.to_string(index=False)
write_report(report)
print_summary("Top facility types", df)`,
    dependencies: "Requires: pip install -r mcp/requirements-analysis.txt",
  };
}
