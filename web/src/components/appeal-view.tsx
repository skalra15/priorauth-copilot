import { FileText, Lightbulb } from "lucide-react";
import type { AppealSection } from "@/lib/api";
import { CopyButton } from "@/components/copy-button";

/** Renders the structured appeal data with real typographic hierarchy --
 * labeled sub-sections, not a flattened <pre> dump of prefixed sentences.
 * `plainText` (the letter-format string) is what gets copied to the
 * clipboard, since that's the form someone would actually paste into a
 * real appeal submission; the structured view is for on-screen reading. */
export function AppealView({
  policyId,
  title,
  sections,
  closing,
  plainText,
}: {
  policyId: string;
  title: string;
  sections: AppealSection[];
  closing: string;
  plainText: string;
}) {
  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-text-muted">
            Prior authorization appeal
          </div>
          <h3 className="font-heading text-lg font-bold text-text">
            {policyId} — {title}
          </h3>
        </div>
        <CopyButton text={plainText} />
      </div>

      <div className="space-y-4">
        {sections.map((s, i) => (
          <div key={s.criterion_id} className="rounded-2xl border border-surface bg-panel p-6">
            <div className="mb-3 flex items-baseline gap-2">
              <span className="font-mono text-xs text-text-muted">
                {i + 1}
              </span>
              <h4 className="font-heading text-base font-semibold text-text">
                {s.criterion_text}
              </h4>
            </div>

            <div className="mb-4">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
                Policy language
              </div>
              <div className="citation">{s.policy_citation}</div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-deny">
                  <FileText className="h-3 w-3" aria-hidden="true" />
                  Why this wasn&apos;t met
                </div>
                <p className="text-sm leading-relaxed text-text-muted">
                  {s.why_not_met}
                </p>
              </div>
              <div>
                <div className="mb-1 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-approve">
                  <Lightbulb className="h-3 w-3" aria-hidden="true" />
                  What would resolve this
                </div>
                <p className="text-sm leading-relaxed text-text-muted">
                  {s.what_would_resolve}
                </p>
              </div>
            </div>
          </div>
        ))}

        <div className="rounded-2xl border border-dashed border-border p-6">
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-text-muted">
            Closing
          </div>
          <p className="text-sm leading-relaxed text-text">{closing}</p>
        </div>
      </div>
    </div>
  );
}
