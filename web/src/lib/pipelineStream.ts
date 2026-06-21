const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type PipelineEvent =
  | { type: "start"; message: string }
  | { type: "meta"; thread_id: string }
  | { type: "log"; message: string; node: string }
  | { type: "cancelling"; message: string }
  | { type: "done"; message: string; contact_count?: number; drafts?: number; interrupted?: boolean; errors?: string[] }
  | { type: "cancelled"; message: string }
  | { type: "error"; message: string };

export type PipelineStreamOpts = {
  run_people?: boolean;
  run_research?: boolean;
  run_outreach?: boolean;
  run_resume?: boolean;
  resume_label?: string;
  resume_labels?: string[];
  auto_approve?: boolean;
};

export type PipelineProgress = {
  people?: string;
  research?: string;
  outreach?: string;
  apply?: string;
};

const STEP_LABELS: Record<string, string> = {
  people: "people",
  research: "research",
  outreach: "outreach",
  apply: "resume",
};

/** Skip stages already marked done — mirrors Streamlit checkbox behavior. */
export function remainingPipelineOpts(
  pipeline: PipelineProgress,
  includeResume = true,
): PipelineStreamOpts | null {
  const run_people = pipeline.people !== "done";
  const run_research = pipeline.research !== "done";
  const run_outreach = pipeline.outreach !== "done";
  const run_resume = includeResume && pipeline.apply !== "done";
  if (!run_people && !run_research && !run_outreach && !run_resume) {
    return null;
  }
  return {
    run_people,
    run_research,
    run_outreach,
    run_resume,
    auto_approve: true,
  };
}

export function describeRemainingSteps(pipeline: PipelineProgress, includeResume = true): string {
  const opts = remainingPipelineOpts(pipeline, includeResume);
  if (!opts) return "All pipeline steps complete";
  const parts: string[] = [];
  if (opts.run_people) parts.push(STEP_LABELS.people);
  if (opts.run_research) parts.push(STEP_LABELS.research);
  if (opts.run_outreach) parts.push(STEP_LABELS.outreach);
  if (opts.run_resume) parts.push(STEP_LABELS.apply);
  return parts.join(" → ");
}

export function streamPipeline(
  jobId: string,
  opts: PipelineStreamOpts,
  onEvent: (ev: PipelineEvent) => void,
): () => void {
  const q = new URLSearchParams();
  if (opts.run_people) q.set("run_people", "true");
  if (opts.run_research) q.set("run_research", "true");
  if (opts.run_outreach) q.set("run_outreach", "true");
  if (opts.run_resume) q.set("run_resume", "true");
  if (opts.auto_approve) q.set("auto_approve", "true");
  if (opts.resume_labels?.length) {
    q.set("resume_labels", opts.resume_labels.join(","));
  } else if (opts.resume_label) {
    q.set("resume_label", opts.resume_label);
  }

  const url = `${API}/api/jobs/${jobId}/pipeline/stream?${q}`;
  const es = new EventSource(url);
  let intentionalClose = false;

  es.onmessage = (ev) => {
    try {
      onEvent(JSON.parse(ev.data) as PipelineEvent);
    } catch {
      /* ignore */
    }
  };
  es.onerror = () => {
    if (intentionalClose) return;
    // Tab navigation closes EventSource — backend may still be running; don't treat as fatal.
    fetch(`${API}/api/pipeline/status`)
      .then((r) => r.json())
      .then((body: { runs?: { job_id: string }[] }) => {
        const still = body.runs?.some((r) => r.job_id === jobId);
        if (!still) {
          onEvent({ type: "error", message: "Connection lost — check API server" });
        }
      })
      .catch(() => {
        onEvent({ type: "error", message: "Connection lost — check API server" });
      });
    intentionalClose = true;
    es.close();
  };

  return () => {
    intentionalClose = true;
    es.close();
  };
}

export function fullPipelineOpts(includeResume = true) {
  return {
    run_people: true,
    run_research: true,
    run_outreach: true,
    run_resume: includeResume,
    auto_approve: true,
  } satisfies PipelineStreamOpts;
}

export function pipelineOptsForStep(step: string) {
  switch (step) {
    case "people":
      return { run_people: true, run_research: false, run_outreach: false, run_resume: false };
    case "research":
      return { run_people: false, run_research: true, run_outreach: false, run_resume: false };
    case "outreach":
      return { run_people: false, run_research: false, run_outreach: true, run_resume: false };
    case "apply":
      return { run_people: false, run_research: false, run_outreach: false, run_resume: true };
    default:
      return { run_people: true, run_research: true, run_outreach: true, run_resume: false };
  }
}
