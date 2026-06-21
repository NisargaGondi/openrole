"use client";

import { useEffect, useRef } from "react";
import { Check, Circle } from "lucide-react";
import type { ActivityLine } from "@/lib/types";
import { cn } from "@/lib/utils";

type Stage = { tag: string; color: string };

function classifyLine(message: string): Stage | null {
  const modelTag = message.match(/^\[([^\]]+)\]/);
  if (modelTag && !modelTag[1].toLowerCase().includes("scout")) {
    return { tag: modelTag[1], color: "tag-violet" };
  }
  const m = message.toLowerCase();
  if (m.includes("[scout]") || m.includes("scout signal") || m.includes("scout complete") || m.includes("jobspy"))
    return { tag: "Scout", color: "tag-coral" };
  if (m.includes("careershift")) return { tag: "CareerShift", color: "tag-slate" };
  if (m.includes("tavily")) return { tag: "Tavily", color: "tag-sky" };
  if (m.includes("apollo")) return { tag: "Apollo", color: "tag-amber" };
  if (m.includes("batch research") || m.includes("synthes")) return { tag: "Research", color: "tag-violet" };
  if (m.includes("batch draft") || m.includes("outreach")) return { tag: "Draft", color: "tag-indigo" };
  if (m.includes("pipeline") && (m.includes("done") || m.includes("finish"))) return { tag: "Done", color: "tag-ok" };
  if (m.includes("validat")) return { tag: "Validate", color: "tag-slate" };
  return null;
}

function stripTimestamp(msg: string): string {
  return msg
    .replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, "")
    .replace(/^\[[^\]]+\]\s*/, "")
    .replace(/^\[scout\]\s*/i, "")
    .replace(/^▸\s*/, "")
    .trim();
}

type Props = {
  lines: ActivityLine[];
  onClear?: () => void;
  busy?: boolean;
  busyLabel?: string;
};

export function ActivityFeed({ lines, onClear, busy = false, busyLabel = "Running…" }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevLen = useRef(0);

  useEffect(() => {
    if (lines.length > prevLen.current && scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
    prevLen.current = lines.length;
  }, [lines.length]);

  const visible = lines.slice(-40);

  return (
    <div className="glass flex h-full max-h-[640px] flex-col rounded-2xl p-4">
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          <h3 className="text-sm font-bold text-body">Live Activity</h3>
        </div>
        {onClear && (
          <button type="button" onClick={onClear} className="text-xs font-semibold text-indigo-600 dark:text-indigo-300 hover:underline">
            Clear
          </button>
        )}
      </div>

      <div ref={scrollRef} className="activity-log min-h-0 flex-1 overflow-y-auto scroll-smooth px-3 py-4">
        {busy && (
          <p className="mb-3 flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs font-semibold text-emerald-100">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-70" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            {busyLabel}
          </p>
        )}
        {visible.length === 0 ? (
          <p className="text-sm text-muted">Pipeline events appear here as steps run.</p>
        ) : (
          <ul className="space-y-3">
            {visible.map((line, i) => {
              const stage = classifyLine(line.message);
              const isDone = stage?.tag === "Done" || line.level === "ok";
              const isNew = i === visible.length - 1;
              const text = stripTimestamp(line.message);

              return (
                <li
                  key={line.id}
                  className={cn(
                    "flex items-start gap-3 rounded-xl px-3 py-2.5",
                    isNew && "bg-white/8 ring-1 ring-white/10",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                      isDone ? "bg-emerald-500/90 text-white" : "bg-indigo-500/25 text-indigo-100",
                    )}
                  >
                    {isDone ? <Check className="h-3.5 w-3.5" /> : <Circle className="h-3 w-3" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    {(stage || line.level === "err") && (
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        {stage && <span className={cn("activity-tag", stage.color)}>{stage.tag}</span>}
                        {line.level === "err" && <span className="activity-tag tag-err">Error</span>}
                        <span className="text-[11px] text-slate-300/80">{line.ago}</span>
                      </div>
                    )}
                    {!stage && line.level !== "err" && (
                      <span className="mb-1 block text-[11px] text-slate-300/80">{line.ago}</span>
                    )}
                    <p
                      className={cn(
                        "text-sm leading-relaxed",
                        line.level === "ok" && "text-emerald-100",
                        line.level === "err" && "text-red-200",
                        line.level === "warn" && "text-amber-100",
                        (!line.level || line.level === "info") && "text-activity",
                      )}
                    >
                      {text}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <button
        type="button"
        onClick={() => (window.location.href = "/activity")}
        className="mt-3 shrink-0 text-left text-xs font-semibold text-indigo-600 dark:text-indigo-300 hover:underline"
      >
        View all activity →
      </button>
    </div>
  );
}
