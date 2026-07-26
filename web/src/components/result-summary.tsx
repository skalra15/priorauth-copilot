import type { Criterion, CoverageDecision, CriterionCheck } from "@/lib/api";
import { getOutcome } from "@/lib/criterion-outcome";
import { DECISION_META } from "@/lib/decision-meta";

/** The full, closing summary -- shown last, after every criterion has been
 * read in detail. Structured as labeled subsections (Decision / Explanation /
 * Criteria breakdown) rather than one undifferentiated paragraph, so it
 * reads as a written conclusion, not another block of model prose. The
 * headline decision was already shown at the top (DecisionHeadline); this
 * restates it briefly alongside the actual reasoning and the full stat
 * breakdown, the way a report's summary/conclusion section restates its
 * impression alongside supporting detail.
 *
 * The breakdown counts by getOutcome() (satisfied/flagged/insufficient), the
 * exact same function and labels as the "Criteria evaluated" section above
 * it -- not by raw verdict string. Counting raw "met"/"not_met" here while
 * the section above groups by outcome meant the two could show different
 * numbers for the same result (an exclusion's "not_met" is satisfied, not
 * met, so raw-verdict counting and outcome counting only agree when there
 * are zero exclusion criteria in the policy). Same inputs, same function,
 * same numbers, everywhere on the page. */
export function ResultSummary({
  decision,
  criteria,
  checks,
}: {
  decision: CoverageDecision;
  criteria: Criterion[];
  checks: CriterionCheck[];
}) {
  const meta = DECISION_META[decision.decision];
  const checksById = new Map(checks.map((c) => [c.criterion_id, c]));
  const outcomes = criteria.map((crit) => getOutcome(crit.type, checksById.get(crit.id)?.verdict));
  const satisfied = outcomes.filter((o) => o === "satisfied").length;
  const flagged = outcomes.filter((o) => o === "flagged").length;
  const insufficient = outcomes.filter((o) => o === "insufficient").length;

  return (
    <div className="rounded-2xl border border-surface bg-panel p-6 sm:p-8">
      <h3 className="mb-6 font-heading text-xl font-bold text-text">Summary</h3>

      <div className="mb-6">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
          Decision
        </div>
        <div className="flex items-center gap-2">
          <meta.Icon className={`h-5 w-5 ${meta.colorClass}`} aria-hidden="true" />
          <span className={`font-heading text-lg font-bold ${meta.colorClass}`}>
            {meta.label}
          </span>
        </div>
      </div>

      <div className="mb-6">
        <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-text-muted">
          Explanation
        </div>
        <p className="leading-relaxed text-text">{decision.rationale}</p>
      </div>

      <div>
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">
          Criteria breakdown
        </div>
        <div className="grid grid-cols-3 divide-x divide-surface border-t border-surface pt-5 text-center">
          <div>
            <div className="font-heading text-2xl font-bold text-approve">{satisfied}</div>
            <div className="mt-0.5 text-xs text-text-muted">Satisfied</div>
          </div>
          <div>
            <div className="font-heading text-2xl font-bold text-deny">{flagged}</div>
            <div className="mt-0.5 text-xs text-text-muted">Flagged</div>
          </div>
          <div>
            <div className="font-heading text-2xl font-bold text-review">{insufficient}</div>
            <div className="mt-0.5 text-xs text-text-muted">Insufficient evidence</div>
          </div>
        </div>
      </div>
    </div>
  );
}
