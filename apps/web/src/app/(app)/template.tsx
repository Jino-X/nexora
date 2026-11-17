"use client";

import { motion } from "motion/react";

/** Re-mounts on every navigation inside the app, giving each page a soft entrance. */
export default function AppTemplate({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 26, mass: 0.8 }}
    >
      {children}
    </motion.div>
  );
}
