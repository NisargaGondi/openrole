"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ActivityFeed } from "@/components/signal/ActivityFeed";
import { api } from "@/lib/api";
import type { ActivityLine } from "@/lib/types";

export default function ActivityPage() {
  const [lines, setLines] = useState<ActivityLine[]>([]);

  useEffect(() => {
    api.activity(300).then((a) => setLines(a.lines));
    const t = setInterval(() => api.activity(300).then((a) => setLines(a.lines)), 4000);
    return () => clearInterval(t);
  }, []);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold signal-gradient-text">Live Activity</h1>
          <p className="text-sm text-slate-500">Full event log — scout, pipeline, outreach</p>
        </div>
        <Link href="/" className="text-sm font-semibold text-indigo-600 hover:underline">
          ← Mission Control
        </Link>
      </div>
      <ActivityFeed
        lines={lines}
        onClear={() => api.clearActivity().then(() => setLines([]))}
      />
    </div>
  );
}
