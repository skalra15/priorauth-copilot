"use client";

import { useState } from "react";
import { Copy, Check, X } from "lucide-react";

function fallbackCopy(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
}

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");

  async function handleCopy() {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch {
      // Clipboard API can reject for reasons that have nothing to do with the
      // user's intent -- non-HTTPS context, a browser permission policy, or
      // (as seen while testing this in an embedded preview) automation-driven
      // clicks not carrying the "trusted" user-activation flag the API
      // requires. Fall back to the older execCommand path rather than
      // failing silently.
      ok = fallbackCopy(text);
    }
    setStatus(ok ? "copied" : "failed");
    setTimeout(() => setStatus("idle"), 2000);
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-text-muted transition-colors duration-200 hover:border-cta hover:text-text cursor-pointer"
    >
      {status === "copied" && (
        <>
          <Check className="h-3.5 w-3.5 text-approve" aria-hidden="true" />
          Copied
        </>
      )}
      {status === "failed" && (
        <>
          <X className="h-3.5 w-3.5 text-deny" aria-hidden="true" />
          Couldn&apos;t copy
        </>
      )}
      {status === "idle" && (
        <>
          <Copy className="h-3.5 w-3.5" aria-hidden="true" />
          {label}
        </>
      )}
    </button>
  );
}
