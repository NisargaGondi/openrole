"use client";

import { motion } from "framer-motion";

export function SignalBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/40 via-transparent to-orange-50/30" />
      <svg className="absolute inset-0 h-full w-full opacity-40" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="line-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#f97316" stopOpacity="0.1" />
          </linearGradient>
        </defs>
        {[
          [100, 200, 400, 350],
          [400, 350, 720, 280],
          [720, 280, 1100, 400],
        ].map(([x1, y1, x2, y2], i) => (
          <motion.line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="url(#line-grad)"
            strokeWidth={1}
            strokeDasharray="8 8"
            animate={{ strokeDashoffset: [0, -32] }}
            transition={{ repeat: Infinity, duration: 4 + i, ease: "linear" }}
          />
        ))}
      </svg>
    </div>
  );
}
