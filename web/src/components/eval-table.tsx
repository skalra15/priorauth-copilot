import { EVAL_RESULTS } from "@/data/eval-results";

function pct(n: number) {
  return `${(n * 100).toFixed(1)}%`;
}

export function EvalTable() {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-panel">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-text-muted">
            <th scope="col" className="px-4 py-3 font-medium">
              Model
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Extraction P / R
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Hallucination rate
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Retrieval R@1 / R@5
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Verdict accuracy
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Correct abstention
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              Cost (full sweep)
            </th>
          </tr>
        </thead>
        <tbody>
          {EVAL_RESULTS.map((row) => (
            <tr key={row.model} className="border-b border-border last:border-0">
              <th scope="row" className="px-4 py-3 font-heading font-medium text-text">
                {row.displayName}
              </th>
              <td className="px-4 py-3 text-text">
                {pct(row.extractionPrecision)} / {pct(row.extractionRecall)}
              </td>
              <td className="px-4 py-3">
                <span
                  className={
                    row.hallucinatedSpanRate === 0
                      ? "text-approve"
                      : "text-review"
                  }
                >
                  {pct(row.hallucinatedSpanRate)}
                </span>
              </td>
              <td className="px-4 py-3 text-text">
                {pct(row.retrievalRecallAt1)} / {pct(row.retrievalRecallAt5)}
              </td>
              <td className="px-4 py-3 text-text">{pct(row.verdictAccuracy)}</td>
              <td className="px-4 py-3 text-text">
                {pct(row.correctAbstentionRate)}
              </td>
              <td className="px-4 py-3 text-text-muted">
                ${row.totalCostUsd.toFixed(2)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
