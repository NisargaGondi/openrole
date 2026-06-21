"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Copy, Link2, RefreshCw, Search, Sparkles, Trash2, X } from "lucide-react";
import { CompanyLogo } from "@/components/signal/CompanyLogo";
import { FormattedText } from "@/components/signal/FormattedText";
import { api } from "@/lib/api";
import type { Contact, NetworkCompany, OutreachDraft } from "@/lib/types";
import { cn } from "@/lib/utils";

type Filter = "all" | "linkedin" | "email" | "drafts" | "alumni" | "researched";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "linkedin", label: "Has LinkedIn" },
  { key: "email", label: "Has email" },
  { key: "drafts", label: "Has drafts" },
  { key: "researched", label: "Researched" },
  { key: "alumni", label: "CMU alumni" },
];

export default function NetworkPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof api.network>> | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const reload = useCallback(() => {
    api.network().then(setData).catch(() => {});
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const filteredCompanies = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.companies
      .map((co) => {
        let contacts = co.contacts;
        if (q) {
          contacts = contacts.filter(
            (c) =>
              `${c.full_name} ${c.title} ${c.email}`.toLowerCase().includes(q) ||
              co.company_name.toLowerCase().includes(q),
          );
        }
        if (filter === "linkedin") contacts = contacts.filter((c) => c.linkedin_url);
        if (filter === "email") contacts = contacts.filter((c) => c.email);
        if (filter === "alumni") contacts = contacts.filter((c) => c.is_cmu_alumni);
        if (filter === "researched") contacts = contacts.filter((c) => c.has_research);
        if (filter === "drafts") {
          const draftContactIds = new Set(co.drafts.map((d) => d.contact_id));
          contacts = contacts.filter((c) => draftContactIds.has(c.id));
        }
        return { ...co, contacts };
      })
      .filter((co) => {
        if (q && !co.company_name.toLowerCase().includes(q) && co.contacts.length === 0) return false;
        if (filter !== "all" && co.contacts.length === 0) return false;
        return true;
      });
  }, [data, query, filter]);

  const resultCount = filteredCompanies.reduce((n, c) => n + c.contacts.length, 0);

  if (!data) {
    return <p className="py-20 text-center text-slate-500">Loading network…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-extrabold signal-gradient-text">Network</h1>
        <p className="text-sm text-slate-500">
          {data.total_companies} companies · {data.total_roles} roles · {data.total_contacts} contacts ·{" "}
          {data.total_drafts} drafts
        </p>
      </div>

      <div className="glass sticky top-[4.5rem] z-40 space-y-3 rounded-2xl p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-indigo-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search contacts, titles, companies…"
            className="w-full rounded-xl border border-indigo-100 bg-white/90 py-2.5 pl-10 pr-10 text-sm dark:border-indigo-500/30 dark:bg-slate-900/50"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-semibold transition",
                filter === key
                  ? "bg-indigo-600 text-white"
                  : "bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950 dark:text-indigo-200",
              )}
            >
              {label}
            </button>
          ))}
          <span className="ml-auto text-xs text-slate-500">{resultCount} contacts</span>
        </div>
      </div>

      {filteredCompanies.length === 0 ? (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-slate-600">No contacts match. Try clearing filters or run people discovery.</p>
          <Link href="/" className="btn-primary mt-4 inline-block">
            Mission Control
          </Link>
        </div>
      ) : (
        filteredCompanies.map((co) => (
          <CompanyCard
            key={co.company_id}
            company={co}
            open={expanded === co.company_id}
            onToggle={() => setExpanded(expanded === co.company_id ? null : co.company_id)}
            onRefresh={reload}
          />
        ))
      )}
    </div>
  );
}

