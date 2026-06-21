"use client";

import { useCallback, useEffect, useState } from "react";
import { ActivityFeed } from "@/components/signal/ActivityFeed";
import { api } from "@/lib/api";
import type { ActivityLine } from "@/lib/types";

export default function ScoutPage() {
  const [resumes, setResumes] = useState<{ label: string; is_default?: boolean }[]>([]);
  const [resume, setResume] = useState("");
  const [terms, setTerms] = useState("");
  const [focusSummary, setFocusSummary] = useState("");
  const [profileSources, setProfileSources] = useState<string[]>([]);
  const [contextLoadedFor, setContextLoadedFor] = useState("");
  const contextLoading = !!resume && resume !== contextLoadedFor;
  const [location, setLocation] = useState("United States");
  const [resultsPerTerm, setResultsPerTerm] = useState(20);
  const [minScore, setMinScore] = useState(45);
  const [includeIndeed, setIncludeIndeed] = useState(true);
  const [includeLinkedin, setIncludeLinkedin] = useState(true);
  const [includeHandshake, setIncludeHandshake] = useState(true);
  const [includeTavily, setIncludeTavily] = useState(true);
  const [includeAts, setIncludeAts] = useState(true);
  const [requireOpt, setRequireOpt] = useState(false);
  const [runResumeAnalysis, setRunResumeAnalysis] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [activity, setActivity] = useState<ActivityLine[]>([]);

  const refreshActivity = useCallback(async () => {
    try {
      const { lines } = await api.activity();
      setActivity(lines);
    } catch {
      /* API may be busy during long scout — retry on next poll */
    }
  }, []);

  useEffect(() => {
    void api.scoutResumes().then((r) => {
      setResumes(r.resumes);
      const def = r.resumes.find((x) => x.is_default) ?? r.resumes[0];
      if (def) setResume(def.label);
    });
    queueMicrotask(() => void refreshActivity());
  }, [refreshActivity]);

  useEffect(() => {
    if (!resume) return;
    let cancelled = false;
    void api
      .scoutContext(resume)
      .then((ctx) => {
        if (cancelled) return;
        setTerms(ctx.search_terms.join(", "));
        setFocusSummary(ctx.focus_summary || "");
        setProfileSources(ctx.profile_sources || []);
        if (ctx.location_default) setLocation(ctx.location_default);
      })
      .catch(() => {
        if (!cancelled) setFocusSummary("");
      })
      .finally(() => {
        if (!cancelled) setContextLoadedFor(resume);
      });
    return () => {
      cancelled = true;
    };
  }, [resume]);

  // Poll Live Activity — faster while scout is running (backend logs via act_log during the run)
  useEffect(() => {
    const ms = running ? 1500 : 5000;
    const t = setInterval(refreshActivity, ms);
    return () => clearInterval(t);
  }, [running, refreshActivity]);

  const sites = [
    ...(includeIndeed ? ["indeed"] : []),
    ...(includeLinkedin ? ["linkedin"] : []),
  ];

  const run = async () => {
    if (!sites.length) {
      setResult("Enable at least Indeed or LinkedIn.");
      return;
    }
    setRunning(true);
    setResult(null);
    void refreshActivity();
    try {
      const { report } = await api.scoutRun({
        resume_label: resume,
        search_terms: terms.split(",").map((t) => t.trim()).filter(Boolean),
        location,
        results_per_term: resultsPerTerm,
        min_score: minScore,
        sites,
        include_handshake: includeHandshake,
        include_tavily: includeTavily,
        include_ats_boards: includeAts,
        require_opt_mention: requireOpt,
        run_resume_analysis: runResumeAnalysis,
        dry_run: dryRun,
      });
      setResult(
        `Scanned ${String(report.discovered ?? "?")} · ingested ${String(report.ingested_new ?? "?")} new roles`,
      );
      await refreshActivity();
    } catch (e) {
      setResult(String(e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2 space-y-4">
        <div>
          <h1 className="text-2xl font-extrabold signal-gradient-text">Scout</h1>
          <p className="text-sm text-slate-500">
            Broadcast resume signal → discover new roles from job boards & ATS (not the ⌘K role finder)
          </p>
        </div>
        <div className="glass space-y-4 rounded-2xl p-5">
          <label className="block text-sm font-semibold">Resume</label>
          <select value={resume} onChange={(e) => setResume(e.target.value)} className="w-full rounded-xl border border-indigo-100 px-3 py-2 dark:border-indigo-500/30 dark:bg-slate-900/50">
            {resumes.map((r) => (
              <option key={r.label} value={r.label}>{r.label}</option>
            ))}
          </select>
          {contextLoading && (
            <p className="text-xs text-muted">Loading resume signal (GitHub / LinkedIn / site)…</p>
          )}
          {focusSummary && !contextLoading && (
            <p className="text-xs text-muted">{focusSummary}</p>
          )}
          {profileSources.length > 0 && !contextLoading && (
            <p className="text-xs text-muted">Signal from: {profileSources.join(", ")}</p>
          )}

          <label className="block text-sm font-semibold">Search terms</label>
          <input value={terms} onChange={(e) => setTerms(e.target.value)} className="w-full rounded-xl border border-indigo-100 px-3 py-2 dark:border-indigo-500/30 dark:bg-slate-900/50" />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-semibold">Location</label>
              <input value={location} onChange={(e) => setLocation(e.target.value)} className="w-full rounded-xl border border-indigo-100 px-3 py-2 dark:border-indigo-500/30 dark:bg-slate-900/50" />
            </div>
            <div>
              <label className="block text-sm font-semibold">Results per term ({resultsPerTerm})</label>
              <input type="range" min={5} max={50} value={resultsPerTerm} onChange={(e) => setResultsPerTerm(Number(e.target.value))} className="w-full" />
            </div>
            <div>
              <label className="block text-sm font-semibold">Min match score ({minScore})</label>
              <input type="range" min={0} max={100} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="w-full" />
            </div>
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold">Sources</p>
            <div className="flex flex-wrap gap-3 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={includeIndeed} onChange={(e) => setIncludeIndeed(e.target.checked)} /> Indeed</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={includeLinkedin} onChange={(e) => setIncludeLinkedin(e.target.checked)} /> LinkedIn</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={includeHandshake} onChange={(e) => setIncludeHandshake(e.target.checked)} /> Handshake</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={includeTavily} onChange={(e) => setIncludeTavily(e.target.checked)} /> Tavily web</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={includeAts} onChange={(e) => setIncludeAts(e.target.checked)} /> ATS boards</label>
            </div>
            <p className="mt-1 text-xs text-slate-500">CareerShift is used in people discovery (pipeline), not scout ingest.</p>
          </div>

          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={requireOpt} onChange={(e) => setRequireOpt(e.target.checked)} /> Require OPT mention</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={runResumeAnalysis} onChange={(e) => setRunResumeAnalysis(e.target.checked)} /> Resume analysis</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} /> Dry run</label>
          </div>

          <button type="button" onClick={run} disabled={running} className="btn-primary w-full disabled:opacity-60">
            {running ? "Scouting… (watch Live Activity →)" : "Run Scout"}
          </button>
          {result && <p className="text-sm text-indigo-700 dark:text-indigo-300">{result}</p>}
        </div>
      </div>
      <ActivityFeed lines={activity} busy={running} busyLabel="Scout running…" />
    </div>
  );
}
