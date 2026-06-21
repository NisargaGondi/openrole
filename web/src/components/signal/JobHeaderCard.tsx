"use client";

import { ExternalLink, Play, XCircle } from "lucide-react";
import type { Job, PipelineState } from "@/lib/types";
import { CompanyLogo } from "@/components/signal/CompanyLogo";
import { VisaTags } from "@/components/signal/VisaTags";
import { ResumeScoreBadge } from "@/components/signal/ResumeScoreBadge";
import { usePipelineRun } from "@/components/signal/PipelineRunProvider";
import {
  describeRemainingSteps,
  remainingPipelineOpts,
  streamPipeline,
} from "@/lib/pipelineStream";

type Props = {
  job: Job;
  pipeline: PipelineState;
  onRefresh?: () => void;
  onLog?: (msg: string) => void;
};

export function JobHeaderCard({ job, pipeline, onRefresh, onLog }: Props) {
  const { isRunning, cancelling, startRun, finishRun, requestCancel } = usePipelineRun();
  const running = isRunning(job.id);

  const scoutScore = job.scout_score;
  const resumeScore = job.resume_score;
  const displayScore = resumeScore ?? scoutScore;
  const skills = job.resume_skills ?? (displayScore != null ? Math.min(displayScore + 5, 98) : null);
  const exp = job.resume_experience ?? (displayScore != null ? Math.max(displayScore - 3, 70) : null);
  const culture = job.resume_culture ?? (displayScore != null ? Math.max(displayScore - 9, 65) : null);
  const loc = job.locations?.[0] ?? "Remote";

  const remaining = remainingPipelineOpts(pipeline, true);
  const remainingLabel = describeRemainingSteps(pipeline, true);
  const allComplete = !remaining;

  const runFullPipeline = () => {
    if (running) return;
    if (!remaining) {
      onLog?.("All pipeline steps are already complete for this role.");
      return;
    }
    startRun({ jobId: job.id, step: "pipeline", company: job.company ?? undefined });
    onLog?.(`Starting pipeline: ${remainingLabel}…`);
    const close = streamPipeline(job.id, remaining, (ev) => {
      if (ev.type === "log" || ev.type === "start") onLog?.(ev.message);
      if (ev.type === "cancelling") onLog?.(ev.message);
      if (ev.type === "done") {
        onLog?.(ev.message);
        finishRun();
        onRefresh?.();
        close();
      }
      if (ev.type === "cancelled") {
        onLog?.(ev.message);
        finishRun();
        onRefresh?.();
        close();
      }
      if (ev.type === "error") {
        onLog?.(ev.message);
        finishRun();
        close();
      }
    });
  };

  const cancelPipeline = () => {
    requestCancel(job.id).then((ok) => {
      if (ok) onLog?.("Cancel requested — stopping after current step…");
    });
  };

  const runButtonLabel = allComplete
    ? "Pipeline complete"
    : remainingLabel === "people → research → outreach → resume"
      ? "Run full pipeline"
      : `Continue: ${remainingLabel}`;

  return (
    <div className="glass mb-4 rounded-2xl p-4 md:p-5">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-start gap-4">
          <CompanyLogo domain={job.company_domain} company={job.company} size={56} />
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-bold text-slate-900 md:text-xl dark:text-white">
                {job.title} · {job.company}
              </h1>
            </div>
            <p className="mt-1 text-sm text-muted">
              {loc} · Full-time · {job.status_label}
            </p>
            <VisaTags visa={job.visa} size="md" className="mt-2" />
            <ResumeScoreBadge job={job} className="mt-2" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {job.source_url && (
            <a
              href={job.source_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:border-indigo-200 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
            >
              View Job <ExternalLink className="h-4 w-4" />
            </a>
          )}
          {running ? (
            <button
              type="button"
              onClick={cancelPipeline}
              disabled={cancelling}
              className="flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-600 disabled:opacity-70"
            >
              <XCircle className="h-4 w-4" /> {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          ) : (
            <button
              type="button"
              onClick={runFullPipeline}
              disabled={allComplete}
              className="btn-primary flex items-center gap-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Play className="h-4 w-4 fill-current" /> {runButtonLabel}
            </button>
          )}
        </div>
      </div>
      {displayScore != null && (
        <div className="mt-4 flex flex-col gap-3 border-t border-indigo-100/80 pt-4 md:flex-row md:items-center md:gap-8 dark:border-indigo-500/20">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-indigo-700 dark:text-indigo-300">{displayScore}</span>
            <span className="text-sm font-semibold text-muted">
              {resumeScore != null ? "Resume match" : "Scout score"}
            </span>
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 via-violet-500 to-orange-400"
                style={{ width: `${displayScore}%` }}
              />
            </div>
            {skills != null && exp != null && culture != null && (
              <div className="flex flex-wrap gap-4 text-xs text-muted">
                <span>Skills <strong className="text-heading">{skills}%</strong></span>
                <span>Experience <strong className="text-heading">{exp}%</strong></span>
                <span>Culture <strong className="text-heading">{culture}%</strong></span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
