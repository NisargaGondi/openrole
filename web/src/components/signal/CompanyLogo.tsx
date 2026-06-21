"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

type Props = {
  domain?: string | null;
  company?: string | null;
  size?: number;
  className?: string;
  circular?: boolean;
};

function logoSources(domain: string): string[] {
  return [
    `https://logo.clearbit.com/${domain}`,
    `https://www.google.com/s2/favicons?domain=${domain}&sz=128`,
    `https://icons.duckduckgo.com/ip3/${domain}.ico`,
  ];
}

function LetterFallback({
  company,
  size,
  className,
  circular,
}: Pick<Props, "company" | "size" | "className" | "circular">) {
  const letter = (company ?? "?")[0]?.toUpperCase() ?? "?";
  const radius = circular ? "rounded-full" : "rounded-2xl";
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center bg-gradient-to-br from-indigo-500 to-violet-600 font-bold text-white shadow-md",
        radius,
        className,
      )}
      style={{ width: size, height: size, fontSize: (size ?? 56) * 0.38 }}
    >
      {letter}
    </div>
  );
}

function CompanyLogoImage({ domain, company, size = 56, className, circular = false }: Props & { domain: string }) {
  const [srcIndex, setSrcIndex] = useState(0);
  const sources = logoSources(domain);
  const src = sources[srcIndex] ?? null;
  const radius = circular ? "rounded-full" : "rounded-2xl";

  if (!src || srcIndex >= sources.length) {
    return <LetterFallback company={company} size={size} className={className} circular={circular} />;
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={`${company ?? "Company"} logo`}
      width={size}
      height={size}
      className={cn(radius, "shrink-0 bg-white object-contain p-1 shadow-sm ring-1 ring-slate-100", className)}
      style={{ width: size, height: size }}
      onError={() => setSrcIndex((i) => i + 1)}
    />
  );
}

export function CompanyLogo({ domain, company, size = 56, className, circular = false }: Props) {
  if (!domain) {
    return <LetterFallback company={company} size={size} className={className} circular={circular} />;
  }
  return (
    <CompanyLogoImage
      key={domain}
      domain={domain}
      company={company}
      size={size}
      className={className}
      circular={circular}
    />
  );
}
