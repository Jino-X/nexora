"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform, type Variants } from "motion/react";
import { useEffect, type ReactNode } from "react";

const container: Variants = {
  hidden: {},
  show: (delay: number = 0) => ({ transition: { staggerChildren: 0.055, delayChildren: delay } }),
};

const item: Variants = {
  hidden: { opacity: 0, y: 16, scale: 0.98 },
  show: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: { type: "spring", stiffness: 260, damping: 26 },
  },
};

type Tag = "div" | "ul" | "li" | "section";

const MOTION = { div: motion.div, ul: motion.ul, li: motion.li, section: motion.section };

/** Children wrapped in <StaggerItem> fade and rise in one after another. */
export function Stagger({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: Tag;
}) {
  const Comp = MOTION[as];
  return (
    <Comp className={className} variants={container} initial="hidden" animate="show" custom={delay}>
      {children}
    </Comp>
  );
}

export function StaggerItem({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: Tag;
}) {
  const Comp = MOTION[as];
  return (
    <Comp className={className} variants={item}>
      {children}
    </Comp>
  );
}

/** Fade + rise for a single block. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 220, damping: 26, delay }}
    >
      {children}
    </motion.div>
  );
}

/** Counts up to `value` whenever it changes. */
export function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => Math.round(v).toLocaleString());
  useEffect(() => {
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, { duration: 1.1, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [mv, value, reduce]);
  return <motion.span className={className}>{text}</motion.span>;
}
