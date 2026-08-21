import type { ReactNode } from "react";

type MetricVariant = "light" | "dark" | "warning" | "verified" | "blocked";

const VARIANT: Record<MetricVariant, string> = {
  light: "metric-card text-ink",
  dark: "dark-card text-cream",
  warning: "border-amber/55 bg-amber-wash text-ink shadow-[inset_0_1px_0_rgba(255,255,255,.72)]",
  verified: "border-sage bg-sage-soft/75 text-forest shadow-[inset_0_1px_0_rgba(255,255,255,.72)]",
  blocked: "border-amber-soft bg-amber-wash/80 text-[#73530d] shadow-[inset_0_1px_0_rgba(255,255,255,.72)]",
};

export function MetricCard({
  eyebrow,
  value,
  label,
  detail,
  variant = "light",
  className = "",
}: {
  eyebrow: string;
  value: ReactNode;
  label: string;
  detail?: ReactNode;
  variant?: MetricVariant;
  className?: string;
}) {
  const dark = variant === "dark";
  return (
    <article className={`h-full rounded-[14px] border p-5 ${VARIANT[variant]} ${className}`}>
      <p className={`text-[11.5px] font-semibold uppercase tracking-[.11em] ${dark ? "text-[var(--status-success)]" : "text-olive"}`}>
        {eyebrow}
      </p>
      <p className={`display-heading mt-3 text-[36px] leading-none ${dark ? "text-cream" : "text-forest"}`}>
        {value}
      </p>
      <p className={`mt-2 text-[14px] font-medium leading-relaxed ${dark ? "text-[var(--text-on-dark-secondary)]" : "text-ink"}`}>
        {label}
      </p>
      {detail ? <div className={`mt-3 text-[13px] leading-relaxed ${dark ? "text-[var(--text-on-dark-secondary)]" : "text-muted"}`}>{detail}</div> : null}
    </article>
  );
}
