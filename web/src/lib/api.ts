const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Verdict = "met" | "not_met" | "insufficient_evidence";

export type Criterion = {
  id: string;
  text: string;
  type: "required" | "exclusion" | "informational";
  logic: "single" | "all_of" | "one_of";
  sub_conditions: string[];
  temporal: string | null;
  source_span: string;
};

export type CriterionCheck = {
  criterion_id: string;
  verdict: Verdict;
  evidence_span: string | null;
  reasoning: string;
  confidence: number;
};

export type CoverageDecision = {
  policy_id: string;
  checks: CriterionCheck[];
  decision: "likely_approve" | "likely_deny" | "needs_human_review";
  unmet_criteria: string[];
  rationale: string;
};

export type PolicySummary = {
  policy_id: string;
  title: string;
  policy_type: string;
  jurisdiction: string | null;
  source_url: string | null;
};

export type AppealSection = {
  criterion_id: string;
  criterion_text: string;
  policy_citation: string;
  why_not_met: string;
  what_would_resolve: string;
};

export type CheckResponse = {
  policy: PolicySummary;
  criteria: Criterion[];
  decision: CoverageDecision;
  appeal_text: string | null;
  appeal_sections: AppealSection[] | null;
  appeal_closing: string | null;
  appeal_error: string | null;
};

export type CheckRequest = {
  cpt?: string;
  icd10?: string;
  state?: string;
  note_text: string;
};

export type CodeSuggestion = {
  code: string;
  description: string | null;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function checkNote(req: CheckRequest): Promise<CheckResponse> {
  const res = await fetch(`${API_BASE}/api/check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export async function searchCodes(
  system: "HCPCS" | "ICD10",
  query: string,
  signal?: AbortSignal,
): Promise<CodeSuggestion[]> {
  if (!query.trim()) return [];
  const params = new URLSearchParams({ system, q: query });
  const res = await fetch(`${API_BASE}/api/codes?${params}`, { signal });
  if (!res.ok) return [];
  return res.json();
}
