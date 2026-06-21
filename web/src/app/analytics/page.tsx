"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  discovered: "#6366f1",
  reviewing: "#8b5cf6",
  applied: "#3b82f6",
  assessment: "#06b6d4",
  interviewing: "#f97316",
  waitlist: "#eab308",
  offer: "#22c55e",
  rejected: "#ef4444",
  archived: "#94a3b8",
};

const STATUS_LABELS: Record<string, string> = {
  discovered: "Discovered",
  reviewing: "Researching",
  applied: "Applied",
  assessment: "Assessment",
  interviewing: "Interview",
  waitlist: "Waitlist",
  offer: "Accepted",
  rejected: "Rejected",
  archived: "Archived",
};

export default function AnalyticsPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [scoutJobs, setScoutJobs] = useState(0);

  useEffect(() => {
    api.dashboard().then((d) => {
      setStats(d.stats);
      setScoutJobs(d.stats.scout_jobs);
    });
  }, []);

  const funnelData = useMemo(() => {
    if (!stats) return [];
    const order = ["discovered", "reviewing", "applied", "assessment", "interviewing", "offer", "rejected"];
    return order
      .map((k) => ({
        stage: STATUS_LABELS[k] ?? k,
        count: stats.jobs_by_status[k] ?? 0,
        fill: STATUS_COLORS[k] ?? "#6366f1",
      }))
      .filter((d) => d.count > 0 || ["discovered", "applied", "interviewing"].includes(d.stage.toLowerCase()));
  }, [stats]);

  const pieData = useMemo(() => {
    if (!stats) return [];
    return Object.entries(stats.jobs_by_status)
      .filter(([, v]) => v > 0)
      .map(([k, v]) => ({
        name: STATUS_LABELS[k] ?? k,
        value: v,
        fill: STATUS_COLORS[k] ?? "#6366f1",
      }));
  }, [stats]);

  if (!stats) {
    return <p className="py-20 text-center text-slate-500">Loading analytics…</p>;
  }

  const applied = stats.jobs_by_status.applied ?? 0;
  const interviewing = stats.jobs_by_status.interviewing ?? 0;
  const rejected = stats.jobs_by_status.rejected ?? 0;
  const offers = stats.jobs_by_status.offer ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold signal-gradient-text">Analytics</h1>
        <p className="text-sm text-slate-500">Pipeline funnel · status breakdown · scout metrics</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {[
          { label: "Total roles", value: stats.total_jobs },
          { label: "Scouted", value: scoutJobs },
          { label: "Applied", value: applied },
          { label: "Interviews", value: interviewing },
          { label: "Offers", value: offers },
          { label: "Rejected", value: rejected },
        ].map(({ label, value }) => (
          <div key={label} className="glass rounded-2xl p-4 text-center">
            <p className="text-2xl font-extrabold text-indigo-700 dark:text-indigo-300">{value}</p>
            <p className="text-xs font-semibold text-slate-500">{label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="glass rounded-2xl p-5">
          <h3 className="mb-1 text-sm font-bold text-slate-800 dark:text-white">Application funnel</h3>
          <p className="mb-4 text-xs text-slate-500">Bar chart — best for stage counts in order</p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnelData} layout="vertical" margin={{ left: 8, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="stage" width={90} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" radius={[0, 6, 6, 0]}>
                  {funnelData.map((e) => (
                    <Cell key={e.stage} fill={e.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass rounded-2xl p-5">
          <h3 className="mb-1 text-sm font-bold text-slate-800 dark:text-white">Status distribution</h3>
          <p className="mb-4 text-xs text-slate-500">Donut chart — best for proportions of whole</p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {pieData.map((e) => (
                    <Cell key={e.name} fill={e.fill} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="glass rounded-2xl p-5">
        <h3 className="mb-4 text-sm font-bold">Outreach & network</h3>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <p className="text-xl font-bold text-indigo-600">{stats.pending_outreach}</p>
            <p className="text-xs text-slate-500">Drafts pending review</p>
          </div>
          <div>
            <p className="text-xl font-bold text-indigo-600">{stats.total_contacts}</p>
            <p className="text-xs text-slate-500">Total contacts</p>
          </div>
          <div>
            <p className="text-xl font-bold text-indigo-600">{stats.companies_total}</p>
            <p className="text-xs text-slate-500">Companies tracked</p>
          </div>
        </div>
      </div>
    </div>
  );
}
