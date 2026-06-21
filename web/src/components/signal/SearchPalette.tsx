"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Building2, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { saveSession } from "@/lib/session";
import type { Job } from "@/lib/types";
import { VisaTags } from "@/components/signal/VisaTags";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function SearchPalette({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      api.jobs().then((r) => setJobs(r.jobs)).catch(() => {});
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (open) onClose();
      }
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return jobs.slice(0, 8);
    return jobs.filter((j) => `${j.title} ${j.company} ${j.locations?.join(" ")}`.toLowerCase().includes(q)).slice(0, 12);
  }, [jobs, query]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center bg-slate-900/40 p-4 pt-[12vh] backdrop-blur-sm" onClick={onClose}>
      <div
        className="glass-float w-full max-w-xl overflow-hidden rounded-2xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-indigo-100/80 px-4 py-3 dark:border-indigo-500/20">
          <Search className="h-5 w-5 text-indigo-500" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search roles, companies, locations…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400"
          />
          <kbd className="hidden rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 sm:inline">esc</kbd>
          <button type="button" onClick={onClose} className="rounded-full p-1 text-slate-400 hover:bg-slate-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="max-h-[360px] overflow-y-auto p-2">
          {results.length === 0 ? (
            <li className="px-3 py-8 text-center text-sm text-slate-500">No roles found</li>
          ) : (
            results.map((j) => (
              <li key={j.id}>
                <Link
                  href={`/?job=${j.id}&step=research`}
                  onClick={() => {
                    saveSession({ jobId: j.id, step: "research" });
                    onClose();
                  }}
                  className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition hover:bg-indigo-50 dark:hover:bg-indigo-950/50"
                >
                  <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-100 text-indigo-600 dark:bg-indigo-900">
                    <Building2 className="h-4 w-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{j.title}</p>
                    <p className="truncate text-xs text-slate-500">{j.company} · {j.locations?.[0] ?? "Remote"}</p>
                    <VisaTags visa={j.visa} className="mt-1" />
                  </div>
                </Link>
              </li>
            ))
          )}
        </ul>
        <div className="border-t border-indigo-100/80 px-4 py-2 text-[10px] text-slate-400 dark:border-indigo-500/20">
          Tip: ⌘K to search · Scout new roles from the Search page
        </div>
      </div>
    </div>
  );
}