function CompanyCard({
  company,
  open,
  onToggle,
  onRefresh,
}: {
  company: NetworkCompany;
  open: boolean;
  onToggle: () => void;
  onRefresh: () => void;
}) {
  const draftsByContact = company.drafts.reduce<Record<string, OutreachDraft[]>>((acc, d) => {
    (acc[d.contact_id] ??= []).push(d);
    return acc;
  }, {});

  return (
    <div className="glass overflow-hidden rounded-2xl">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-4 text-left hover:bg-indigo-50/50 dark:hover:bg-indigo-950/20"
      >
        <CompanyLogo domain={company.company_domain} company={company.company_name} size={48} circular />
        <div className="min-w-0 flex-1">
          <p className="font-bold text-slate-900 dark:text-white">{company.company_name}</p>
          <p className="text-xs text-slate-500">
            {company.jobs.length} role{company.jobs.length === 1 ? "" : "s"} · {company.contacts.length} people ·{" "}
            {company.drafts.length} drafts
          </p>
        </div>
        <span className="text-xs font-semibold text-indigo-600">{open ? "Hide" : "Expand"}</span>
      </button>

      {open && (
        <div className="space-y-3 border-t border-indigo-100/80 p-4 dark:border-indigo-500/20">
          {company.jobs.length > 0 && (
            <div className="rounded-lg bg-indigo-50/50 px-3 py-2 dark:bg-indigo-950/30">
              <p className="text-[10px] font-bold uppercase tracking-wide text-indigo-600">Tracked roles</p>
              <ul className="mt-1 space-y-1 text-xs text-slate-600 dark:text-slate-300">
                {company.jobs.map((j) => (
                  <li key={j.id}>
                    {j.title}{" "}
                    <span className="text-slate-400">· {j.status.replace("_", " ")}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {company.contacts.length === 0 ? (
            <p className="text-sm text-slate-500">
              No people discovered yet — open a role in Mission Control and run people search.
            </p>
          ) : (
            company.contacts.map((c) => (
              <ContactRow
                key={c.id}
                contact={c}
                companyName={company.company_name}
                drafts={draftsByContact[c.id] ?? []}
                onRefresh={onRefresh}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function copyText(text: string) {
  void navigator.clipboard.writeText(text);
}

function ContactRow({
  contact,
  companyName,
  drafts,
  onRefresh,
}: {
  contact: Contact;
  companyName: string;
  drafts: OutreachDraft[];
  onRefresh: () => void;
}) {
  const [csLoading, setCsLoading] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);

  const onCopy = (key: string, text: string) => {
    copyText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const fetchCs = async () => {
    setCsLoading(true);
    try {
      await api.fetchCareerShiftEmail(contact.id, companyName);
      onRefresh();
    } catch (e) {
      alert(String(e));
    } finally {
      setCsLoading(false);
    }
  };

  const deleteContact = async () => {
    if (!confirm(`Delete ${contact.full_name} and all drafts?`)) return;
    await api.deleteContact(contact.id);
    onRefresh();
  };

  const deleteDraft = async (id: string) => {
    if (!confirm("Delete this draft?")) return;
    await api.deleteOutreach(id);
    onRefresh();
  };

  const emailDraft = drafts.find((d) => d.channel === "email");

  return (
    <div className="rounded-xl bg-white/80 p-4 ring-1 ring-indigo-100 dark:bg-slate-900/50">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-semibold text-slate-900 dark:text-white">{contact.full_name}</p>
          <p className="text-xs text-slate-500">{contact.title ?? "—"}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {contact.is_cmu_alumni && (
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-bold text-red-600">CMU</span>
            )}
            {contact.has_research && (
              <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[10px] font-bold text-violet-600">Researched</span>
            )}
            {contact.email_ai_generated && contact.email && (
              <span className="flex items-center gap-0.5 rounded-full bg-violet-100 px-2 py-0.5 text-[9px] font-bold text-violet-700">
                <Sparkles className="h-3 w-3" /> AI email
              </span>
            )}
          </div>
          {contact.email && (
            <p className="mt-1 text-xs text-indigo-600">{contact.email}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {contact.linkedin_url && (
            <a
              href={contact.linkedin_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 rounded-full bg-[#0A66C2] px-3 py-1.5 text-xs font-bold text-white"
            >
              <Link2 className="h-3.5 w-3.5" /> LinkedIn
            </a>
          )}
          {contact.email && (
            <button
              type="button"
              onClick={() => onCopy("addr", contact.email!)}
              className="flex items-center gap-1 rounded-full border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700"
            >
              <Copy className="h-3.5 w-3.5" /> {copied === "addr" ? "Copied!" : "Copy email"}
            </button>
          )}
          <button
            type="button"
            onClick={fetchCs}
            disabled={csLoading}
            className="flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 disabled:opacity-60"
            title="Fetch email from CareerShift"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", csLoading && "animate-spin")} />
            {csLoading ? "CS…" : "↻ CS"}
          </button>
          <button
            type="button"
            onClick={deleteContact}
            className="rounded-full border border-red-200 p-1.5 text-red-500 hover:bg-red-50"
            title="Delete contact"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {drafts.map((d) => {
        const copyKey = `draft-${d.id}`;
        const mailBody = d.subject ? `Subject: ${d.subject}\n\n${d.body}` : d.body;
        return (
          <div key={d.id} className="mt-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-bold uppercase text-indigo-600">{d.channel}</span>
              {d.ai_generated !== false && (
                <span className="flex items-center gap-0.5 rounded-full bg-violet-100 px-2 py-0.5 text-[9px] font-bold text-violet-700">
                  <Sparkles className="h-3 w-3" /> AI-generated
                </span>
              )}
              {d.channel === "email" && (
                <button
                  type="button"
                  onClick={() => onCopy(copyKey, mailBody)}
                  className="ml-auto flex items-center gap-1 rounded-full bg-indigo-600 px-2.5 py-1 text-[10px] font-bold text-white"
                >
                  <Copy className="h-3 w-3" />
                  {copied === copyKey ? "Copied!" : "Copy draft"}
                </button>
              )}
              <button
                type="button"
                onClick={() => deleteDraft(d.id)}
                className={cn("rounded p-1 text-red-400 hover:text-red-600", d.channel !== "email" && "ml-auto")}
                title="Delete draft"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            {d.subject && <p className="text-sm font-semibold text-heading">{d.subject}</p>}
            <div className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-white/60 p-3 dark:bg-slate-950/40">
              <FormattedText text={d.body} />
            </div>
          </div>
        );
      })}

      {!drafts.length && emailDraft === undefined && (
        <p className="mt-2 text-[10px] text-slate-400">No drafts yet for this contact.</p>
      )}
    </div>
  );
}
