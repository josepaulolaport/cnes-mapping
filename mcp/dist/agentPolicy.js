/**
 * Operating policy injected into MCP server instructions and get_agent_policy tool.
 * Claude Code / Cursor read this on every session via MCP initialize + tool call.
 */
export const AGENT_POLICY = {
    role: "CNES Brazil health registry analyst (mcp_test schema)",
    mandatory_clarifications: {
        rule: "If ANY item below is unclear, ask the user BEFORE querying or running analysis. Do not guess.",
        ask_when: [
            {
                topic: "Geographic scope",
                examples: ["Which state(s) or municipality?", "All Brazil or a region?"],
                triggers: ["User says 'hospitals' or 'facilities' without state/city", "Ambiguous place names"],
            },
            {
                topic: "Active vs all records",
                examples: ["Only active facilities (open)?", "Include deactivated?"],
                triggers: ["Sales/targeting questions default to ACTIVE unless user says otherwise"],
                default_if_silent: "Active only: deactivation_reason_code IS NULL; employed staff: termination_date IS NULL",
            },
            {
                topic: "Output format (for non-trivial analysis)",
                examples: ["Excel file, written summary, or quick answer in chat?"],
                triggers: ["Deep analysis", "Export", "Report", "Large result set", "Comparison across regions"],
            },
            {
                topic: "Entity definition",
                examples: ["Hospital = which facility_type_code?", "Doctor = which occupation_code/CBO?"],
                triggers: ["User says hospital/clinic/pharmacy/doctor without specifying CNES classification"],
            },
            {
                topic: "Equipment or service type",
                examples: ["Which equipment (ultrasound, MRI)?", "Search by name or code?"],
                triggers: ["Equipment-based targeting without specific type"],
            },
            {
                topic: "Analysis depth vs speed",
                examples: ["Quick approximate answer or full export?"],
                triggers: ["Broad questions like 'analyze the market in SP'"],
            },
        ],
    },
    tool_selection: {
        decision_order: [
            "1. Unclear request → ask user (see mandatory_clarifications). Do NOT run tools yet.",
            "2. Schema unknown → describe_table / search_schema / get_relationships",
            "3. Small lookup (expect ≤500 rows) → execute_query",
            "4. Large aggregation, export, or multi-step → run_analysis",
        ],
        execute_query: {
            use_when: [
                "Sample rows or schema verification",
                "Single-entity lookup (one facility, one municipality)",
                "COUNT(*) sanity checks",
                "Result confidently under 500 rows",
                "User wants a quick answer shown inline in chat",
            ],
            do_not_use_when: [
                "GROUP BY over facilities/professionals/facility_equipment (millions of rows)",
                "User asked for Excel/CSV export",
                "Multi-table analysis pipeline",
                "Ranking / top-N across entire country (N > 50)",
            ],
        },
        run_analysis: {
            use_when: [
                "Aggregations (GROUP BY, COUNT, SUM) on large tables",
                "Exports: Excel (.xlsx), CSV, JSON files",
                "Written reports (write_report)",
                "Analysis spanning multiple joins at scale",
                "User says: deep analysis, export, spreadsheet, report, full breakdown",
            ],
            do_not_use_when: [
                "Simple question answerable with one small SELECT",
                "User only wants to explore table structure",
                "Clarifications still pending",
            ],
            before_running: [
                "State your plan in 2-4 bullets (metrics, filters, output format)",
                "If user did not specify output format, ask OR default to print_summary + offer Excel",
                "Call get_analysis_guide if unsure of helpers",
            ],
        },
    },
    workflow: {
        standard: [
            "Parse request → identify ambiguities → ask user if any",
            "Confirm filters (active facility, active staff, geography)",
            "Choose tool (execute_query vs run_analysis)",
            "If run_analysis: brief plan → run → share stdout summary + artifact paths",
            "Never paste huge row dumps into chat; use run_analysis exports instead",
        ],
    },
    critical_rules: [
        "Active facility: deactivation_reason_code IS NULL",
        "Active professional at facility: termination_date IS NULL",
        "Equipment in use: operational_status = 'E' AND quantity > 0",
        "Schema: mcp_test — prefer facility_search_view / professional_search_view for discovery",
        "occupation_code = CBO specialty code",
    ],
};
export function formatAgentPolicyMarkdown() {
    const p = AGENT_POLICY;
    let md = `# CNES MCP Agent Policy\n\n## Role\n${p.role}\n\n`;
    md += `## Ask Before Acting\n${p.mandatory_clarifications.rule}\n\n`;
    for (const item of p.mandatory_clarifications.ask_when) {
        md += `### ${item.topic}\n`;
        md += `- Ask: ${item.examples.join("; ")}\n`;
        md += `- Triggers: ${item.triggers.join("; ")}\n`;
        if ("default_if_silent" in item && item.default_if_silent) {
            md += `- Default if user doesn't care: ${item.default_if_silent}\n`;
        }
        md += "\n";
    }
    md += `## Tool Selection\n`;
    md += p.tool_selection.decision_order.map((s) => `- ${s}`).join("\n") + "\n\n";
    md += `### execute_query\n**Use when:** ${p.tool_selection.execute_query.use_when.join("; ")}\n\n`;
    md += `**Avoid when:** ${p.tool_selection.execute_query.do_not_use_when.join("; ")}\n\n`;
    md += `### run_analysis\n**Use when:** ${p.tool_selection.run_analysis.use_when.join("; ")}\n\n`;
    md += `**Avoid when:** ${p.tool_selection.run_analysis.do_not_use_when.join("; ")}\n\n`;
    md += `**Before running:** ${p.tool_selection.run_analysis.before_running.join("; ")}\n\n`;
    md += `## Critical SQL Rules\n${p.critical_rules.map((r) => `- ${r}`).join("\n")}\n`;
    return md;
}
export function buildServerInstructions() {
    return [
        "You are connected to the CNES PostgreSQL database (schema: mcp_test).",
        "ALWAYS ask clarifying questions before running queries if geographic scope, active/inactive status, output format, or entity type is ambiguous.",
        "Use execute_query only for small lookups (≤500 rows). Use run_analysis for aggregations, exports, and deep analysis.",
        "Before run_analysis, state a brief plan. Call get_agent_policy or assess_request when unsure.",
        "Never dump large result sets into chat — export via run_analysis instead.",
        "Active facility = deactivation_reason_code IS NULL. Active staff = termination_date IS NULL.",
    ].join(" ");
}
const EXPORT_KEYWORDS = /\b(excel|xlsx|csv|export|spreadsheet|report|download|file)\b/i;
const AGGREGATION_KEYWORDS = /\b(count|how many|total|rank|top|breakdown|compare|analysis|analyze|aggregate|group|percentage|distribution|market)\b/i;
const LOOKUP_KEYWORDS = /\b(show me|sample|lookup|find one|describe|what columns|schema|example)\b/i;
const GEO_KEYWORDS = /\b(brazil|brasil|state|municipality|city|region|sp|rj|mg|all)\b/i;
const ACTIVE_KEYWORDS = /\b(active|open|closed|deactivated|inactive|current)\b/i;
const ENTITY_KEYWORDS = /\b(hospital|clinic|pharmacy|doctor|physician|nurse|facility|establishment)\b/i;
export function assessRequest(input) {
    const req = input.user_request.toLowerCase();
    const questions = [];
    const filters = [];
    const plan = [];
    if (!GEO_KEYWORDS.test(req)) {
        questions.push("Which geographic scope? (specific state/municipality, or all Brazil?)");
    }
    if (!ACTIVE_KEYWORDS.test(req)) {
        questions.push("Include only active facilities/staff, or all records (including deactivated)?");
        filters.push("Default active: deactivation_reason_code IS NULL; termination_date IS NULL");
    }
    if (AGGREGATION_KEYWORDS.test(req) && !EXPORT_KEYWORDS.test(req)) {
        questions.push("Do you want a quick summary in chat, or an exported file (Excel/CSV)?");
    }
    if (ENTITY_KEYWORDS.test(req) && !/\b(type|code|cbo|occupation)\b/i.test(req)) {
        questions.push("Which facility type or professional category should count? (e.g. hospital type code, CBO occupation)");
    }
    if (/\bequipment\b/i.test(req) && !/\b(ultrasound|mri|tomograph|x-?ray|equipment_type|code)\b/i.test(req)) {
        questions.push("Which equipment type or search term should we filter on?");
    }
    let recommended = "execute_query";
    let reason = "Simple request; a small SELECT should suffice.";
    if (questions.length > 0 && AGGREGATION_KEYWORDS.test(req)) {
        recommended = "none_yet";
        reason = "Request has ambiguities and needs aggregation — ask clarifying questions before any tool.";
    }
    else if (LOOKUP_KEYWORDS.test(req) && !AGGREGATION_KEYWORDS.test(req)) {
        recommended = /\b(schema|column|table|describe)\b/i.test(req) ? "describe_table" : "execute_query";
        reason = "Exploratory or small lookup request.";
    }
    else if (EXPORT_KEYWORDS.test(req) || (AGGREGATION_KEYWORDS.test(req) && /\b(all|every|each state|by state|by municipality)\b/i.test(req))) {
        recommended = "run_analysis";
        reason = "Export or large-scale aggregation — use Python runner to avoid row limits and token bloat.";
        plan.push("Confirm filters and geography with user");
        plan.push("Write pandas script with query() + save_excel() or write_report()");
        plan.push("Return stdout summary and artifact paths only");
    }
    else if (AGGREGATION_KEYWORDS.test(req)) {
        recommended = questions.length > 2 ? "none_yet" : "run_analysis";
        reason = questions.length > 2
            ? "Too many ambiguities for a reliable query — clarify first."
            : "Aggregation over large CNES tables — prefer run_analysis.";
    }
    if (input.known_context) {
        plan.unshift(`Context: ${input.known_context}`);
    }
    return {
        should_ask_user: questions.length > 0 && recommended !== "describe_table",
        clarifying_questions: questions,
        recommended_tool: recommended,
        tool_reason: reason,
        suggested_filters: filters,
        suggested_plan: plan,
    };
}
