"use client";

/**
 * Renders plain text or HTML job descriptions / draft bodies with readable paragraphs.
 */

function normalizeText(raw: string): string {
  let text = raw.trim();
  if (!text) return "";

  if (/<[a-z][\s\S]*>/i.test(text)) {
    text = text
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p[^>]*>/gi, "\n\n")
      .replace(/<\/div>\s*<div[^>]*>/gi, "\n\n")
      .replace(/<\/li>\s*/gi, "\n")
      .replace(/<li[^>]*>/gi, "• ")
      .replace(/<\/h[1-6]>\s*/gi, "\n\n")
      .replace(/<[^>]+>/g, "")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&#39;/g, "'");
  }

  text = text
    .replace(/\r\n/g, "\n")
    .replace(/\t/g, "  ")
    // Inline bullets / numbered lists often arrive as one line from scrapers
    .replace(/([.!?])\s+(?=[•●▪-]\s)/g, "$1\n")
    .replace(/\s([•●▪-]\s+)/g, "\n$1")
    .replace(/\s(\d+[.)]\s+)/g, "\n$1")
    // Section headers in plain text
    .replace(/\s+(Responsibilities|Requirements|Qualifications|About (?:the role|us)|What you'll do|Who you are|Benefits|Nice to have|Must have|Preferred|Skills|Experience):\s*/gi, "\n\n$1:\n");

  return text.trim();
}

function renderBlocks(text: string) {
  const paragraphs = text.split(/\n{2,}/);
  return paragraphs.map((block, i) => {
    const lines = block.split("\n").filter((l) => l.trim());
    const isList = lines.length > 0 && lines.every((l) => /^[\s]*[-•*●▪]\s/.test(l) || /^[\s]*\d+[.)]\s/.test(l));
    const isHeading = lines.length === 1 && /^[\w\s/&]+:\s*$/.test(lines[0].trim());

    if (isHeading) {
      return (
        <p key={i} className="formatted-heading mt-4 mb-1 text-sm font-semibold text-heading first:mt-0">
          {lines[0].trim()}
        </p>
      );
    }

    if (isList) {
      return (
        <ul key={i} className="formatted-list my-2 list-disc space-y-1.5 pl-5">
          {lines.map((line, j) => (
            <li key={j}>{line.replace(/^[\s]*[-•*●▪]\s|^[\s]*\d+[.)]\s/, "").trim()}</li>
          ))}
        </ul>
      );
    }

    if (lines.length > 1) {
      return (
        <div key={i} className="formatted-block my-2 space-y-1.5">
          {lines.map((line, j) => (
            <p key={j}>{line.trim()}</p>
          ))}
        </div>
      );
    }

    const trimmed = block.trim();
    if (trimmed.length > 320 && !trimmed.includes("\n")) {
      const sentences = trimmed.match(/[^.!?]+[.!?]+(?:\s|$)|[^.!?]+$/g) ?? [trimmed];
      return (
        <div key={i} className="formatted-block my-2 space-y-1.5">
          {sentences.map((s, j) => (
            <p key={j}>{s.trim()}</p>
          ))}
        </div>
      );
    }

    return (
      <p key={i} className="formatted-block my-2">
        {trimmed}
      </p>
    );
  });
}

type Props = {
  text: string | null | undefined;
  className?: string;
  clamp?: number;
};

export function FormattedText({ text, className = "", clamp }: Props) {
  if (!text?.trim()) return null;
  const normalized = normalizeText(text);
  const blocks = renderBlocks(normalized);

  return (
    <div
      className={`formatted-text text-sm leading-relaxed ${className}`}
      style={clamp ? { maxHeight: `${clamp}rem`, overflow: "hidden" } : undefined}
    >
      {blocks}
    </div>
  );
}

export function normalizeDescription(raw: string | null | undefined): string {
  if (!raw) return "";
  return normalizeText(raw);
}
