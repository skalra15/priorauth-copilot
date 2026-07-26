import { Search, FileSearch2, ClipboardCheck, Scale, Send } from "lucide-react";
import { PIPELINE_STAGES } from "@/data/pipeline";
import { RevealGroup, RevealItem } from "@/components/reveal";

const ICONS = [Search, FileSearch2, ClipboardCheck, Scale, Send];

export function BentoGrid() {
  return (
    <RevealGroup className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {PIPELINE_STAGES.map((stage, i) => {
        const Icon = ICONS[i];
        return (
          <RevealItem key={stage.step} className={i === 0 ? "lg:col-span-2" : ""}>
            <div className="h-full rounded-xl border border-surface bg-panel p-6 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-border hover:shadow-md">
              <div className="mb-4 flex items-center justify-between">
                <span className="font-mono text-xs text-text-muted">
                  {stage.step}
                </span>
                <Icon className="h-5 w-5 text-cta" aria-hidden="true" />
              </div>
              <h3 className="mb-2 font-heading text-lg font-semibold text-text">
                {stage.title}
              </h3>
              <p className="text-sm leading-relaxed text-text-muted">
                {stage.description}
              </p>
            </div>
          </RevealItem>
        );
      })}
    </RevealGroup>
  );
}
