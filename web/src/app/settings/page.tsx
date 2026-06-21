"use client";

import { useEffect, useState } from "react";
import {
  Cloud,
  Database,
  Flame,
  Globe,
  Loader2,
  Radar,
  Search,
  Sparkles,
  Users,
} from "lucide-react";
import { api } from "@/lib/api";
import type { SettingsResponse } from "@/lib/types";

const ICONS: Record<string, typeof Cloud> = {
  vertex: Cloud,
  fireworks: Flame,
  jobspy: Search,
  handshake: Users,
  careershift: Globe,
  apollo: Users,
  tavily: Radar,
  notion: Database,
};

function formatServiceLabel(key: string): string {
  if (key.startsWith("llm/")) return key.slice(4);
  return key;
}

const ROLE_LABELS: Record<string, string> = {
  ingestion: "Ingestion / parsing",
  research: "Research",
  writing: "Writing / drafts",
  fast: "Fast / extraction",
  default: "Default / eval",
};

function DaemonRow({
  label,
  mode,
  running,
  pid,
  extra,
  startCmd,
  stopCmd,
}: {
  label: string;
  mode: string;
  running: boolean;
  pid?: number | null;
  extra?: string;
  startCmd: string;
  stopCmd: string;
}) {
  return (
    <div className="mb-4 last:mb-0">
      <p className="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
        {label} · mode <span className="font-mono">{mode}</span>
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`rounded-full px-3 py-1 text-xs font-bold ${
            running
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
              : "bg-slate-100 text-slate-500 dark:bg-slate-800"
          }`}
        >
          {running ? "Running" : "Not running"}
        </span>
        {running && (
          <span className="text-xs text-slate-500">
            pid {pid ?? "?"}
            {extra ? ` · ${extra}` : ""}
          </span>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        Manual: <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{startCmd}</code>
        {" · "}
        <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{stopCmd}</code>
      </p>
    </div>
  );
}

export default function SettingsPage() {
  const [data, setData] = useState<SettingsResponse | null>(null);

  useEffect(() => {
    api.settings().then(setData).catch(() => {});
  }, []);

  if (!data) {
    return <p className="py-20 text-center text-slate-500">Loading settings…</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-extrabold signal-gradient-text">Settings</h1>
        <p className="text-sm text-slate-500">
          Integrations · LLM: {data.llm_provider} · env: {data.app_env}
        </p>
      </div>

      <div className="glass rounded-2xl p-5">
        <h2 className="mb-1 text-sm font-bold text-slate-800 dark:text-white">Active LLM models</h2>
        <p className="mb-4 text-xs text-slate-500">
          Provider: <span className="font-semibold">{data.llm_models.provider}</span> — tracked per model in usage below
        </p>
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {(["ingestion", "research", "writing", "fast", "default"] as const).map((role) => (
            <div key={role} className="rounded-xl bg-indigo-50/60 px-3 py-2 dark:bg-indigo-950/30">
              <dt className="text-[10px] font-bold uppercase tracking-wide text-slate-500">{ROLE_LABELS[role]}</dt>
              <dd className="font-mono text-sm font-semibold text-indigo-700 dark:text-indigo-300">
                {data.llm_models[role]}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      {(data.careershift_daemon || data.handshake_daemon) && (
        <div className="glass rounded-2xl p-5">
          <h2 className="mb-1 text-sm font-bold text-slate-800 dark:text-white">Browser daemons</h2>
          <p className="mb-3 text-xs text-slate-500">
            {data.browser_daemon_on_demand
              ? "On-demand: scout and pipeline start/stop daemons automatically for Handshake (scout) and CareerShift (people search)."
              : "Manual mode: start daemons yourself before scout or people search."}
          </p>
          {data.careershift_daemon && (
            <DaemonRow
              label="CareerShift"
              mode={data.careershift_daemon.mode}
              running={data.careershift_daemon.running}
              pid={data.careershift_daemon.pid}
              extra={
                data.careershift_daemon.running
                  ? [
                      data.careershift_daemon.searches != null && `${data.careershift_daemon.searches} searches`,
                      data.careershift_daemon.idle_s != null && `idle ${Math.round(data.careershift_daemon.idle_s)}s`,
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : undefined
              }
              startCmd="bash scripts/run_careershift_daemon.sh"
              stopCmd="bash scripts/careershift_daemon_ctl.sh stop"
            />
          )}
          {data.handshake_daemon && (
            <DaemonRow
              label="Handshake"
              mode={data.handshake_daemon.mode}
              running={data.handshake_daemon.running}
              pid={data.handshake_daemon.pid}
              extra={
                data.handshake_daemon.running
                  ? [
                      data.handshake_daemon.calls != null && `${data.handshake_daemon.calls} calls`,
                      data.handshake_daemon.idle_s != null && `idle ${Math.round(data.handshake_daemon.idle_s)}s`,
                    ]
                      .filter(Boolean)
                      .join(" · ")
                  : undefined
              }
              startCmd="bash scripts/run_handshake_daemon.sh"
              stopCmd="bash scripts/handshake_daemon_ctl.sh stop"
            />
          )}
        </div>
      )}

      <div>
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Connections</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.integrations.map((item) => {
            const Icon = ICONS[item.key] ?? Sparkles;
            return (
              <div
                key={item.key}
                className={`glass rounded-2xl p-5 ${item.ok ? "ring-1 ring-emerald-200 dark:ring-emerald-800" : ""}`}
              >
                <Icon className={`mb-2 h-7 w-7 ${item.ok ? "text-indigo-600" : "text-slate-300"}`} />
                <p className="font-bold text-slate-800 dark:text-white">{item.name}</p>
                <p className={`text-sm ${item.ok ? "text-emerald-600" : "text-slate-400"}`}>
                  {item.ok ? "Connected" : "Not configured"}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      <div className="glass rounded-2xl p-5">
        <h2 className="mb-1 text-sm font-bold text-slate-800 dark:text-white">API usage & estimated cost</h2>
        <p className="mb-4 text-xs text-slate-500">
          Persisted across runs · {data.usage.event_count ?? 0} logged events — rough estimates only
        </p>
        <div className="mb-4 flex items-baseline gap-2">
          <span className="text-3xl font-extrabold text-indigo-700">${data.usage.total_est_cost_usd.toFixed(2)}</span>
          <span className="text-sm text-slate-500">total tracked</span>
        </div>
        <table className="mb-6 w-full text-sm">
          <thead>
            <tr className="border-b border-indigo-100 text-left text-xs uppercase text-slate-500 dark:border-indigo-500/30">
              <th className="pb-2">Service</th>
              <th className="pb-2">Calls</th>
              <th className="pb-2">Rate</th>
              <th className="pb-2">Cost</th>
            </tr>
          </thead>
          <tbody>
            {data.usage.services.map((s) => (
              <tr key={s.key} className="border-b border-indigo-50 dark:border-indigo-900/30">
                <td className="py-2 font-medium">{formatServiceLabel(s.key)}</td>
                <td className="py-2">{s.calls}</td>
                <td className="py-2 text-slate-500">${s.rate_usd.toFixed(3)}/call</td>
                <td className="py-2 font-semibold">${s.est_cost_usd.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {(data.usage.by_job?.length ?? 0) > 0 && (
          <>
            <h3 className="mb-2 text-xs font-bold uppercase text-slate-500">Cost by job / pipeline run</h3>
            <div className="mb-6 space-y-2">
              {data.usage.by_job!.map((j) => (
                <div key={j.job_id} className="rounded-xl bg-indigo-50/50 px-3 py-2 dark:bg-indigo-950/30">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-800 dark:text-white">
                      {j.job_title ?? j.company ?? j.job_id.slice(0, 8)}
                    </p>
                    <p className="text-xs font-bold text-indigo-600">${j.total_cost_usd.toFixed(3)} · {j.total_calls} calls</p>
                  </div>
                  <p className="text-[10px] text-slate-500">
                    {Object.entries(j.steps).map(([k, v]) => `${k}: $${v.toFixed(3)}`).join(" · ")}
                  </p>
                </div>
              ))}
            </div>
          </>
        )}

        {(data.usage.recent?.length ?? 0) > 0 && (
          <>
            <h3 className="mb-2 text-xs font-bold uppercase text-slate-500">Recent API events</h3>
            <ul className="max-h-48 space-y-1 overflow-y-auto text-xs text-slate-600">
              {data.usage.recent!.slice(0, 15).map((e, i) => (
                <li key={i} className="border-b border-indigo-50 py-1 dark:border-indigo-900/30">
                  <span className="font-semibold text-indigo-600">{formatServiceLabel(e.service)}</span>
                  {e.company && ` · ${e.company}`}
                  {e.pipeline_step && ` · ${e.pipeline_step}`}
                  {` · $${e.est_cost_usd.toFixed(4)}`}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="glass rounded-2xl p-5">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">API tests</h2>
        <p className="mb-4 text-xs text-slate-500">Quick probes — results also appear in Live Activity.</p>
        <div className="flex flex-wrap gap-2">
          {[
            { id: "jobspy_indeed", label: "Test Indeed (JobSpy)" },
            { id: "jobspy_linkedin", label: "Test LinkedIn (JobSpy)" },
            { id: "apollo", label: "Test Apollo" },
            { id: "careershift", label: "Test CareerShift" },
          ].map(({ id, label }) => (
            <TestButton key={id} service={id} label={label} />
          ))}
        </div>
      </div>

      <div className="glass rounded-2xl p-5">
        <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500">Browser login</h2>
        <p className="mb-4 text-xs text-slate-500">
          Opens a local Chrome window on your machine. Cookies stay in ~/.openrole and ~/.handshake-mcp.
        </p>
        <div className="flex flex-wrap gap-2">
          <LoginButton provider="handshake" label="Handshake login" />
          <LoginButton provider="careershift" label="CareerShift login" />
          <LoginButton provider="handshake" label="Handshake (clear profile)" clear />
          <LoginButton provider="careershift" label="CareerShift (clear profile)" clear />
        </div>
      </div>

      <p className="text-sm text-slate-500">
        Configure keys in <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">.env</code> at the repo root. Restart the API after changes.
      </p>
    </div>
  );
}

function TestButton({ service, label }: { service: string; label: string }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      const r = await api.testIntegration(service);
      setResult(r.ok ? `OK — ${JSON.stringify(r).slice(0, 120)}…` : String(r.error ?? "Failed"));
    } catch (e) {
      setResult(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="rounded-xl border border-indigo-200 bg-white px-3 py-2 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-60 dark:border-indigo-500/30 dark:bg-slate-900/50"
      >
        {loading ? <Loader2 className="inline h-3.5 w-3.5 animate-spin" /> : null} {label}
      </button>
      {result && <p className="max-w-xs text-[10px] text-slate-500">{result}</p>}
    </div>
  );
}

function LoginButton({
  provider,
  label,
  clear = false,
}: {
  provider: "careershift" | "handshake";
  label: string;
  clear?: boolean;
}) {
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await api.integrationLogin(provider, clear);
      alert(r.ok ? r.message : `Failed: ${r.message}`);
    } catch (e) {
      alert(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={run}
      disabled={loading}
      className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-bold text-white hover:bg-indigo-700 disabled:opacity-60"
    >
      {loading ? "Opening browser…" : label}
    </button>
  );
}
