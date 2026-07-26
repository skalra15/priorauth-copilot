"use client";

import { motion, type Variants } from "motion/react";

const EASE_OUT_SMOOTH = [0.16, 1, 0.3, 1] as const;

const variants: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0 },
};

/** Fade+slide reveal triggered once when scrolled into view. Runs once
 * (viewport.once) per the "no continuous/looping decorative animation"
 * guideline -- this tells a one-time story as the page unfolds, it doesn't
 * loop or scroll-jack. Respects prefers-reduced-motion globally (see
 * globals.css) since Motion honors that media query automatically. */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      variants={variants}
      transition={{ duration: 0.6, ease: EASE_OUT_SMOOTH, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Staggered children reveal -- use for grids/lists where each item should
 * cascade in rather than all firing at once. */
export function RevealGroup({
  children,
  className,
  stagger = 0.08,
}: {
  children: React.ReactNode;
  className?: string;
  stagger?: number;
}) {
  return (
    <motion.div
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
      transition={{ staggerChildren: stagger }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function RevealItem({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      variants={variants}
      transition={{ duration: 0.5, ease: EASE_OUT_SMOOTH }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
