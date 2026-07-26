import type { Criterion, CriterionCheck } from "@/lib/api";

export type Outcome = "satisfied" | "flagged" | "insufficient";

/** Single source of truth for "is this criterion a good or bad outcome" --
 * shared between the page's Flagged/Satisfied grouping and CriterionRow's
 * badge/accent color. Before this was factored out, the page grouped by this
 * logic while CriterionRow colored its badge straight off the raw verdict
 * string -- so an exclusion criterion that's `not_met` (the GOOD outcome,
 * satisfied) landed in the green "Satisfied" column but still showed a red
 * "Not met" badge, since the badge never looked at criterion type. Having
 * both places call this one function makes that kind of disagreement
 * impossible by construction, not just by careful duplication. */
export function getOutcome(
  criterionType: Criterion["type"],
  verdict: CriterionCheck["verdict"] | undefined,
): Outcome {
  if (!verdict || verdict === "insufficient_evidence") return "insufficient";
  const isGood = criterionType === "exclusion" ? verdict === "not_met" : verdict === "met";
  return isGood ? "satisfied" : "flagged";
}
