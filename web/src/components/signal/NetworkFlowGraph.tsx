"use client";

import {
  Background,
  BaseEdge,
  Controls,
  EdgeProps,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  getSmoothStepPath,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { motion } from "framer-motion";
import { BarChart3, Lightbulb, User, Users } from "lucide-react";
import { useMemo } from "react";
import { CompanyLogo } from "@/components/signal/CompanyLogo";
import type { Contact, Job, PipelineState } from "@/lib/types";

type Props = {
  job: Job;
  contacts: Contact[];
  pipeline: PipelineState;
  activeStep?: string;
  cmuAlumniCount?: number;
  researchedCount?: number;
};

function YouNode() {
  return (
    <div className="relative flex h-[80px] w-[80px] items-center justify-center">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="pointer-events-none absolute inset-0 rounded-full border-2 border-indigo-400/50"
          initial={{ scale: 0.5, opacity: 0.8 }}
          animate={{ scale: 2.4, opacity: 0 }}
          transition={{ duration: 2.8, repeat: Infinity, delay: i * 0.9, ease: "easeOut" }}
        />
      ))}
      <div className="relative z-10 flex h-14 w-14 flex-col items-center justify-center rounded-full border-2 border-indigo-500 bg-gradient-to-br from-indigo-50 to-white shadow-lg shadow-indigo-500/25 dark:from-indigo-950 dark:to-slate-900">
        <Handle type="source" position={Position.Top} className="!bg-indigo-500 !border-white" />
        <User className="h-5 w-5 text-indigo-600" />
      </div>
      <p className="absolute -bottom-4 text-[10px] font-bold text-indigo-900 dark:text-indigo-100">You</p>
    </div>
  );
}

function CompanyNode({ data }: { data: { label: string; domain?: string | null } }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <Handle type="target" position={Position.Bottom} className="!bg-indigo-500" />
      <Handle type="source" position={Position.Top} className="!bg-indigo-500" />
      <CompanyLogo domain={data.domain} company={data.label} size={40} className="!rounded-full" circular />
      <p className="max-w-[80px] truncate text-[10px] font-bold text-slate-800 dark:text-slate-100">{data.label}</p>
    </div>
  );
}

