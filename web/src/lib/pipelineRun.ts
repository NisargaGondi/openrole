const KEY = "openrole_pipeline_run";

export type PipelineRunState = {
  jobId: string;
  step: string;
  company?: string;
  startedAt: string;
};

export function loadPipelineRun(): PipelineRunState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PipelineRunState;
  } catch {
    return null;
  }
}

export function savePipelineRun(run: PipelineRunState) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(KEY, JSON.stringify(run));
}

export function clearPipelineRun() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(KEY);
}

export function stepLabel(step: string): string {
  const labels: Record<string, string> = {
    pipeline: "Full pipeline",
    people: "Finding people",
    research: "Researching contacts",
    outreach: "Drafting outreach",
    apply: "Resume analysis",
  };
  return labels[step] ?? "Pipeline";
}
