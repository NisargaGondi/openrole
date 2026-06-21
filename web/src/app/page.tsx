"use client";

import { Suspense } from "react";
import { MissionControl } from "@/components/signal/MissionControl";

export default function HomePage() {
  return (
    <Suspense fallback={<p className="py-20 text-center text-slate-500">Loading…</p>}>
      <MissionControl />
    </Suspense>
  );
}
