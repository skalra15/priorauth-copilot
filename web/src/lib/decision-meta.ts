import { CheckCircle2, XCircle, HelpCircle } from "lucide-react";
import type { CoverageDecision } from "@/lib/api";

/** Shared between DecisionHeadline (shown first) and ResultSummary (shown
 * last, with full explanation) so both agree on label/color/icon per
 * decision -- one source of truth, not two components independently
 * hardcoding the same three-way mapping. */
export const DECISION_META: Record<
  CoverageDecision["decision"],
  { label: string; colorClass: string; bgClass: string; Icon: typeof CheckCircle2 }
> = {
  likely_approve: {
    label: "Likely Approve",
    colorClass: "text-approve",
    bgClass: "bg-approve/10 border-approve/30",
    Icon: CheckCircle2,
  },
  likely_deny: {
    label: "Likely Deny",
    colorClass: "text-deny",
    bgClass: "bg-deny/10 border-deny/30",
    Icon: XCircle,
  },
  needs_human_review: {
    label: "Needs Human Review",
    colorClass: "text-review",
    bgClass: "bg-review/10 border-review/30",
    Icon: HelpCircle,
  },
};
