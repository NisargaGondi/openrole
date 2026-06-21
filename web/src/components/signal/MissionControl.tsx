"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ActivityFeed } from "@/components/signal/ActivityFeed";
import { JobHeaderCard } from "@/components/signal/JobHeaderCard";
import { NetworkFlowGraph } from "@/components/signal/NetworkFlowGraph";
import { PipelineRail } from "@/components/signal/PipelineRail";
import { StepWorkspace } from "@/components/signal/StepWorkspace";
import { api } from "@/lib/api";
import { usePipelineRun } from "@/components/signal/PipelineRunProvider";
import { stepLabel } from "@/lib/pipelineRun";
import { loadSession, saveSession, sessionFromSearchParams } from "@/lib/session";
import type { ActivityLine, Job, JobDetail } from "@/lib/types";

export function MissionControl() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [activeStep, setActiveStep] = useState("research");
  const [activity, setActivity] = useState<ActivityLine[]>([]);
  const [localLogs, setLocalLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isRunning, activeRun } = usePipelineRun();
  const running = isRunning(selectedId ?? undefined);

  const fromUrl = sessionFromSearchParams(searchParams);

  // Sync URL / sessionStorage when search params change (deferred to avoid sync setState in effect).
  useEffect(() => {
    const stored = loadSession();
    queueMicrotask(() => {
      setSelectedId(fromUrl.jobId ?? stored.jobId);
      setActiveStep(fromUrl.step ?? stored.step ?? "research");
    });
  }, [fromUrl.jobId, fromUrl.step]);

  const persist = useCallback(
    (jobId: string | null, step: string) => {
      saveSession({ jobId, step });
      const q = new URLSearchParams();
      if (jobId) q.set("job", jobId);
      if (step) q.set("step", step);
      router.replace(`/?${q.toString()}`, { scroll: false });
    },
    [router],
  );

  const refreshActivity = useCallback(async () => {
    try {
      const { lines } = await api.activity();
      setActivity(lines);
    } catch {
      /* offline */
    }
  }, []);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const { jobs: list } = await api.jobs();
      setJobs(list);
      setError(null);
      if (!list.length) {
        setSelectedId(null);
        return;
      }
      setSelectedId((current) => {
        const candidate = current ?? loadSession().jobId;
        if (candidate && list.some((j) => j.id === candidate)) {
          return candidate;
        }
        return list[0].id;
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const d = await api.job(id);
      setDetail(d);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadJobs();
      void refreshActivity();
    });
    const t = setInterval(refreshActivity, 3000);
    return () => clearInterval(t);
  }, [loadJobs, refreshActivity]);

  useEffect(() => {
    if (!selectedId) return;
    queueMicrotask(() => void loadDetail(selectedId));
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (selectedId) persist(selectedId, activeStep);
  }, [selectedId, activeStep, persist]);

  const setStep = (step: string) => {
    setActiveStep(step);
    if (selectedId) persist(selectedId, step);
  };

  const appendLocalLog = (msg: string) => {
    setLocalLogs((prev) => [...prev.slice(-30), msg]);
    refreshActivity();
  };

  const displayActivity: ActivityLine[] = [
    ...activity,
    ...localLogs.map((message, i) => ({
      id: 9000 + i,
      time: "",
      ago: "live",
      message,
      level: "info",
      icon: "dot",
    })),
  ];

  if (loading) {
    return <p className="py-20 text-center text-slate-500">Loading mission control…</p>;
  }

  if (!jobs.length) {
    return (
      <div className="glass mx-auto max-w-lg rounded-2xl p-8 text-center">
        <h2 className="text-xl font-bold text-slate-800">No roles yet</h2>
        <p className="mt-2 text-slate-500">Ingest a URL in Library or run Scout.</p>
        <a href="/library" className="btn-primary mt-6 inline-block">Go to Library</a>
      </div>
    );
  }

  const job =
    detail?.job ??
    (selectedId ? jobs.find((j) => j.id === selectedId) : undefined);

  if (!job) {
    return <p className="py-20 text-center text-slate-500">Loading role…</p>;
  }

  return (
    <div>
      {error && <div className="mb-4 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>}

      {(running || (activeRun && activeRun.jobId === selectedId)) && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <span className="pipeline-chip flex items-center gap-2 rounded-full bg-orange-50 px-3 py-1.5 text-xs font-semibold text-orange-600 ring-1 ring-orange-200 dark:bg-orange-950/50 dark:text-orange-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-500" />
            </span>
            {activeRun ? stepLabel(activeRun.step) : "Pipeline running…"}
          </span>
        </div>
      )}

      <JobHeaderCard
        job={job}
        pipeline={detail?.pipeline ?? { people: "pending", research: "pending", outreach: "pending", apply: "pending" }}
        onRefresh={() => selectedId && loadDetail(selectedId)}
        onLog={appendLocalLog}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-3">
          {detail && (
            <PipelineRail pipeline={detail.pipeline} activeStep={activeStep} onStepClick={setStep} />
          )}
        </div>
        <div className="lg:col-span-6">
          {detail && (
            <>
              <NetworkFlowGraph
                job={detail.job}
                contacts={detail.contacts}
                pipeline={detail.pipeline}
                activeStep={activeStep}
                cmuAlumniCount={detail.contacts.filter((c) => c.is_cmu_alumni).length}
                researchedCount={detail.contacts.filter((c) => c.has_research).length}
              />

              <StepWorkspace
                step={activeStep}
                detail={detail}
                onRefresh={() => selectedId && loadDetail(selectedId)}
                onLog={appendLocalLog}
                onStepDone={setStep}
              />
            </>
          )}
        </div>
        <div className="lg:col-span-3">
          <ActivityFeed
            lines={displayActivity}
            busy={running}
            busyLabel="Pipeline running…"
            onClear={() => api.clearActivity().then(() => { setLocalLogs([]); refreshActivity(); })}
          />
        </div>
      </div>
    </div>
  );
}
