"use client";

import type { Job, ResumeAnalysis } from "@/lib/types";
import { cn } from "@/lib/utils";

function scoreColor(score: number) {
  if (score >= 80) return "resume-score-high";
  if (score >= 65) return "resume-score-mid";
  return "resume-score-low";
}

function sortedAnalyses(job: Job): { label: string; report: ResumeAnalysis }[] {
  const map = job.resume_analyses ?? {};
  const entries = Object.entries(map).map(([label, report]) => ({
    label: report.resume_label ?? label,
    report,
  }));
  entries.sort((a, b) => (b.report.match_score ?? 0) - (a.report.match_score ?? 0));
  if (entries.length) return entries;
  if (job.resume_report && job.resume_score != null) {
    const report = job.resume_report as ResumeAnalysis;
    const label =
      job.resume_label ??
      (typeof report.resume_label === "string" ? report.resume_label : "Resume");
    return [{ label, report }];
  }
  return [];
}

type Props = {
  job: Job;
  compact?: boolean;
  className?: string;
};

export function ResumeScoreBadge({ job, compact = false, className }: Props) {
  const analyses = sortedAnalyses(job);
  const scout = job.scout_score;

  if (!analyses.length && scout == null) {
    return (
      <span className={cn("resume-score-none inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold", className)}>
        No resume score
      </span>
    );
  }

  if (compact && analyses.length === 1) {
    const { label, report } = analyses[0];
    const score = report.match_score ?? job.resume_score;
    if (score == null) return null;
    return (
      <span
        className={cn("resume-score-pill inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold", scoreColor(score), className)}
        title={typeof report.summary === "string" ? report.summary : undefined}
      >
        <span className="opacity-80">{label}</span>
        <span>{score}</span>
      </span>
    );
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {scout != null && (
        <span className="resume-score-scout inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold" title="Scout relevance score">
          Scout {scout}
        </span>
      )}
      {analyses.map(({ label, report }) => {
        const score = report.match_score;
        if (score == null) return null;
        return (
          <span
            key={label}
            className={cn("resume-score-pill inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold", scoreColor(score))}
            title={typeof report.summary === "string" ? report.summary : undefined}
          >
            <span className="max-w-[8rem] truncate opacity-80">{label}</span>
            <span>{score}</span>
          </span>
        );
      })}
    </div>
  );
}

export function ResumeAnalysisList({ job }: { job: Job }) {
  const analyses = sortedAnalyses(job);
  if (!analyses.length) {
    return <p className="text-sm text-muted">No resume analysis yet — run Apply prep in Mission Control.</p>;
  }

  return (
    <div className="space-y-3">
      {analyses.map(({ label, report }) => (
        <details key={label} className="group rounded-xl bg-white/60 ring-1 ring-indigo-100 dark:bg-slate-900/40 dark:ring-indigo-500/20">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
            <span>
              {label}
              {report.match_score != null && (
                <span className={cn("ml-2 rounded-full px-2 py-0.5 text-xs", scoreColor(report.match_score))}>
                  {report.match_score}
                </span>
              )}
            </span>
            <span className="text-xs font-normal text-muted">View report</span>
          </summary>
          <div className="space-y-2 border-t border-indigo-50 px-4 pb-4 pt-3 text-sm text-body dark:border-indigo-500/20">
            {report.summary && <p>{report.summary}</p>}
            {report.strengths?.length ? (
              <div>
                <p className="text-xs font-bold uppercase text-muted">Strengths</p>
                <ul className="mt-1 list-disc pl-5">
                  {report.strengths.slice(0, 6).map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {report.gaps?.length ? (
              <div>
                <p className="text-xs font-bold uppercase text-muted">Gaps</p>
                <ul className="mt-1 list-disc pl-5">
                  {report.gaps.slice(0, 6).map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </details>
      ))}
    </div>
  );
}
