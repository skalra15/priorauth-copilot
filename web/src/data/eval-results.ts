// Synced by hand from evals/results/20260725.json ().
// Regenerate that file with `python -m priorauth.cli eval --full --sweep --report evals/results/<date>.json`
// and copy the updated numbers here -- this frontend doesn't read across the repo at build time
// since only web/ is deployed to Vercel.

export type EvalRow = {
  model: string;
  displayName: string;
  extractionPrecision: number;
  extractionRecall: number;
  hallucinatedSpanRate: number;
  retrievalRecallAt1: number;
  retrievalRecallAt5: number;
  verdictAccuracy: number;
  correctAbstentionRate: number;
  totalCostUsd: number;
};

export const EVAL_RESULTS: EvalRow[] = [
  {
    model: "claude-haiku-4-5",
    displayName: "Claude Haiku 4.5",
    extractionPrecision: 0.7981,
    extractionRecall: 0.9405,
    hallucinatedSpanRate: 0.0847,
    retrievalRecallAt1: 0.72,
    retrievalRecallAt5: 1.0,
    verdictAccuracy: 0.7054,
    correctAbstentionRate: 0.4722,
    totalCostUsd: 0.3026,
  },
  {
    model: "claude-sonnet-5",
    displayName: "Claude Sonnet 5",
    extractionPrecision: 0.8815,
    extractionRecall: 0.8848,
    hallucinatedSpanRate: 0.0,
    retrievalRecallAt1: 0.72,
    retrievalRecallAt5: 1.0,
    verdictAccuracy: 0.8682,
    correctAbstentionRate: 0.6389,
    totalCostUsd: 0.6762,
  },
  {
    model: "claude-opus-5",
    displayName: "Claude Opus 5",
    extractionPrecision: 0.6753,
    extractionRecall: 0.9665,
    hallucinatedSpanRate: 0.0,
    retrievalRecallAt1: 0.72,
    retrievalRecallAt5: 1.0,
    verdictAccuracy: 0.6744,
    correctAbstentionRate: 0.4444,
    totalCostUsd: 1.9608,
  },
];

export const HEADLINE_MODEL = "claude-sonnet-5";
