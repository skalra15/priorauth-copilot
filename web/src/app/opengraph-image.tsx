import { ImageResponse } from "next/og";

export const alt = "PriorAuth Copilot";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "80px",
          background: "#fbfbfd",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 32,
          }}
        >
          <div
            style={{
              width: 14,
              height: 14,
              borderRadius: "50%",
              background: "#16a34a",
            }}
          />
          <div style={{ fontSize: 28, fontWeight: 600, color: "#1d1d1f" }}>
            PriorAuth Copilot
          </div>
        </div>
        <div
          style={{
            fontSize: 56,
            fontWeight: 700,
            color: "#1d1d1f",
            lineHeight: 1.1,
            maxWidth: 980,
          }}
        >
          Check coverage against Medicare policy.
        </div>
        <div
          style={{
            fontSize: 56,
            fontWeight: 700,
            color: "#6e6e73",
            lineHeight: 1.1,
            marginBottom: 32,
          }}
        >
          Cite every claim.
        </div>
        <div style={{ fontSize: 28, color: "#6e6e73", maxWidth: 900 }}>
          Open, benchmarked, citation-backed. 0% hallucination rate on Sonnet
          and Opus.
        </div>
      </div>
    ),
    { ...size },
  );
}
