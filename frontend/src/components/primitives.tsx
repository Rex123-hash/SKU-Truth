/**
 * The small shared vocabulary every page is built from: the button, the section frame,
 * the eyebrow capsule, the numbered section heading. Defined once so the eight routes
 * cannot drift apart visually.
 */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

export function Container({
  children,
  className = "",
  ...rest
}: {
  children: ReactNode;
  className?: string;
} & Omit<ComponentProps<"div">, "children" | "className">) {
  return (
    <div className={`mx-auto w-full max-w-[1240px] px-5 sm:px-8 ${className}`} {...rest}>
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "onDark" | "ghostOnDark";

/**
 * `onDark` and `ghostOnDark` exist as real variants rather than as colour overrides
 * passed through `className`. Two utilities that set the same property have equal
 * specificity, so which one wins is decided by stylesheet order, not by the order they
 * appear in the class attribute — an override written that way rendered forest-green
 * text on the forest-green CTA band and made the label disappear.
 */
const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary:
    "bg-forest text-cream hover:bg-forest-deep border border-transparent shadow-[0_1px_2px_rgb(23_32_25/0.15)]",
  secondary: "bg-card text-forest border border-line hover:border-sage hover:bg-cream-soft",
  onDark: "bg-olive text-white border border-transparent hover:bg-[#5f7c39]",
  ghostOnDark: "bg-transparent text-cream border border-cream/30 hover:border-cream/60 hover:bg-cream/10",
};

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-[15px] font-medium transition-colors duration-200";

export function ButtonLink({
  href,
  children,
  variant = "primary",
  withArrow = true,
  className = "",
  ...rest
}: {
  href: string;
  children: ReactNode;
  variant?: ButtonVariant;
  withArrow?: boolean;
  className?: string;
} & Omit<ComponentProps<typeof Link>, "href" | "className" | "children">) {
  return (
    <Link href={href} className={`${BUTTON_BASE} ${BUTTON_STYLES[variant]} ${className}`} {...rest}>
      {children}
      {withArrow ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
    </Link>
  );
}

export function Button({
  children,
  variant = "primary",
  withArrow = false,
  className = "",
  ...rest
}: {
  children: ReactNode;
  variant?: ButtonVariant;
  withArrow?: boolean;
} & ComponentProps<"button">) {
  return (
    <button className={`${BUTTON_BASE} ${BUTTON_STYLES[variant]} ${className}`} {...rest}>
      {children}
      {withArrow ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
    </button>
  );
}

/** The small capitalised capsule that sits above every hero headline. */
export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border border-line bg-card px-3.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-green ${className}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-olive" aria-hidden="true" />
      {children}
    </span>
  );
}

/** A numbered section header, as used on the approved Platform page. */
export function SectionHeading({
  index,
  title,
  subtitle,
  className = "",
}: {
  index?: number;
  title: ReactNode;
  subtitle?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-start gap-3.5 ${className}`}>
      {index !== undefined ? (
        <span
          aria-hidden="true"
          className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line-soft bg-card text-[13px] font-semibold text-green"
        >
          {index}
        </span>
      ) : null}
      <div>
        <h2 className="display-heading text-[26px] text-ink sm:text-[30px]">{title}</h2>
        {subtitle ? <p className="mt-1.5 text-[15px] text-muted">{subtitle}</p> : null}
      </div>
    </div>
  );
}

/** A page-level section frame with consistent vertical rhythm. */
export function Section({
  children,
  className = "",
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`py-14 sm:py-20 ${className}`}>
      {children}
    </section>
  );
}

/** The breadcrumb capsule from the approved inner pages. */
export function Breadcrumb({ trail }: { trail: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-7">
      <ol className="inline-flex items-center gap-2 rounded-full border border-line bg-card/70 px-3.5 py-1.5 text-[12.5px] text-muted">
        {trail.map((item, i) => (
          <li key={item.label} className="inline-flex items-center gap-2">
            {i > 0 ? <span aria-hidden="true">›</span> : null}
            {item.href ? (
              <Link href={item.href} className="hover:text-green">
                {item.label}
              </Link>
            ) : (
              <span className="font-medium text-ink">{item.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
