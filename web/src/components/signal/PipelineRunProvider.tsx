"use client";

import Link from "next/link";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import {
  clearPipelineRun,
  loadPipelineRun,
  savePipelineRun,
  stepLabel,
  type PipelineRunState,
} from "@/lib/pipelineRun";
import { saveSession } from "@/lib/session";

type Ctx = {
  activeRun: PipelineRunState | null;
  cancelling: boolean;
  isRunning: (jobId?: string) => boolean;
  startRun: (run: Omit<PipelineRunState, "startedAt">) => void;
  finishRun: () => void;
  markCancelling: () => void;
  requestCancel: (jobId: string) => Promise<boolean>;
};

const PipelineRunCtx = createContext<Ctx>({
  activeRun: null,
  cancelling: false,
  isRunning: () => false,
  startRun: () => {},
  finishRun: () => {},
  markCancelling: () => {},
  requestCancel: async () => false,
});

export function PipelineRunProvider({ children }: { children: React.ReactNode }) {
  const [activeRun, setActiveRun] = useState<PipelineRunState | null>(() =>
    typeof window !== "undefined" ? loadPipelineRun() : null,
  );
  const [cancelling, setCancelling] = useState(false);

  const syncFromServer = useCallback(async () => {
    try {
      const { runs } = await api.pipelineStatus();
      if (runs.length) {
        const r = runs[0];
        const next: PipelineRunState = {
          jobId: r.job_id,
          step: r.step,
          company: r.company ?? undefined,
          startedAt: r.started_at,
        };
        setActiveRun(next);
        savePipelineRun(next);
        setCancelling(r.status === "cancelling");
        return;
      }
      setActiveRun((prev) => {
        if (prev) clearPipelineRun();
        return null;
      });
      setCancelling(false);
    } catch {
      /* API offline — keep sessionStorage state */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (!cancelled) await syncFromServer();
    };
    void poll();
    const t = setInterval(() => void poll(), 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [syncFromServer]);

  const startRun = useCallback((run: Omit<PipelineRunState, "startedAt">) => {
    const next = { ...run, startedAt: new Date().toISOString() };
    setActiveRun(next);
    setCancelling(false);
    savePipelineRun(next);
  }, []);

  const finishRun = useCallback(() => {
    setActiveRun(null);
    setCancelling(false);
    clearPipelineRun();
  }, []);

  const markCancelling = useCallback(() => {
    setCancelling(true);
  }, []);

  const requestCancel = useCallback(
    async (jobId: string) => {
      markCancelling();
      try {
        await api.cancelPipeline(jobId);
        return true;
      } catch {
        finishRun();
        return false;
      }
    },
    [finishRun, markCancelling],
  );

  const value = useMemo(
    () => ({
      activeRun,
      cancelling,
      isRunning: (jobId?: string) =>
        !!activeRun && (!jobId || activeRun.jobId === jobId),
      startRun,
      finishRun,
      markCancelling,
      requestCancel,
    }),
    [activeRun, cancelling, startRun, finishRun, markCancelling, requestCancel],
  );

  return (
    <PipelineRunCtx.Provider value={value}>
      {activeRun && (
        <div className="pipeline-banner fixed left-1/2 top-[4.5rem] z-[60] w-[min(640px,calc(100vw-2rem))] -translate-x-1/2">
          <div className="flex items-center gap-3 rounded-2xl border border-orange-200/80 bg-white/95 px-4 py-2.5 shadow-lg shadow-orange-500/10 backdrop-blur-xl dark:border-orange-500/30 dark:bg-slate-900/95">
            <span className="relative flex h-8 w-8 shrink-0 items-center justify-center">
              <span className="absolute inset-0 animate-ping rounded-full bg-orange-400/40" />
              <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-orange-400 to-indigo-500 text-white">
                <Loader2 className="h-4 w-4 animate-spin" />
              </span>
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-slate-900 dark:text-white">
                {cancelling
                  ? "Cancelling pipeline…"
                  : `Pipeline running — ${stepLabel(activeRun.step)}`}
              </p>
              <p className="truncate text-xs text-slate-500">
                {activeRun.company ?? "Role"} · safe to switch tabs — progress continues on server
              </p>
            </div>
            <Link
              href={`/?job=${activeRun.jobId}&step=${activeRun.step}`}
              onClick={() => saveSession({ jobId: activeRun.jobId, step: activeRun.step })}
              className="shrink-0 rounded-full bg-indigo-100 px-3 py-1.5 text-xs font-bold text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-900 dark:text-indigo-200"
            >
              View
            </Link>
            {!cancelling && (
              <button
                type="button"
                onClick={() => requestCancel(activeRun.jobId)}
                className="shrink-0 rounded-full border border-red-200 px-2.5 py-1.5 text-xs font-bold text-red-600"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
      {children}
    </PipelineRunCtx.Provider>
  );
}

export function usePipelineRun() {
  return useContext(PipelineRunCtx);
}
