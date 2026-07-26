"use client";

import { useState } from "react";
import { Loader2, AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { checkNote, ApiError, type CheckResponse } from "@/lib/api";
import { getOutcome } from "@/lib/criterion-outcome";
import { EXAMPLES } from "@/data/examples";
import { CriterionRow } from "@/components/criterion-row";
import { AppealView } from "@/components/appeal-view";
import { CodeCombobox } from "@/components/code-combobox";
import { MatchedPolicyCard } from "@/components/matched-policy-card";
import { ResultSummary } from "@/components/result-summary";
import { DecisionHeadline } from "@/components/decision-headline";
import { SectionHeading } from "@/components/section-heading";

const US_STATES = [
  "", "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
  "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
  "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
  "WV", "WI", "WY",
];

export default function CheckerPage() {
  const [cpt, setCpt] = useState("");
  const [icd10, setIcd10] = useState("");
  const [state, setState] = useState("");
  const [noteText, setNoteText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckResponse | null>(null);

  // Computed once here, not re-filtered separately by the grouping UI and the
  // Summary breakdown below -- both must count the exact same set of
  // criteria, or their totals can silently drift apart.
  const testableCriteria = result ? result.criteria.filter((c) => c.type !== "informational") : [];

  function loadExample(i: number) {
    const ex = EXAMPLES[i];
    setCpt(ex.cpt);
    setIcd10(ex.icd10);
    setState("");
    setNoteText(ex.noteText);
    setResult(null);
    setError(null);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!noteText.trim() || (!cpt.trim() && !icd10.trim())) {
      setError("Provide at least one code (CPT or ICD-10) and a clinical note.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await checkNote({
        cpt: cpt.trim() || undefined,
        icd10: icd10.trim() || undefined,
        state: state.trim() || undefined,
        note_text: noteText,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Is the API running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-4 pb-24 pt-32">
      <SectionHeading as="h1">Live coverage checker</SectionHeading>
      <p className="mt-2 max-w-2xl text-text-muted">
        Enter a CPT or ICD-10 code and a clinical note. The system retrieves the
        matching Medicare policy, checks the note against every criterion, and
        shows the policy citation and note evidence side by side for each one.
      </p>

      <div className="mt-6 text-xs font-medium uppercase tracking-wide text-text-muted">
        Try an example
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {EXAMPLES.map((ex, i) => (
          <button
            key={ex.label}
            type="button"
            onClick={() => loadExample(i)}
            className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-muted transition-colors duration-200 hover:border-cta hover:text-text cursor-pointer"
          >
            {ex.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="mt-6 space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label htmlFor="cpt" className="mb-1.5 block text-sm font-bold text-text">
              CPT / HCPCS code
            </label>
            <CodeCombobox
              id="cpt"
              system="HCPCS"
              value={cpt}
              onChange={setCpt}
              placeholder="e.g. 86003"
            />
          </div>
          <div>
            <label htmlFor="icd10" className="mb-1.5 block text-sm font-bold text-text">
              ICD-10 code
            </label>
            <CodeCombobox
              id="icd10"
              system="ICD10"
              value={icd10}
              onChange={setIcd10}
              placeholder="e.g. J30.0"
            />
          </div>
          <div>
            <label htmlFor="state" className="mb-1.5 block text-sm font-bold text-text">
              State (optional)
            </label>
            <select
              id="state"
              className="input w-full"
              value={state}
              onChange={(e) => setState(e.target.value)}
            >
              {US_STATES.map((s) => (
                <option key={s || "any"} value={s}>
                  {s || "Any"}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label htmlFor="note" className="mb-1.5 block text-sm font-bold text-text">
            Clinical note
          </label>
          <textarea
            id="note"
            className="input w-full font-mono text-sm"
            rows={10}
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Paste or write a clinical note..."
          />
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-deny/30 bg-deny/10 px-4 py-3 text-sm text-deny">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-text px-5 py-3 text-sm font-semibold text-deep transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
        >
          {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          {loading ? "Checking..." : "Check coverage"}
        </button>
      </form>

      <AnimatePresence mode="wait">
        {result && (
          <motion.div
            key={`${result.policy.policy_id}-${result.decision.decision}`}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="mt-10 space-y-6"
          >
            <DecisionHeadline decision={result.decision.decision} />

            <MatchedPolicyCard policy={result.policy} />

            <div>
              <h3 className="mb-4 font-heading text-xl font-bold text-text">
                Criteria evaluated
              </h3>
              {(() => {
                const withChecks = testableCriteria.map((criterion) => ({
                  criterion,
                  check: result.decision.checks.find((c) => c.criterion_id === criterion.id),
                }));

                // Grouped by the same getOutcome() that CriterionRow uses for its
                // badge color -- one function decides both, so a card's badge can
                // never contradict the column it's sitting in (see
                // lib/criterion-outcome.ts for the exclusion/required distinction
                // this depends on).
                const satisfied = withChecks.filter(
                  ({ criterion, check }) => getOutcome(criterion.type, check?.verdict) === "satisfied",
                );
                const flagged = withChecks.filter(
                  ({ criterion, check }) => getOutcome(criterion.type, check?.verdict) !== "satisfied",
                );

                return (
                  <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                    <div>
                      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-deny">
                        <span className="h-2 w-2 rounded-full bg-deny" aria-hidden="true" />
                        Flagged ({flagged.length})
                      </div>
                      <div className="space-y-4">
                        {flagged.length === 0 && (
                          <p className="text-sm text-text-muted">Nothing flagged.</p>
                        )}
                        {flagged.map(({ criterion, check }) => (
                          <CriterionRow key={criterion.id} criterion={criterion} check={check} />
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-approve">
                        <span className="h-2 w-2 rounded-full bg-approve" aria-hidden="true" />
                        Satisfied ({satisfied.length})
                      </div>
                      <div className="space-y-4">
                        {satisfied.length === 0 && (
                          <p className="text-sm text-text-muted">Nothing satisfied yet.</p>
                        )}
                        {satisfied.map(({ criterion, check }) => (
                          <CriterionRow key={criterion.id} criterion={criterion} check={check} />
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>

            <ResultSummary
              decision={result.decision}
              criteria={testableCriteria}
              checks={result.decision.checks}
            />

            {result.appeal_text && result.appeal_sections && result.appeal_closing && (
              <AppealView
                policyId={result.policy.policy_id}
                title={result.policy.title}
                sections={result.appeal_sections}
                closing={result.appeal_closing}
                plainText={result.appeal_text}
              />
            )}

            {result.appeal_error && (
              <div className="flex items-center gap-2 rounded-lg border border-review/30 bg-review/10 px-4 py-3 text-sm text-review">
                <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
                Appeal draft failed a citation integrity check and was withheld: {result.appeal_error}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
