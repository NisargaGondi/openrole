"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Check, Circle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { usePipelineRun } from "@/components/signal/PipelineRunProvider";
import { stepLabel } from "@/lib/pipelineRun";
import type { ActivityLine } from "@/lib/types";
import { cn } from "@/lib/utils";

export function NotificationsPanel() {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<ActivityLine[]>([]);
  const ref = useRef<HTMLDivElement>(null);
  const { activeRun } = usePipelineRun();

  const refresh = () => api.activity().then((a) => setLines(a.lines.slice(-8).reverse())).catch(() => {});

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const unread = (activeRun ? 1 : 0) + lines.filter((l) => l.level === "info" || l.level === "ok").length;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => { setOpen((v) => !v); refresh(); }}
        className="relative rounded-full p-2 text-slate-400 transition hover:bg-indigo-50 hover:text-indigo-600 dark:hover:bg-slate-800"
        aria-label="Notifications"
      >
        <Bell className="h-5 w-5" />
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-500" />
          </span>
        )}
      </button>

      {open && (
        <div className="glass-float absolute right-0 top-full z-50 mt-2 w-[min(360px,calc(100vw-2rem))] overflow-hidden rounded-2xl shadow-xl">
          <div className="border-b border-indigo-100/80 px-4 py-3 dark:border-indigo-500/20">
            <p className="text-sm font-bold text-slate-900 dark:text-white">Notifications</p>
          </div>
          <ul className="max-h-[320px] overflow-y-auto p-2">
            {activeRun && (
              <li className="mb-1 rounded-xl bg-orange-50 px-3 py-2.5 dark:bg-orange-950/40">
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-orange-500" />
                  <div>
                    <p className="text-xs font-bold text-orange-700 dark:text-orange-300">
                      {stepLabel(activeRun.step)} in progress
                    </p>
                    <Link
                      href={`/?job=${activeRun.jobId}&step=${activeRun.step}`}
                      onClick={() => setOpen(false)}
                      className="text-[10px] font-semibold text-indigo-600 hover:underline"
                    >
                      Return to mission control →
                    </Link>
                  </div>
                </div>
              </li>
            )}
            {lines.map((line) => (
              <li key={line.id} className="flex gap-2 rounded-xl px-3 py-2 hover:bg-indigo-50/80 dark:hover:bg-indigo-950/30">
                {line.level === "ok" ? (
                  <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                ) : (
                  <Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-400" />
                )}
                <div>
                  <p className={cn("text-xs", line.level === "err" && "text-red-600")}>{line.message}</p>
                  <p className="text-[10px] text-slate-400">{line.ago}</p>
                </div>
              </li>
            ))}
            {!activeRun && lines.length === 0 && (
              <li className="px-3 py-6 text-center text-xs text-slate-500">No recent activity</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
