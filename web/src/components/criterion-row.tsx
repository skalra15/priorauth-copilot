import type { Criterion, CriterionCheck } from "@/lib/api";
import { getOutcome } from "@/lib/criterion-outcome";
import { OutcomeBadge } from "@/components/outcome-badge";

/** The side-by-side evidence view: policy citation vs. note evidence span,
 * for one criterion. This is the whole point of the UI -- it's what makes
 * the system inspectable rather than magic.
 *
 * Deliberately monochrome except the OutcomeBadge pill: color used to live
 * on the card's left border, both citation boxes, and the confidence bar too
 * -- four colored elements per card, on every card, reads as busy/cheap
 * rather than premium. Red/green/amber now appear only where a verdict is
 * actually being stated (the badge here; the Flagged/Satisfied column
 * headers; the Decision headline) -- everything else is neutral border and
 * text, matching the site's black/white restraint. */
export function CriterionRow({
  criterion,
  check,
}: {
  criterion: Criterion;
  check: CriterionCheck | undefined;
}) {
  const outcome = getOutcome(criterion.type, check?.verdict);

  return (
    <div className="rounded-2xl border border-surface bg-panel p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-text-muted">
            <span>{criterion.type}</span>
            <span aria-hidden="true">·</span>
            <span className="font-mono normal-case">{criterion.id}</span>
          </div>
          <p className="text-sm font-medium text-text">{criterion.text}</p>
        </div>
        {check && <OutcomeBadge outcome={outcome} />}
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
            Policy language
          </div>
          <div className="citation">{criterion.source_span}</div>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
            Note evidence
          </div>
          {check?.evidence_span ? (
            <div className="citation">{check.evidence_span}</div>
          ) : (
            <div className="flex h-full items-center rounded-lg border border-dashed border-border px-4 py-3 text-sm text-text-muted">
              No supporting evidence found in the note
            </div>
          )}
        </div>
      </div>

      {check && (
        <div className="mt-4 border-t border-surface pt-3">
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
            Why
          </div>
          <div className="flex items-start justify-between gap-4">
            <p className="text-sm leading-relaxed text-text-muted">{check.reasoning}</p>
            <div className="flex shrink-0 items-center gap-1.5 pt-0.5" title={`${(check.confidence * 100).toFixed(0)}% confidence`}>
              <div className="h-1 w-10 overflow-hidden rounded-full bg-surface">
                <div
                  className="h-full rounded-full bg-text-muted"
                  style={{ width: `${check.confidence * 100}%` }}
                />
              </div>
              <span className="font-mono text-xs text-text-muted">
                {(check.confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
