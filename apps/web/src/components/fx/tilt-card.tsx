"use client";

import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring } from "motion/react";
import { useRef, type PointerEvent, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Card that tilts in 3D toward the pointer, with a spotlight that follows the cursor.
 * Disabled for touch input and for users who prefer reduced motion.
 */
export function TiltCard({
  children,
  className,
  max = 7,
  spotlight = true,
  lift = true,
  onClick,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  max?: number;
  spotlight?: boolean;
  lift?: boolean;
  onClick?: () => void;
  as?: "div" | "button";
}) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement & HTMLButtonElement>(null);
  const rx = useMotionValue(0);
  const ry = useMotionValue(0);
  const mx = useMotionValue(50);
  const my = useMotionValue(50);
  const srx = useSpring(rx, { stiffness: 220, damping: 22 });
  const sry = useSpring(ry, { stiffness: 220, damping: 22 });
  const light = useMotionTemplate`radial-gradient(420px circle at ${mx}% ${my}%, color-mix(in oklch, var(--brand) 22%, transparent), transparent 62%)`;

  function onMove(e: PointerEvent<HTMLElement>) {
    if (reduce || e.pointerType !== "mouse" || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    ry.set((px - 0.5) * max * 2);
    rx.set(-(py - 0.5) * max * 2);
    mx.set(px * 100);
    my.set(py * 100);
  }

  function onLeave() {
    rx.set(0);
    ry.set(0);
  }

  const Comp = as === "button" ? motion.button : motion.div;
  return (
    <Comp
      ref={ref}
      type={as === "button" ? "button" : undefined}
      onClick={onClick}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      whileHover={lift && !reduce ? { y: -3 } : undefined}
      whileTap={as === "button" && !reduce ? { scale: 0.97 } : undefined}
      transition={{ type: "spring", stiffness: 300, damping: 24 }}
      style={{ rotateX: srx, rotateY: sry, transformPerspective: 900 }}
      className={cn("group/tilt relative [transform-style:preserve-3d]", className)}
    >
      {children}
      {spotlight && !reduce && (
        <motion.span
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover/tilt:opacity-100"
          style={{ background: light }}
        />
      )}
    </Comp>
  );
}
