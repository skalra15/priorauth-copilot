import type { CoverageDecision } from "@/lib/api";
import { DECISION_META } from "@/lib/decision-meta";

/** The headline answer, shown first -- before the matched policy or any
 * criteria detail. Someone using this shouldn't have to read the whole
 * results view to find out whether the answer is yes or no; that comes at
 * the end too (ResultSummary), with the full explanation, but the quick
 * answer belongs at the top. No rationale text here -- that's what the
 * closing Summary section is for. */
export function DecisionHeadline({
  decision,
}: {
  decision: CoverageDecision["decision"];
}) {
  const meta = DECISION_META[decision];
  return (
    <div className={`flex items-center gap-4 rounded-2xl border px-6 py-5 ${meta.bgClass}`}>
      <meta.Icon className={`h-9 w-9 shrink-0 ${meta.colorClass}`} aria-hidden="true" />
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Decision
        </div>
        <div className={`font-heading text-2xl font-bold ${meta.colorClass}`}>
          {meta.label}
        </div>
      </div>
    </div>
  );
}
