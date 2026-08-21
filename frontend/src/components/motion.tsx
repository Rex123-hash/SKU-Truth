"use client";

import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * The whole motion vocabulary for the site: a short rise on entry, a stagger for groups,
 * and a slow float for the hero cutouts. No springs that overshoot, no parallax, no
 * scroll-jacking. The product should feel calm and expensive.
 *
 * One rule holds throughout: `initial` is never branched on the reduced-motion
 * preference. `useReducedMotion()` reads a media query, which the server cannot see, so
 * a component whose *initial* markup depends on it hydrates into a mismatch. `animate`
 * is applied after mount and is safe to branch. Everything else is handled by the
 * `MotionConfig` below, which is framer-motion's own reduced-motion path: it suppresses
 * transform animation for visitors who asked for that, while still landing every element
 * on its final opacity, so nothing can end up invisible.
 */

const EASE = [0.22, 0.61, 0.36, 1] as const;

export function MotionProvider({ children }: { children: ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

export function Rise({
  children,
  delay = 0,
  y = 14,
  className = "",
  once = true,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
  once?: boolean;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, amount: 0.2 }}
      transition={{ duration: 0.55, delay, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}

/** Wraps a group whose children should arrive one after another. */
export function Stagger({
  children,
  className = "",
  step = 0.08,
}: {
  children: ReactNode;
  className?: string;
  step?: number;
}) {
  return (
    <motion.div
      className={className}
      initial="hidden"
      whileInView="shown"
      viewport={{ once: true, amount: 0.15 }}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: step } } }}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({
  children,
  className = "",
  y = 12,
}: {
  children: ReactNode;
  className?: string;
  y?: number;
}) {
  return (
    <motion.div
      className={className}
      variants={{
        hidden: { opacity: 0, y },
        shown: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  );
}

/**
 * The hero cutouts drift a few pixels over several seconds. The element rendered is the
 * same either way; only the `animate` target is dropped when motion is unwelcome, so an
 * endless loop never runs against the visitor's stated preference.
 */
export function Float({
  children,
  className = "",
  distance = 5,
  duration = 7,
  delay = 0,
  rotate = 0,
}: {
  children: ReactNode;
  className?: string;
  distance?: number;
  duration?: number;
  delay?: number;
  rotate?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      animate={
        reduced
          ? undefined
          : { y: [0, -distance, 0], rotate: rotate ? [0, rotate, 0] : undefined }
      }
      transition={{ duration, delay, repeat: Infinity, ease: "easeInOut" }}
    >
      {children}
    </motion.div>
  );
}

export { motion, useReducedMotion };
