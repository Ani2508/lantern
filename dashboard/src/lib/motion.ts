import type { Transition, Variants } from "motion/react";

export const EASE = [0.22, 1, 0.36, 1] as const;
export const spring: Transition = { type: "spring", stiffness: 260, damping: 30 };
export const soft: Transition = { duration: 0.5, ease: EASE };

export const rise: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: soft },
  exit: { opacity: 0, y: -8, transition: { duration: 0.25, ease: EASE } },
};

export const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
