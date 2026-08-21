import type { LucideIcon } from "lucide-react";

import { Stagger, StaggerItem } from "@/components/motion";

export interface ConnectedStep {
  label: string;
  title: string;
  body: string;
  boundary?: string;
  Icon: LucideIcon;
}

export function ConnectedRail({ steps, compact = false }: { steps: ConnectedStep[]; compact?: boolean }) {
  return (
    <div className="relative">
      <div aria-hidden="true" className="absolute bottom-auto left-7 top-7 h-[calc(100%-3.5rem)] w-px border-l border-dashed border-sage sm:left-[6%] sm:right-[6%] sm:top-7 sm:h-px sm:w-auto sm:border-l-0 sm:border-t" />
      <Stagger className={`relative grid gap-3 ${steps.length > 6 ? "sm:grid-cols-4 xl:grid-cols-8" : "sm:grid-cols-3 lg:grid-cols-6"}`} step={0.055}>
        {steps.map(({ label, title, body, boundary, Icon }) => (
          <StaggerItem key={label} className="h-full">
            <article className={`relative ml-3 h-full rounded-[14px] border border-line bg-card shadow-[var(--shadow-soft)] sm:ml-0 ${compact ? "p-4" : "p-5"}`}>
              <div className="flex items-center gap-3 sm:block">
                <span className="premium-icon-frame relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-forest sm:mx-auto">
                  <Icon className="h-4.5 w-4.5" aria-hidden="true" />
                </span>
                <div className="sm:mt-3 sm:text-center">
                  <p className="font-mono text-[11px] font-semibold text-olive">{label}</p>
                  <h3 className="mt-0.5 text-[14px] font-semibold text-ink">{title}</h3>
                </div>
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted sm:text-center">{body}</p>
              {boundary ? <p className="mt-3 border-t border-line-soft pt-2.5 text-[11.5px] leading-relaxed text-green"><strong>Boundary:</strong> {boundary}</p> : null}
            </article>
          </StaggerItem>
        ))}
      </Stagger>
    </div>
  );
}
