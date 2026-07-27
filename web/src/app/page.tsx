import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BentoGrid } from "@/components/bento-grid";
import { EvalTable } from "@/components/eval-table";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl px-4 pb-24">
      {/* Hero */}
      <section className="flex flex-col items-start gap-7 pb-24 pt-28 sm:pt-48">
        <Reveal>
          <h1 className="max-w-3xl font-heading text-5xl font-semibold leading-[1.05] tracking-tight text-text sm:text-6xl md:text-7xl">
            Check coverage against Medicare policy.{" "}
            <span className="text-text-muted">Cite every claim.</span>
          </h1>
        </Reveal>
        <Reveal delay={0.08}>
          <p className="max-w-xl text-lg leading-relaxed text-text-muted">
            PriorAuth Copilot reads a clinical note, checks it against the exact
            LCD/NCD criteria that apply, and drafts a citation-backed appeal on
            denial -- every citation is a verbatim, programmatically verified
            quote from the policy, checked against the source text, not taken
            on faith.*
          </p>
          <p className="mt-3 max-w-xl text-xs text-text-muted/70">
            *Measured at a 0% hallucination rate on Sonnet and Opus, 8.5% on
            Haiku, on the golden eval set below. Built in response to
            CMS-0057-F&apos;s prior-authorization transparency requirements.
          </p>
        </Reveal>
        <Reveal delay={0.16}>
          <div className="flex flex-wrap items-center gap-4 pt-2">
            <Link
              href="/checker"
              className="flex items-center gap-2 rounded-lg bg-cta px-5 py-3 text-sm font-semibold text-emerald-950 transition-all duration-200 hover:opacity-90 hover:shadow-lg active:scale-[0.98] cursor-pointer"
            >
              Try the live demo
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
            <a
              href="#results"
              className="rounded-lg border border-border px-5 py-3 text-sm font-semibold text-text transition-all duration-200 hover:bg-surface active:scale-[0.98] cursor-pointer"
            >
              See the eval results
            </a>
          </div>
        </Reveal>
      </section>

      {/* Pipeline */}
      <section id="pipeline" className="scroll-mt-24 py-16">
        <Reveal>
          <SectionHeading>
            Five explicit steps, not a black box
          </SectionHeading>
          <p className="mb-10 max-w-2xl text-text-muted">
            Retrieval, extraction, and decision aggregation are deterministic
            code paths wherever possible. The model is used only where
            judgment is actually required -- and every one of its outputs is
            checked.
          </p>
        </Reveal>
        <BentoGrid />
      </section>

      {/* Grounding callout */}
      <Reveal className="py-16">
        <section className="grid grid-cols-1 gap-8 rounded-2xl border border-surface bg-panel p-8 shadow-sm lg:grid-cols-2 lg:p-12">
          <div>
            <SectionHeading>
              No citation is ever generated
            </SectionHeading>
            <p className="text-text-muted">
              When the checker drafts an appeal, it never asks the model to
              produce a policy quote. Every citation is the criterion&apos;s own
              verified excerpt, already checked as an exact substring of the
              policy text back in extraction. It structurally can&apos;t
              hallucinate a citation -- because it never gets asked to write
              one.
            </p>
          </div>
          <div className="flex flex-col justify-center gap-2">
            <div className="citation">
              {
                "\"As with any allergy testing, the need for such tests is based on the findings during a complete history and physical examination of the patient.\""
              }
            </div>
            <div className="text-xs text-text-muted">
              Verbatim from L33591 — RAST Type Tests, one of the live demo&apos;s
              actual policies
            </div>
          </div>
        </section>
      </Reveal>

      {/* Eval results */}
      <section id="results" className="scroll-mt-24 py-16">
        <Reveal>
          <SectionHeading>
            Model sweep, one reproducible eval
          </SectionHeading>
          <p className="mb-8 max-w-2xl text-text-muted">
            Haiku, Sonnet, and Opus run through the identical extraction,
            retrieval, and checking eval. Hallucination rate is the headline
            number -- Sonnet and Opus hit zero on this golden set; Haiku
            doesn&apos;t.
          </p>
        </Reveal>
        <Reveal delay={0.1}>
          <EvalTable />
        </Reveal>
      </section>

      {/* CTA */}
      <Reveal>
        <section className="flex flex-col items-center gap-4 rounded-2xl border border-surface bg-panel py-16 text-center shadow-sm">
          <SectionHeading as="h2">Try it on a real policy</SectionHeading>
          <p className="max-w-md text-text-muted">
            Enter a CPT or ICD-10 code, a state, and a clinical note. The
            system retrieves the applicable policy, evaluates every
            criterion, and returns a citation-backed decision.
          </p>
          <Link
            href="/checker"
            className="mt-2 flex items-center gap-2 rounded-lg bg-cta px-5 py-3 text-sm font-semibold text-emerald-950 transition-all duration-200 hover:opacity-90 hover:shadow-lg active:scale-[0.98] cursor-pointer"
          >
            Open the live demo
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </section>
      </Reveal>
    </div>
  );
}
