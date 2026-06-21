const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const JOB_STATUSES = [
  { value: "discovered", label: "Discovered" },
  { value: "reviewing", label: "Researching" },
  { value: "applied", label: "Applied" },
  { value: "assessment", label: "Assessment" },
  { value: "interviewing", label: "Interviewing" },
  { value: "waitlist", label: "Waitlist" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "archived", label: "Archived" },
] as const;

export const api = {
  health: () => request<{ ok: boolean }>("/api/health"),
  jobs: () => request<{ jobs: import("./types").Job[] }>("/api/jobs"),
  job: (id: string) => request<import("./types").JobDetail>(`/api/jobs/${id}`),
  ingest: (body: { job_url?: string; job_text?: string }) =>
    request<{ job_id: string }>("/api/jobs/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateJobStatus: (id: string, status: string) =>
    request<{ job: import("./types").Job }>(`/api/jobs/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  deleteJob: (id: string) =>
    request<{ deleted: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
  runPipeline: (id: string, body: Record<string, unknown>) =>
    request<{ contact_count: number; drafts: number }>(`/api/jobs/${id}/pipeline`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelPipeline: (id: string) =>
    request<{ cancelled: boolean }>(`/api/jobs/${id}/pipeline/cancel`, { method: "POST" }),
  scoutResumes: () => request<{ resumes: { label: string; is_default?: boolean }[] }>("/api/scout/resumes"),
  scoutContext: (resumeLabel: string) =>
    request<{
      resume_label: string;
      search_terms: string[];
      focus_summary: string;
      profile_sources: string[];
      warnings: string[];
      location_default: string;
    }>(`/api/scout/context?resume_label=${encodeURIComponent(resumeLabel)}`),
  scoutRun: (body: Record<string, unknown>) =>
    request<{ report: Record<string, unknown> }>("/api/scout/run", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  scoutHistory: () => request<{ runs: Record<string, unknown>[] }>("/api/scout/history"),
  dashboard: () =>
    request<{ stats: import("./types").DashboardStats; last_scout: Record<string, unknown> | null }>(
      "/api/dashboard",
    ),
  network: () => request<import("./types").NetworkResponse>("/api/network"),
  settings: () => request<import("./types").SettingsResponse>("/api/settings"),
  activity: (limit = 60) => request<{ lines: import("./types").ActivityLine[] }>(`/api/activity?limit=${limit}`),
  clearActivity: () => request<{ cleared: boolean }>("/api/activity", { method: "DELETE" }),
  pipelineStatus: () =>
    request<{ runs: { job_id: string; step: string; company?: string; started_at: string; status: string }[] }>(
      "/api/pipeline/status",
    ),
  deleteContact: (id: string) =>
    request<{ deleted: boolean }>(`/api/contacts/${id}`, { method: "DELETE" }),
  deleteOutreach: (id: string) =>
    request<{ deleted: boolean }>(`/api/outreach/${id}`, { method: "DELETE" }),
  fetchCareerShiftEmail: (contactId: string, companyName?: string) =>
    request<{ email: string }>(`/api/contacts/${contactId}/careershift-email`, {
      method: "POST",
      body: JSON.stringify({ company_name: companyName ?? null }),
    }),
  testIntegration: (service: string) =>
    request<Record<string, unknown>>(`/api/integrations/test/${service}`, { method: "POST" }),
  integrationLogin: (provider: "careershift" | "handshake", clearProfile = false) =>
    request<{ ok: boolean; message: string }>(
      `/api/integrations/login/${provider}?clear_profile=${clearProfile}`,
      { method: "POST" },
    ),
};
