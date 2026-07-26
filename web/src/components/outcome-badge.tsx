import { Check, X, HelpCircle } from "lucide-react";
import type { Outcome } from "@/lib/criterion-outcome";

/** Labeled and colored by semantic outcome (satisfied/flagged/insufficient),
 * never by the raw verdict string -- see lib/criterion-outcome.ts for why
 * that distinction matters (an exclusion's "not_met" is a good outcome, not
 * a bad one). Labels intentionally match the column headers ("Satisfied" /
 * "Flagged") so a card's badge can never contradict which column it's in. */
const OUTCOME_META: Record<
  Outcome,
  { label: string; colorClass: string; bgClass: string; Icon: typeof Check }
> = {
  satisfied: {
    label: "Satisfied",
    colorClass: "text-approve",
    bgClass: "bg-approve/10 border-approve/30",
    Icon: Check,
  },
  flagged: {
    label: "Flagged",
    colorClass: "text-deny",
    bgClass: "bg-deny/10 border-deny/30",
    Icon: X,
  },
  insufficient: {
    label: "Insufficient evidence",
    colorClass: "text-review",
    bgClass: "bg-review/10 border-review/30",
    Icon: HelpCircle,
  },
};

export function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  const { label, colorClass, bgClass, Icon } = OUTCOME_META[outcome];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${colorClass} ${bgClass}`}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
