"use client";

import { motion, useReducedMotion } from "framer-motion";

/**
 * The small hand-drawn marks that tie the approved layouts together: amber sparkles and
 * dashed arrows between illustrations. These are primitive shapes, so they are drawn
 * here rather than pulled from the illustration set.
 *
 * As in `motion.tsx`, `initial` never depends on the reduced-motion media query — the
 * server cannot read it, and markup that does would hydrate into a mismatch.
 */

export function Sparkle({
  className = "",
  size = 22,
  delay = 0,
}: {
  className?: string;
  size?: number;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
      animate={reduced ? undefined : { opacity: [0.4, 1, 0.4], scale: [0.88, 1, 0.88] }}
      transition={{ duration: 3.6, delay, repeat: Infinity, ease: "easeInOut" }}
    >
      <path
        d="M12 1.6c.9 4.9 2.5 7.5 8.4 8.4-5.9.9-7.5 3.5-8.4 8.4-.9-4.9-2.5-7.5-8.4-8.4C9.5 9.1 11.1 6.5 12 1.6Z"
        fill="#E7A62B"
      />
    </motion.svg>
  );
}

/** A dashed arc with an arrowhead, drawn once on entry. */
export function DottedArrow({
  className = "",
  d = "M4 34C28 6 74 2 116 20",
  width = 128,
  height = 44,
  flip = false,
}: {
  className?: string;
  d?: string;
  width?: number;
  height?: number;
  flip?: boolean;
}) {
  return (
    <svg
      viewBox={"0 0 " + width + " " + height}
      width={width}
      height={height}
      className={className}
      aria-hidden="true"
      style={flip ? { transform: "scaleX(-1)" } : undefined}
    >
      <motion.path
        d={d}
        fill="none"
        stroke="#2F6B4A"
        strokeWidth="2"
        strokeDasharray="6 7"
        strokeLinecap="round"
        initial={{ pathLength: 0, opacity: 0 }}
        whileInView={{ pathLength: 1, opacity: 0.6 }}
        viewport={{ once: true }}
        transition={{ duration: 1.1, ease: "easeInOut" }}
      />
    </svg>
  );
}

/** The horizontal connector used between conveyor stages and journey steps. */
export function StageConnector({ className = "" }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 10" className={className} aria-hidden="true" preserveAspectRatio="none">
      <path
        d="M1 5h52"
        stroke="#C9BFA9"
        strokeWidth="1.5"
        strokeDasharray="4 5"
        strokeLinecap="round"
        fill="none"
      />
      <path d="M52 1.5 58.5 5 52 8.5Z" fill="#C9BFA9" />
    </svg>
  );
}
