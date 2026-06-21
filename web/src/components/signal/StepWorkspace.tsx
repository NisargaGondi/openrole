"use client";

import { useEffect, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  Mail,
  Link2,
  User,
  FlaskConical,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import type { Contact, JobDetail, OutreachDraft } from "@/lib/types";
import { pipelineOptsForStep, streamPipeline } from "@/lib/pipelineStream";
import { usePipelineRun } from "@/components/signal/PipelineRunProvider";
import { ResumeAnalysisList } from "@/components/signal/ResumeScoreBadge";
import { api } from "@/lib/api";
import { FormattedText } from "@/components/signal/FormattedText";

type ResumeOption = { label: string; is_default?: boolean };

type Props = {
  step: string;
  detail: JobDetail;
  onRefresh: () => void;
  onLog: (msg: string) => void;
  onStepDone: (nextStep: string) => void;
};

export function StepWorkspace({ step, detail, onRefresh, onLog, onStepDone }: Props) {
  const { isRunning, cancelling, startRun, finishRun, requestCancel } = usePipelineRun();
  const running = isRunning(detail.job.id);
  const [resumeOptions, setResumeOptions] = useState<ResumeOption[]>([]);
  const [selectedResumes, setSelectedResumes] = useState<string[]>([]);
  const [selectAllResumes, setSelectAllResumes] = useState(false);

  useEffect(() => {
    if (step !== "apply") return;
    api.scoutResumes().then((r) => {
      setResumeOptions(r.resumes);
      const def = r.resumes.find((x) => x.is_default) ?? r.resumes[0];
      if (def) setSelectedResumes([def.label]);
    });
  }, [step]);

  const toggleResume = (label: string) => {
    setSelectAllResumes(false);
    setSelectedResumes((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label],
    );
  };

  const toggleAllResumes = () => {
    const next = !selectAllResumes;
    setSelectAllResumes(next);
    if (next) {
      setSelectedResumes(resumeOptions.map((r) => r.label));
    } else {
      const def = resumeOptions.find((x) => x.is_default) ?? resumeOptions[0];
      setSelectedResumes(def ? [def.label] : []);
    }
  };

  const runStep = () => {
    if (running) return;
    if (step === "apply" && !selectAllResumes && !selectedResumes.length) {
      onLog("Select at least one resume to analyze.");
      return;
    }
    startRun({
      jobId: detail.job.id,
      step,
      company: detail.job.company ?? undefined,
    });
    onLog(`Starting ${step}…`);
    const baseOpts = pipelineOptsForStep(step);
    const resumeOpts =
      step === "apply"
        ? selectAllResumes || selectedResumes.length === resumeOptions.length
          ? { resume_labels: ["__all__"] as string[] }
          : { resume_labels: selectedResumes }
        : {};
    const opts = { ...baseOpts, ...resumeOpts };
    const close = streamPipeline(detail.job.id, opts, (ev) => {
      if (ev.type === "log" || ev.type === "start") onLog(ev.message);
      if (ev.type === "cancelling") onLog(ev.message);
      if (ev.type === "done") {
        onLog(ev.message);
        finishRun();
        onRefresh();
        const next =
          step === "people" ? "research" : step === "research" ? "outreach" : step === "outreach" ? "apply" : step;
        if (step !== "apply") onStepDone(next);
        close();
      }
      if (ev.type === "cancelled") {
        onLog(ev.message);
        finishRun();
        onRefresh();
        close();
      }
      if (ev.type === "error") {
        onLog(ev.message);
        finishRun();
        close();
      }
    });
  };

  const cancelStep = () => {
    requestCancel(detail.job.id).then((ok) => {
      if (ok) onLog("Cancel requested — stopping after current step…");
    });
  };

  return (
    <div className="glass mt-4 rounded-2xl p-5">
      <StepHeader step={step} detail={detail} />
      {step === "people" && (
        <PeoplePanel contacts={detail.contacts} onRefresh={onRefresh} onLog={onLog} />
      )}
      {step === "research" && (
        <ResearchPanel contacts={detail.contacts} onRefresh={onRefresh} onLog={onLog} />
      )}
      {step === "outreach" && (
        <OutreachPanel drafts={detail.drafts} onRefresh={onRefresh} onLog={onLog} />
      )}
      {step === "apply" && (
        <ApplyPanel
          job={detail.job}
          resumeOptions={resumeOptions}
          selectedResumes={selectedResumes}
          selectAllResumes={selectAllResumes}
          onToggleResume={toggleResume}
          onToggleAll={toggleAllResumes}
        />
      )}
      {step === "role" && <RolePanel job={detail.job} />}
      {step === "qualify" && <p className="text-sm text-slate-600">Role qualified via scout or manual ingest.</p>}

      {["people", "research", "outreach", "apply"].includes(step) && (
        <div className="mt-5 flex flex-wrap gap-2">
          <button type="button" onClick={runStep} disabled={running} className="btn-primary disabled:opacity-60">
            {running ? "Running…" : runLabel(step)}
          </button>
          {running && (
            <button
              type="button"
              onClick={cancelStep}
              disabled={cancelling}
              className="flex items-center gap-1.5 rounded-full border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-100 disabled:opacity-70"
            >
              <XCircle className="h-4 w-4" /> {cancelling ? "Cancelling…" : "Cancel pipeline"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function runLabel(step: string) {
  const m: Record<string, string> = {
    people: "Find people",
    research: "Research all contacts",
    outreach: "Draft email + LinkedIn",
    apply: "Run resume analysis",
  };
  return m[step] ?? "Run";
}

function StepHeader({ step, detail }: { step: string; detail: JobDetail }) {
  const titles: Record<string, string> = {
    role: "Role overview",
    people: "People discovery",
    research: "Research & personalize",
    outreach: "Outreach drafts",
    apply: "Apply prep",
  };
  const researched = detail.contacts.filter((c) => c.has_research).length;
  return (
    <div className="mb-4 border-b border-indigo-100/80 pb-3">
      <h3 className="text-base font-bold text-slate-900">{titles[step] ?? step}</h3>
      <p className="text-xs text-slate-500">
        Full drafts & contacts live in{" "}
        <a href="/network" className="font-semibold text-indigo-600 hover:underline">
          Network
        </a>
        . Summary below — expand for details.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <StatPill label="Contacts" value={detail.contacts.length} />
        <StatPill label="Researched" value={`${researched}/${detail.contacts.length || 0}`} />
        <StatPill label="Drafts" value={detail.draft_count} />
      </div>
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: string | number }) {
  return (
    <span className="rounded-full bg-indigo-50 px-2.5 py-1 text-[10px] font-bold text-indigo-700">
      {label}: {value}
    </span>
  );
}

function ProgressRow({ done, total, label }: { done: number; total: number; label: string }) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="rounded-xl bg-white/80 p-4 ring-1 ring-indigo-100">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="font-semibold text-slate-800">{label}</span>
        <span className="text-xs font-bold text-indigo-600">
          {done}/{total || 0} · {pct}%
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-indigo-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {done > 0 && (
        <p className="mt-2 flex items-center gap-1 text-xs text-emerald-600">
          <CheckCircle2 className="h-3.5 w-3.5" /> Ready — open Network for full drafts
        </p>
      )}
    </div>
  );
}

function PeoplePanel({
  contacts,
  onRefresh,
  onLog,
}: {
  contacts: Contact[];
  onRefresh: () => void;
  onLog: (m: string) => void;
}) {
  if (!contacts.length) {
    return (
      <p className="text-sm text-slate-600">
        No contacts yet. Click <strong>Find people</strong> to discover engineers, managers, and CMU alumni.
      </p>
    );
  }
  const withEmail = contacts.filter((c) => c.email).length;
  const withLinkedIn = contacts.filter((c) => c.linkedin_url).length;

  return (
    <div className="space-y-3">
      <ProgressRow done={contacts.length} total={contacts.length} label="Contacts discovered" />
      <div className="flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
        <span>{withEmail} with email</span>
        <span>·</span>
        <span>{withLinkedIn} with LinkedIn</span>
      </div>
      <details className="group rounded-xl bg-white/60 ring-1 ring-indigo-100">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-indigo-700">
          View contact list
          <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
        </summary>
        <ul className="space-y-2 border-t border-indigo-50 px-4 pb-4 pt-2">
          {contacts.map((c) => (
            <li key={c.id} className="flex items-start gap-2 rounded-lg bg-slate-50/80 p-2 text-sm">
              <User className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-500" />
              <div className="min-w-0 flex-1">
                <p className="font-medium text-slate-900">{c.full_name}</p>
                <p className="truncate text-xs text-slate-500">{c.title ?? "—"}</p>
              </div>
              <DeleteContactButton contactId={c.id} name={c.full_name} onDone={onRefresh} onLog={onLog} />
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function ResearchPanel({
  contacts,
  onRefresh,
  onLog,
}: {
  contacts: Contact[];
  onRefresh: () => void;
  onLog: (m: string) => void;
}) {
  const researched = contacts.filter((c) => c.has_research);
  if (!contacts.length) {
    return (
      <p className="text-sm text-slate-600">
        Run <strong>People</strong> first, then <strong>Research all contacts</strong>.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <ProgressRow done={researched.length} total={contacts.length} label="Research briefs" />
      {researched.length > 0 && (
        <details className="group rounded-xl bg-white/60 ring-1 ring-indigo-100">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-indigo-700">
            View briefs ({researched.length})
            <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
          </summary>
          <ul className="space-y-2 border-t border-indigo-50 px-4 pb-4 pt-2">
            {researched.map((c) => (
              <li key={c.id} className="rounded-lg bg-slate-50/80 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <FlaskConical className="h-4 w-4 text-violet-500" />
                    <span className="text-sm font-semibold">{c.full_name}</span>
                  </div>
                  <DeleteContactButton contactId={c.id} name={c.full_name} onDone={onRefresh} onLog={onLog} />
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-slate-600">{c.research_hook ?? "Brief saved"}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function OutreachPanel({
  drafts,
  onRefresh,
  onLog,
}: {
  drafts: OutreachDraft[];
  onRefresh: () => void;
  onLog: (m: string) => void;
}) {
  if (!drafts.length) {
    return (
      <p className="text-sm text-slate-600">
        Run <strong>Draft email + LinkedIn</strong> after research. Full text in Network tab.
      </p>
    );
  }
  const emails = drafts.filter((d) => d.channel === "email").length;
  const linkedin = drafts.filter((d) => d.channel === "linkedin").length;

  return (
    <div className="space-y-3">
      <ProgressRow done={drafts.length} total={drafts.length} label="Outreach drafts generated" />
      <div className="flex flex-wrap gap-2 text-[10px] font-semibold text-slate-500">
        <span>{emails} email</span>
        <span>·</span>
        <span>{linkedin} LinkedIn</span>
      </div>
      <details className="group rounded-xl bg-white/60 ring-1 ring-indigo-100">
        <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-indigo-700">
          Preview drafts
          <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
        </summary>
        <div className="space-y-3 border-t border-indigo-50 px-4 pb-4 pt-2">
          {drafts.map((d) => (
            <div key={d.id} className="rounded-lg bg-slate-50/80 p-3">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                {d.channel === "linkedin" ? (
                  <Link2 className="h-3.5 w-3.5 text-indigo-600" />
                ) : (
                  <Mail className="h-3.5 w-3.5 text-indigo-600" />
                )}
                <span className="text-[10px] font-bold uppercase text-indigo-600">{d.channel}</span>
                {d.ai_generated !== false && (
                  <span className="flex items-center gap-0.5 rounded-full bg-violet-100 px-2 py-0.5 text-[9px] font-bold text-violet-700">
                    <Sparkles className="h-3 w-3" /> AI
                  </span>
                )}
                <DeleteDraftButton draftId={d.id} onDone={onRefresh} onLog={onLog} />
              </div>
              {d.subject && <p className="text-xs font-medium text-slate-800">{d.subject}</p>}
              <p className="mt-1 line-clamp-3 text-xs text-slate-600">{d.body}</p>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function DeleteContactButton({
  contactId,
  name,
  onDone,
  onLog,
}: {
  contactId: string;
  name: string;
  onDone: () => void;
  onLog: (m: string) => void;
}) {
  const del = async () => {
    if (!confirm(`Delete ${name} and their drafts?`)) return;
    try {
      await api.deleteContact(contactId);
      onLog(`Deleted contact ${name}`);
      onDone();
    } catch (e) {
      onLog(String(e));
    }
  };
  return (
    <button type="button" onClick={del} className="rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600" title="Delete">
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  );
}

function DeleteDraftButton({
  draftId,
  onDone,
  onLog,
}: {
  draftId: string;
  onDone: () => void;
  onLog: (m: string) => void;
}) {
  const del = async () => {
    if (!confirm("Delete this draft?")) return;
    try {
      await api.deleteOutreach(draftId);
      onLog("Draft deleted");
      onDone();
    } catch (e) {
      onLog(String(e));
    }
  };
  return (
    <button type="button" onClick={del} className="ml-auto rounded p-1 text-red-400 hover:bg-red-50 hover:text-red-600" title="Delete draft">
      <Trash2 className="h-3.5 w-3.5" />
    </button>
  );
}

function ApplyPanel({
  job,
  resumeOptions,
  selectedResumes,
  selectAllResumes,
  onToggleResume,
  onToggleAll,
}: {
  job: JobDetail["job"];
  resumeOptions: ResumeOption[];
  selectedResumes: string[];
  selectAllResumes: boolean;
  onToggleResume: (label: string) => void;
  onToggleAll: () => void;
}) {
  const hasReports = Boolean(
    job.resume_analyses && Object.keys(job.resume_analyses).length,
  ) || Boolean(job.resume_report);

  return (
    <div className="space-y-4">
      <div className="rounded-xl bg-white/80 p-4 ring-1 ring-indigo-100 dark:bg-slate-900/40 dark:ring-indigo-500/20">
        <p className="text-sm font-semibold text-heading">Resumes to analyze</p>
        <p className="mt-1 text-xs text-muted">
          Pick one, several, or all variants from your `.env` resume paths — not locked to the default.
        </p>
        {!resumeOptions.length ? (
          <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">
            No resumes configured. Set <code className="text-xs">CANDIDATE_RESUME_PATHS</code> in Settings.
          </p>
        ) : (
          <div className="mt-3 space-y-2">
            <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-indigo-50/80 px-3 py-2 text-sm font-semibold text-indigo-800 dark:bg-indigo-950/40 dark:text-indigo-200">
              <input
                type="checkbox"
                checked={selectAllResumes}
                onChange={onToggleAll}
                className="rounded border-indigo-300"
              />
              All resumes ({resumeOptions.length})
            </label>
            {resumeOptions.map((r) => (
              <label
                key={r.label}
                className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-body hover:bg-slate-50 dark:hover:bg-slate-800/50"
              >
                <input
                  type="checkbox"
                  checked={selectAllResumes || selectedResumes.includes(r.label)}
                  disabled={selectAllResumes}
                  onChange={() => onToggleResume(r.label)}
                  className="rounded border-indigo-300"
                />
                <span>{r.label}</span>
                {r.is_default && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    default
                  </span>
                )}
              </label>
            ))}
          </div>
        )}
      </div>

      {hasReports ? (
        <div className="space-y-3">
          <ProgressRow done={1} total={1} label="Resume analysis" />
          <ResumeAnalysisList job={job} />
        </div>
      ) : (
        <p className="text-sm text-muted">
          Select resume(s) above, then click <strong>Run resume analysis</strong>.
        </p>
      )}
    </div>
  );
}

function RolePanel({ job }: { job: JobDetail["job"] }) {
  return (
    <details className="group rounded-xl bg-white/60 ring-1 ring-indigo-100 dark:bg-slate-900/40 dark:ring-indigo-500/20">
      <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-semibold text-indigo-700 dark:text-indigo-300">
        Role description
        <ChevronDown className="h-4 w-4 transition group-open:rotate-180" />
      </summary>
      <div className="max-h-80 overflow-y-auto border-t border-indigo-50 px-4 pb-4 pt-2 dark:border-indigo-500/20">
        {job.description ? (
          <FormattedText text={job.description} />
        ) : (
          <p className="text-sm text-muted">No description stored.</p>
        )}
      </div>
    </details>
  );
}
