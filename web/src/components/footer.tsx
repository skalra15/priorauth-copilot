import Link from "next/link";
import { Code2 } from "lucide-react";

/** The site had no footer at all -- meaning the disclaimer, the author, and
 * the link back to the actual code only ever existed in README.md, never on
 * the live product a visitor actually lands on. This is the fix: real,
 * verifiable links only (the repo, the author name from LICENSE), no
 * fabricated contact details or social proof. */
export function Footer() {
  return (
    <footer className="mt-24 border-t border-surface">
      <div className="mx-auto max-w-5xl px-4 py-10">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-md">
            <p className="font-heading text-sm font-semibold text-text">
              PriorAuth Copilot
            </p>
            <p className="mt-2 text-xs leading-relaxed text-text-muted">
              Research and portfolio project. Not a medical device, not
              clinical decision support, not for use in real coverage or care
              decisions. No real patient data is used or stored -- see the
              writeup for the full methodology and honest limitations.
            </p>
          </div>
          <div className="flex flex-col gap-2 text-sm">
            <a
              href="https://github.com/skalra15/priorauth-copilot"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-text-muted transition-colors duration-200 hover:text-text cursor-pointer"
            >
              <Code2 className="h-4 w-4" aria-hidden="true" />
              View source on GitHub
            </a>
            <Link
              href="/checker"
              className="text-text-muted transition-colors duration-200 hover:text-text cursor-pointer"
            >
              Try the live demo
            </Link>
          </div>
        </div>
        <p className="mt-8 text-xs text-text-muted/70">
          Built by Shantanu Kalra.
        </p>
      </div>
    </footer>
  );
}
