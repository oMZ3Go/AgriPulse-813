"use client";

import { motion, useReducedMotion } from "framer-motion";

export default function Template({ children }: { children: React.ReactNode }) {
  const reduced = useReducedMotion();
  // Keep server and initial client markup identical; CSS suppresses the offset
  // under reduced motion before hydration, while Motion skips the transition.
  return <motion.div data-page-transition initial={{ opacity: 1, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduced ? 0 : 0.3 }}>{children}</motion.div>;
}
