/** Visa / OPT / sponsorship signals from job ingestion (llm_enrich + scout). */

export type VisaSummary = {
  visa_status?: "eligible" | "ineligible" | "unknown" | null;
  accepts_opt?: boolean | null;
  accepts_cpt?: boolean | null;
  stem_opt_eligible?: boolean | null;
  will_sponsor?: boolean | null;
  work_auth_us_only?: boolean | null;
  visa_notes?: string | null;
  visa_confidence?: "high" | "medium" | "low" | null;
};

export type VisaTagVariant = "opt" | "cpt" | "stem" | "sponsor" | "unknown" | "no_sponsor";

export type VisaTag = {
  id: string;
  label: string;
  variant: VisaTagVariant;
  title?: string;
};

const VARIANT_HINT: Record<VisaTagVariant, string> = {
  opt: "Posting mentions OPT work authorization",
  cpt: "Posting mentions CPT work authorization",
  stem: "Role may qualify for STEM OPT extension",
  sponsor: "Employer indicates future visa sponsorship",
  unknown: "No OPT, CPT, or sponsorship language found — verify before applying",
  no_sponsor: "Posting indicates no visa sponsorship or US-only authorization",
};

export function deriveVisaTags(visa?: VisaSummary | null): VisaTag[] {
  if (!visa || Object.values(visa).every((v) => v == null)) {
    return [
      {
        id: "unknown",
        label: "Unknown",
        variant: "unknown",
        title: "Visa status not analyzed — re-ingest with pasted JD if missing",
      },
    ];
  }

  const notes = visa.visa_notes?.trim() || undefined;
  const status = visa.visa_status;

  const noSponsor =
    status === "ineligible" || visa.work_auth_us_only === true || visa.will_sponsor === false;

  if (noSponsor) {
    return [
      {
        id: "no_sponsor",
        label: "No sponsorship",
        variant: "no_sponsor",
        title: notes ?? VARIANT_HINT.no_sponsor,
      },
    ];
  }

  const tags: VisaTag[] = [];

  if (visa.accepts_opt === true) {
    tags.push({ id: "opt", label: "OPT", variant: "opt", title: notes ?? VARIANT_HINT.opt });
  }
  if (visa.accepts_cpt === true) {
    tags.push({ id: "cpt", label: "CPT", variant: "cpt", title: notes ?? VARIANT_HINT.cpt });
  }
  if (visa.stem_opt_eligible === true) {
    tags.push({ id: "stem", label: "STEM OPT", variant: "stem", title: notes ?? VARIANT_HINT.stem });
  }
  if (visa.will_sponsor === true) {
    tags.push({
      id: "sponsor",
      label: "F-1 sponsorship",
      variant: "sponsor",
      title: notes ?? VARIANT_HINT.sponsor,
    });
  }

  if (tags.length === 0) {
    if (status === "eligible") {
      tags.push({
        id: "f1_friendly",
        label: "F-1 friendly",
        variant: "opt",
        title: notes ?? "Posting appears open to international students on F-1",
      });
    } else {
      tags.push({
        id: "unknown",
        label: "Unknown",
        variant: "unknown",
        title: notes ?? VARIANT_HINT.unknown,
      });
    }
  }

  return tags;
}
