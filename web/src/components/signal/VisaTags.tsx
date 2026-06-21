"use client";

import { deriveVisaTags, type VisaSummary } from "@/lib/visa";
import { cn } from "@/lib/utils";

const VARIANT_CLASS: Record<string, string> = {
  opt: "visa-tag-opt",
  cpt: "visa-tag-opt",
  stem: "visa-tag-opt",
  sponsor: "visa-tag-sponsor",
  unknown: "visa-tag-unknown",
  no_sponsor: "visa-tag-no",
};

type Props = {
  visa?: VisaSummary | null;
  size?: "sm" | "md";
  className?: string;
};

export function VisaTags({ visa, size = "sm", className }: Props) {
  const tags = deriveVisaTags(visa);
  if (!tags.length) return null;

  return (
    <div className={cn("flex flex-wrap items-center gap-1.5", className)}>
      {tags.map((tag) => (
        <span
          key={tag.id}
          title={tag.title}
          className={cn(
            "visa-tag inline-flex items-center rounded-full font-bold uppercase tracking-wide",
            VARIANT_CLASS[tag.variant],
            size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-2.5 py-1 text-xs",
          )}
        >
          {tag.label}
        </span>
      ))}
    </div>
  );
}
