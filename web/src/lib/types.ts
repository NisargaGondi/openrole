import type { VisaSummary } from "@/lib/visa";

export type ResumeAnalysis = {
  resume_label?: string;
  match_score?: number;
  summary?: string;
  strengths?: string[];
  gaps?: string[];
  missing_keywords?: string[];
  ats_risks?: string[];
  recommended_resume?: string | null;
};

export type Job = {
  id: string;
  title: string;
  company: string | null;
  company_id: string | null;
  company_domain: string | null;
  locations: string[];
  description: string | null;
  source_url: string | null;
  status: string;
  status_label: string;
  scout_score: number | null;
  scout_source: string | null;
  visa?: VisaSummary | null;
  resume_score: number | null;
  resume_label?: string | null;
  resume_analyses?: Record<string, ResumeAnalysis> | null;
  resume_skills: number | null;
  resume_experience: number | null;
  resume_culture: number | null;
  created_at: string | null;
  resume_report?: Record<string, unknown> | null;
};

export type Contact = {
  id: string;
  full_name: string;
  title: string | null;
  email: string | null;
  linkedin_url: string | null;
  location: string | null;
  has_research: boolean;
  research_hook: string | null;
  research_brief: Record<string, unknown> | null;
  tier: string | null;
  is_cmu_alumni?: boolean;
  email_ai_generated?: boolean;
};

export type OutreachDraft = {
  id: string;
  contact_id: string;
  contact_name: string | null;
  contact_title: string | null;
  channel: string;
  subject: string | null;
  body: string;
  status: string;
  ai_generated?: boolean;
  generator?: string;
  job_id?: string;
  job_title?: string;
};

export type DashboardStats = {
  total_jobs: number;
  jobs_by_status: Record<string, number>;
  scout_jobs: number;
  pending_outreach: number;
  total_contacts: number;
  companies_total: number;
};

export type NetworkCompany = {
  company_id: string;
  company_name: string;
  company_domain: string | null;
  jobs: { id: string; title: string; status: string }[];
  contacts: Contact[];
  drafts: OutreachDraft[];
};

export type NetworkResponse = {
  companies: NetworkCompany[];
  total_companies: number;
  total_roles: number;
  total_contacts: number;
  total_drafts: number;
  cmu_alumni_count: number;
};

export type SettingsResponse = {
  app_env: string;
  llm_provider: string;
  llm_models: {
    provider: string;
    ingestion: string;
    research: string;
    writing: string;
    fast: string;
    default: string;
  };
  integrations: { key: string; name: string; ok: boolean }[];
  careershift_daemon?: {
    mode: string;
    running: boolean;
    pid?: number | null;
    socket?: string;
    logged_in?: boolean;
    headless?: boolean;
    searches?: number;
    idle_s?: number;
  };
  handshake_daemon?: {
    mode: string;
    running: boolean;
    pid?: number | null;
    socket?: string;
    headless?: boolean;
    calls?: number;
    idle_s?: number;
  };
  browser_daemon_on_demand?: boolean;
  profile: Record<string, unknown>;
  usage: {
    services: { key: string; calls: number; est_cost_usd: number; rate_usd: number }[];
    total_est_cost_usd: number;
    activity_lines_scanned?: number;
    event_count?: number;
    by_job?: {
      job_id: string;
      job_title?: string;
      company?: string;
      total_cost_usd: number;
      total_calls: number;
      steps: Record<string, number>;
      services: Record<string, number>;
    }[];
    recent?: {
      service: string;
      calls: number;
      est_cost_usd: number;
      job_id?: string;
      company?: string;
      pipeline_step?: string;
      detail?: string;
      created_at?: string;
    }[];
  };
};

export type PipelineState = Record<string, "done" | "pending">;

export type ActivityLine = {
  id: number;
  time: string;
  ago: string;
  message: string;
  level: string;
  icon: string;
};

export type JobDetail = {
  job: Job;
  contacts: Contact[];
  drafts: OutreachDraft[];
  draft_count: number;
  pipeline: PipelineState;
};