function ContactNode({ data }: { data: { name: string; title: string; researched: boolean; outreach?: boolean } }) {
  return (
    <div
      className={`relative min-w-[76px] rounded-2xl border-2 px-2 py-1.5 text-center shadow-sm transition ${
        data.outreach
          ? "border-orange-400 bg-orange-50 shadow-orange-200/50 dark:bg-orange-950/40"
          : data.researched
            ? "border-violet-400 bg-violet-50 dark:bg-violet-950/40"
            : "border-indigo-200 bg-white dark:bg-slate-900"
      }`}
    >
      {data.outreach && (
        <motion.span
          className="absolute -inset-1 rounded-2xl border border-orange-300/60"
          animate={{ opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        />
      )}
      <Handle type="target" position={Position.Bottom} className="!bg-indigo-400" />
      <p className="text-[10px] font-bold text-slate-800 dark:text-slate-100">{data.name}</p>
      <p className="text-[8px] leading-tight text-slate-500">{data.title}</p>
    </div>
  );
}

function InsightNode({ data }: { data: { label: string; icon: string; count?: string } }) {
  const Icon = data.icon === "chart" ? BarChart3 : data.icon === "users" ? Users : Lightbulb;
  return (
    <div className="rounded-xl border border-dashed border-indigo-300/80 bg-indigo-50/50 px-2 py-1.5 text-center dark:border-indigo-600/50 dark:bg-indigo-950/30">
      <Handle type="target" position={Position.Top} className="!bg-indigo-300" />
      <Icon className="mx-auto h-3.5 w-3.5 text-indigo-500" />
      <p className="text-[8px] font-semibold text-indigo-700 dark:text-indigo-300">{data.label}</p>
      {data.count && <p className="text-[7px] text-slate-500">{data.count}</p>}
    </div>
  );
}

function PulseEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, style, markerEnd, data }: EdgeProps) {
  const [path] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const active = data?.active as boolean;
  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {active && (
        <circle r="4" fill="#f97316">
          <animateMotion dur="2s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </>
  );
}

const nodeTypes = { you: YouNode, company: CompanyNode, contact: ContactNode, insight: InsightNode };
const edgeTypes = { pulse: PulseEdge };

export function NetworkFlowGraph({ job, contacts, activeStep = "research", cmuAlumniCount = 0, researchedCount = 0 }: Props) {
  const company = job.company ?? "Company";
  const outreachActive = activeStep === "outreach";
  const researchActive = activeStep === "research";

  const researched = researchedCount || contacts.filter((c) => c.has_research).length;
  const alumni = cmuAlumniCount || contacts.filter((c) => c.is_cmu_alumni).length;

  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = [
      { id: "you", type: "you", position: { x: 210, y: 200 }, data: {} },
      {
        id: "company",
        type: "company",
        position: { x: 200, y: 90 },
        data: { label: company, domain: job.company_domain },
      },
    ];
    const es: Edge[] = [
      {
        id: "you-company",
        source: "you",
        target: "company",
        type: "smoothstep",
        style: { stroke: "#6366f1", strokeWidth: 2.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#6366f1" },
      },
    ];

    contacts.slice(0, 5).forEach((c, i) => {
      const id = `c-${c.id}`;
      const x = 20 + i * 88;
      const isOutreachTarget = outreachActive && i === 1;
      ns.push({
        id,
        type: "contact",
        position: { x, y: 0 },
        data: {
          name: c.full_name.split(" ")[0],
          title: (c.title ?? "Contact").slice(0, 16),
          researched: c.has_research,
          outreach: isOutreachTarget,
        },
      });
      es.push({
        id: `e-${id}`,
        source: "company",
        target: id,
        type: isOutreachTarget ? "pulse" : "smoothstep",
        data: { active: isOutreachTarget },
        animated: outreachActive && !c.has_research,
        style: {
          stroke: isOutreachTarget ? "#f97316" : c.has_research ? "#8b5cf6" : researchActive ? "#93c5fd" : "#c7d2fe",
          strokeWidth: isOutreachTarget ? 3 : 1.5,
          strokeDasharray: c.has_research ? undefined : "6 4",
        },
      });
      if (isOutreachTarget) {
        es.push({
          id: `outreach-you-${id}`,
          source: "you",
          target: id,
          type: "pulse",
          data: { active: true },
          style: { stroke: "#f97316", strokeWidth: 2.5 },
        });
      }
    });

    ns.push(
      { id: "insight-1", type: "insight", position: { x: 0, y: 130 }, data: { label: "Interview Insights", icon: "bulb", count: researched ? `${researched} notes` : "Run research" } },
      { id: "insight-2", type: "insight", position: { x: 380, y: 130 }, data: { label: "Team Research", icon: "chart", count: `${contacts.length} contacts` } },
      { id: "insight-3", type: "insight", position: { x: 190, y: 280 }, data: { label: "CMU Alumni", icon: "users", count: alumni ? `${alumni} at company` : "None found" } },
    );
    es.push(
      { id: "you-insight", source: "you", target: "insight-3", type: "smoothstep", style: { stroke: "#c7d2fe", strokeWidth: 1, strokeDasharray: "4 4" } },
      { id: "co-insight", source: "company", target: "insight-2", type: "smoothstep", style: { stroke: "#a5b4fc", strokeWidth: 1, strokeDasharray: "4 4" } },
    );

    return { nodes: ns, edges: es };
  }, [company, contacts, job.company_domain, outreachActive, researchActive, researched, alumni]);

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">Your Signal Network</h3>
        <div className="flex gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-indigo-400" /> Connection</span>
          <span className="flex items-center gap-1"><span className="h-0.5 w-4 border-t border-dashed border-violet-400" /> Research</span>
          <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-orange-500 animate-pulse" /> Outreach</span>
        </div>
      </div>
      <div className="signal-graph h-[300px] overflow-hidden rounded-xl bg-gradient-to-b from-white/60 to-indigo-50/30 dark:from-slate-900/40 dark:to-indigo-950/20">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          nodesDraggable
          nodesConnectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} color="#c7d2fe" className="opacity-40" />
          <Controls showInteractive={false} className="!rounded-xl !border-indigo-100 !shadow-md" />
        </ReactFlow>
      </div>
    </div>
  );
}
