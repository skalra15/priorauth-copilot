import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";

const LINKS = [
  { href: "/#pipeline", label: "Pipeline" },
  { href: "/#results", label: "Results" },
  { href: "/checker", label: "Live Demo" },
];

export function NavBar() {
  return (
    <header className="sticky top-4 z-50 mx-4 md:mx-auto md:max-w-5xl">
      <nav className="glass flex items-center justify-between gap-2 rounded-xl px-4 py-3 shadow-lg">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 font-heading text-base font-semibold whitespace-nowrap text-text cursor-pointer"
        >
          <ShieldCheck className="h-5 w-5 shrink-0 text-cta" aria-hidden="true" />
          <span className="hidden sm:inline">PriorAuth Copilot</span>
        </Link>
        <div className="flex shrink-0 items-center gap-1 sm:gap-3">
          {LINKS.slice(0, -1).map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="hidden whitespace-nowrap px-2 text-sm text-text-muted transition-colors duration-200 hover:text-text lg:inline cursor-pointer"
            >
              {link.label}
            </Link>
          ))}
          <ThemeToggle />
          <Link
            href="/checker"
            className="whitespace-nowrap rounded-lg bg-cta px-3 py-2 text-sm font-semibold text-emerald-950 transition-transform duration-200 hover:opacity-90 sm:px-4 cursor-pointer"
          >
            Live Demo
          </Link>
        </div>
      </nav>
    </header>
  );
}
