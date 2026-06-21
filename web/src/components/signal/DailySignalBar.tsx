"use client";

import { Sparkles, X } from "lucide-react";
import { useState } from "react";

export function DailySignalBar() {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  return (
    <div className="fixed bottom-4 left-1/2 z-40 w-[min(640px,calc(100%-2rem))] -translate-x-1/2">
      <div className="glass flex items-center gap-3 rounded-2xl border border-indigo-200/80 px-4 py-3 shadow-xl">
        <Sparkles className="h-5 w-5 shrink-0 text-orange-500" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold text-indigo-700">Daily Signal</p>
          <p className="truncate text-sm text-slate-600">
            People at target companies respond 42% more on Tuesdays 9–11am EST.
          </p>
        </div>
        <button type="button" className="shrink-0 rounded-full bg-indigo-100 px-3 py-1.5 text-xs font-semibold text-indigo-700">
          View Timing Insights
        </button>
        <button type="button" onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
