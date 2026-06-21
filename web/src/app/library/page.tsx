"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { ActivityFeed } from "@/components/signal/ActivityFeed";
import { CompanyLogo } from "@/components/signal/CompanyLogo";
import { FormattedText, normalizeDescription } from "@/components/signal/FormattedText";
import { VisaTags } from "@/components/signal/VisaTags";
import { ResumeScoreBadge } from "@/components/signal/ResumeScoreBadge";
import { api, JOB_STATUSES } from "@/lib/api";
import { saveSession } from "@/lib/session";
import type { ActivityLine, Job } from "@/lib/types";

function searchText(html: string | null): string {
  return normalizeDescription(html).slice(0, 5000);
}

export default function LibraryPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [url, setUrl] = useState("");
  const [jobText, setJobText] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [ingestError, setIngestError] = useState<string | null>(null);
  const [activity, setActivity] = useState<ActivityLine[]>([]);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = () => {
    api.jobs().then((r) => setJobs(r.jobs));
    api.activity().then((a) => setActivity(a.lines));
  };

  useEffect(() => { load(); }, []);

  const canIngest = Boolean(url.trim() || jobText.trim());

  const ingest = async () => {
    if (!canIngest || ingesting) return;
    setIngestError(null);
    setIngesting(true);
    try {
      const { job_id } = await api.ingest({
        job_url: url.trim() || undefined,
        job_text: jobText.trim() || undefined,
      });
      saveSession({ jobId: job_id, step: "people" });
      setUrl("");
      setJobText("");
      load();
    } catch (err) {
      setIngestError(err instanceof Error ? err.message : "Ingest failed");
    } finally {
      setIngesting(false);
    }
  };

  const updateStatus = async (jobId: string, status: string) => {
    await api.updateJobStatus(jobId, status);
    load();
  };

  const filtered = jobs.filter(
    (j) =>
      !search ||
      `${j.title} ${j.company} ${searchText(j.description ?? "")}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 space-y-4">
        <div>
          <h1 className="text-2xl font-extrabold signal-gradient-text">Library</h1>
          <p className="text-sm text-muted">Saved roles · status tracking · descriptions</p>
        </div>
        <div className="glass rounded-2xl p-5 space-y-3">
          <h3 className="font-bold text-slate-800 dark:text-white">Ingest signal</h3>
          <input
            placeholder="Job URL — Greenhouse, Lever, Handshake, Indeed…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="w-full rounded-xl border border-indigo-100 bg-white/80 px-3 py-2 text-body dark:border-indigo-500/30 dark:bg-slate-900/50"
          />
          <div>
            <label htmlFor="job-text" className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
              Paste description <span className="font-normal normal-case">(optional)</span>
            </label>
            <textarea
              id="job-text"
              placeholder="Full job description — used for parsing when the URL scrape is thin, or paste-only ingest for LinkedIn/Indeed"
              value={jobText}
              onChange={(e) => setJobText(e.target.value)}
              rows={5}
              className="w-full resize-y rounded-xl border border-indigo-100 bg-white/80 px-3 py-2 text-sm leading-relaxed text-body dark:border-indigo-500/30 dark:bg-slate-900/50"
            />
            <p className="mt-1 text-xs text-muted">
              Provide a URL, pasted text, or both — pasted text improves parsing and fills the description when scraping fails.
            </p>
          </div>
          {ingestError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {ingestError}
            </p>
          )}
          <button
            type="button"
            onClick={ingest}
            disabled={!canIngest || ingesting}
            className="btn-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {ingesting ? "Ingesting…" : "Ingest & open"}
          </button>
        </div>
        <input
          placeholder="Search roles, companies, description text…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-indigo-100 bg-white/80 px-4 py-2 dark:border-indigo-500/30 dark:bg-slate-900/50"
        />
        <div className="space-y-3">
          {filtered.map((j) => {
            const desc = j.description;
            const open = expandedId === j.id;
            return (
              <div key={j.id} className="glass overflow-hidden rounded-2xl">
                <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex gap-3">
                    <CompanyLogo domain={j.company_domain} company={j.company} size={44} />
                    <div className="min-w-0">
                      <p className="text-xs font-bold uppercase text-indigo-600">{j.company}</p>
                      <p className="font-bold text-slate-900 dark:text-white">{j.title}</p>
                      <VisaTags visa={j.visa} className="mt-2" />
                      <ResumeScoreBadge job={j} className="mt-2" />
                      <div className="mt-2">
                        <label className="sr-only">Status</label>
                        <select
                          value={j.status}
                          onChange={(e) => updateStatus(j.id, e.target.value)}
                          className="rounded-lg border border-indigo-100 bg-white px-2 py-1 text-xs font-semibold text-slate-700 dark:border-indigo-500/30 dark:bg-slate-900"
                        >
                          {JOB_STATUSES.map((s) => (
                            <option key={s.value} value={s.value}>{s.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Link
                      href={`/?job=${j.id}&step=role`}
                      onClick={() => saveSession({ jobId: j.id, step: "role" })}
                      className="rounded-full bg-indigo-100 px-4 py-2 text-sm font-semibold text-indigo-700 dark:bg-indigo-900 dark:text-indigo-200"
                    >
                      Mission Control
                    </Link>
                    {j.source_url && (
                      <a
                        href={j.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1 rounded-full border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600"
                      >
                        View <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => api.deleteJob(j.id).then(load)}
                      className="rounded-full border border-red-200 px-4 py-2 text-sm font-semibold text-red-600"
                    >
                      Delete
                    </button>
                  </div>
                </div>
                {desc && (
                  <div className="border-t border-indigo-100/80 px-4 py-3 dark:border-indigo-500/20">
                    <button
                      type="button"
                      onClick={() => setExpandedId(open ? null : j.id)}
                      className="flex w-full items-center justify-between text-left text-xs font-bold uppercase tracking-wide text-indigo-600"
                    >
                      Job description
                      {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                    </button>
                    <div className={`mt-2 ${open ? "max-h-[28rem] overflow-y-auto pr-1" : "line-clamp-4"}`}>
                      <FormattedText text={desc} />
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <ActivityFeed lines={activity} />
    </div>
  );
}
