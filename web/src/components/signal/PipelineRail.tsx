"use client";

import {
  Briefcase,
  Check,
  FileText,
  Mail,
  Search,
  Target,
  Users,
} from "lucide-react";
import type { PipelineState } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS: { key: keyof PipelineState; label: string; icon: typeof Briefcase }[] = [
  { key: "role", label: "Define Role & Goals", icon: Briefcase },
  { key: "qualify", label: "Find & Qualify Opportunities", icon: Target },
  { key: "people", label: "Map Your Network", icon: Users },
  { key: "research", label: "Research & Personalize", icon: Search },
  { key: "outreach", label: "Outreach & Engage", icon: Mail },
  { key: "nurture", label: "Nurture & Stay Top of Mind", icon: Users },
  { key: "apply", label: "Convert to Interview", icon: FileText },
];

type Props = {
  pipeline: PipelineState;
  onStepClick?: (key: string) => void;
  activeStep?: string;
};

export function PipelineRail({ pipeline, onStepClick, activeStep }: Props) {
  const doneCount = STEPS.filter((s) => pipeline[s.key] === "done").length;

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-800">Your Search Pipeline</h3>
        <span className="text-xs font-semibold text-indigo-600">
          {doneCount} / {STEPS.length} completed
        </span>
      </div>
      <ol className="space-y-1">
        {STEPS.map((step, i) => {
          const state = pipeline[step.key] ?? "pending";
          const isSelected = activeStep === step.key;
          const Icon = step.icon;
          return (
            <li key={step.key}>
              <button
                type="button"
                onClick={() => onStepClick?.(step.key)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition",
                  isSelected && "bg-orange-50 ring-1 ring-orange-200 dark:bg-orange-950/40",
                  state === "done" && !isSelected && "opacity-80",
                )}
              >
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2",
                    state === "done" && "border-indigo-500 bg-indigo-50 text-indigo-600",
                    isSelected && state !== "done" && "border-orange-500 bg-orange-50 text-orange-600 pulse-active",
                    !isSelected && state !== "done" && "border-slate-200 text-slate-400",
                  )}
                >
                  {state === "done" ? <Check className="h-4 w-4" /> : <Icon className="h-4 w-4" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-semibold text-slate-800">{step.label}</span>
                </span>
                <span className="text-[10px] font-bold text-slate-300">{i + 1}</span>
              </button>
              {i < STEPS.length - 1 && (
                <div
                  className={cn(
                    "ml-[1.35rem] h-3 w-0.5",
                    state === "done" ? "bg-gradient-to-b from-indigo-400 to-orange-300" : "bg-slate-200",
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
      <div className="mt-4 rounded-xl bg-indigo-50/80 p-3 text-[11px] leading-relaxed text-indigo-900">
        <strong>Pro tip:</strong> Adding 3+ personalized details to outreach increases reply rate by 2.6×.
      </div>
    </div>
  );
}
