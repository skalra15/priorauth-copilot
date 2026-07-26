import { ExternalLink, FileCheck2 } from "lucide-react";
import type { PolicySummary } from "@/lib/api";

/** Highlighted callout for the retrieved policy -- this is the system's
 * first, most consequential decision (which policy applies at all), so it
 * gets its own visually distinct card rather than a plain text label.
 *
 * Neutral, not green: matching a policy isn't itself a good outcome (it's
 * the input to the decision, not the decision), so it shouldn't borrow the
 * same green the verdict badges use for "approved" -- that would visually
 * suggest a positive result before the checker has said anything. */
export function MatchedPolicyCard({ policy }: { policy: PolicySummary }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-surface bg-panel px-6 py-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-surface">
          <FileCheck2 className="h-5 w-5 text-text-muted" aria-hidden="true" />
        </div>
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Matched policy · {policy.policy_type}
            {policy.jurisdiction ? ` · ${policy.jurisdiction}` : ""}
          </div>
          <h2 className="font-heading text-lg font-bold text-text">
            {policy.policy_id} — {policy.title}
          </h2>
        </div>
      </div>
      {policy.source_url && (
        <a
          href={policy.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-panel px-3 py-2 text-sm font-medium text-text transition-colors duration-200 hover:bg-surface cursor-pointer"
        >
          View on CMS
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </div>
  );
}
