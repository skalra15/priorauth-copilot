export type PipelineStage = {
  step: string;
  title: string;
  description: string;
};

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    step: "01",
    title: "Retrieve",
    description:
      "Deterministic CPT/ICD-10 + state lookup against 1,800+ CMS LCDs and NCDs, with a local semantic fallback -- no hosted vector DB.",
  },
  {
    step: "02",
    title: "Extract",
    description:
      "Policy prose is parsed into structured, typed criteria. Every extracted quote is verified as a verbatim substring of the policy text -- never a paraphrase.",
  },
  {
    step: "03",
    title: "Check",
    description:
      "Each criterion is tested against the clinical note. The system can abstain when the evidence is unclear, rather than guessing.",
  },
  {
    step: "04",
    title: "Decide",
    description:
      "The coverage decision is aggregated deterministically in code from the per-criterion verdicts -- never delegated to the model.",
  },
  {
    step: "05",
    title: "Appeal",
    description:
      "On denial, drafts a citation-backed appeal. The model writes the clinical narrative; every citation is the already-verified policy quote, never generated text.",
  },
];
