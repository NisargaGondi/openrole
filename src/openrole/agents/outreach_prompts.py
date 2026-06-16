"""Outreach draft prompts keyed by contact tier (hiring manager, recruiter, engineer, etc.)."""

from __future__ import annotations

import re

from openrole.db.models import Contact
from openrole.schemas.contact import ContactTier

_JSON_FORMAT = (
    'Return ONLY JSON: '
    '{"email": {"subject": "...", "body": "..."}, '
    '"linkedin": {"subject": null, "body": "..."}}. '
    "Email under 150 words; LinkedIn connection note under 280 characters. "
    "No placeholders like [Your Name]. Sign off with the candidate's first name from profile."
)

_COMMON_RULES = (
    "Use candidate_profile.full_context (resume, GitHub, LinkedIn, website) for accurate "
    "credentials — do not invent experience not supported by that context. "
    "Early in the email, name 1–2 specific projects, tools, papers, or experiences from "
    "candidate_profile.full_context that clearly relate to this role's stack, domain, or "
    "problems; briefly say why each is relevant. "
    "Reference something specific from the contact research when possible."
)

_RELATED_WORK_RULE = (
    "The email must cite concrete related work from the candidate's resume, GitHub, or "
    "LinkedIn (via full_context) — not generic claims like 'strong background in ML'."
)

_CLOSING_RULE_TEMPLATE = (
    "Close the email (before sign-off) with one natural sentence that notes graduation in "
    "{graduation} and asks about {role_search}. "
    "LinkedIn note: lead with the strongest related-work hook; include graduation and the "
    "{role_search} ask only if it fits within 280 characters."
)

# Edit these blocks to refine tone per audience.
_TIER_INSTRUCTIONS: dict[ContactTier, str] = {
    ContactTier.HIRING_MANAGER: (
        "Audience: hiring manager or engineering director who owns the team. "
        "Tone: peer-level, technical, and concise — write like one builder to another. "
        "Lead with 1–2 concrete technical accomplishments that map to the job description "
        "(stack, scale, domain). Show you understand what the team likely works on. "
        "Ask a thoughtful question about team scope, technical challenges, or how the role "
        "fits the org — not a generic 'any openings?' note. "
        "Avoid HR-speak, buzzwords, and long credential lists."
    ),
    ContactTier.TEAM_ENGINEER: (
        "Audience: individual contributor engineer on the target team (referral path). "
        "Tone: collegial, technical, slightly informal — like reaching out to a senior teammate. "
        "Lead with a shared technical interest, stack overlap, or something specific from their "
        "role/research. Keep jargon appropriate for engineers; skip management framing. "
        "Ask for a brief perspective on the team or whether they'd be open to referring you — "
        "low pressure, not a hard sell."
    ),
    ContactTier.ROLE_RECRUITER: (
        "Audience: recruiter tied to this role or technical hiring (talent partner, sourcer). "
        "Tone: professional and clear; moderate technical detail — enough to show fit, not a deep dive. "
        "State the exact role title and company. Summarize fit in 2–3 crisp bullets they can "
        "forward to the hiring manager. Mention location/start timing only if present in context. "
        "Make it easy for them to route you to the right requisition."
    ),
    ContactTier.GENERAL_RECRUITER: (
        "Audience: company-wide or non-technical recruiter / HR coordinator. "
        "Tone: warm, plain language — minimize jargon, acronyms, and implementation detail. "
        "Focus on role title, why the company, and a short human summary of qualifications. "
        "No deep technical architecture or stack talk unless the JD itself is highly technical. "
        "Clear, polite ask to learn about the process or be pointed to the right contact."
    ),
    ContactTier.CMU_ALUMNI: (
        "Audience: CMU alumni at the company (warm intro path). "
        "Tone: friendly and personal; mention the shared CMU connection early. "
        "Technical depth should match their title: more technical for engineers/managers, "
        "lighter for non-engineering roles. Ask for brief advice or a coffee chat — not demanding. "
        "Keep it genuine; do not over-flatter."
    ),
    ContactTier.OTHER: (
        "Audience: related contact (tier unclear). "
        "Tone: balanced professional — moderately technical if their title is engineering-related, "
        "otherwise accessible and non-jargon. Tailor depth to contact.title when inferable."
    ),
}

_TIER_LABELS: dict[ContactTier, str] = {
    ContactTier.HIRING_MANAGER: "Hiring manager / engineering leader",
    ContactTier.TEAM_ENGINEER: "Team engineer (referral)",
    ContactTier.ROLE_RECRUITER: "Role / technical recruiter",
    ContactTier.GENERAL_RECRUITER: "General recruiter / HR",
    ContactTier.CMU_ALUMNI: "CMU alumni",
    ContactTier.OTHER: "Related contact",
}

_EVAL_CRITERIA_EXTRA: dict[ContactTier, list[str]] = {
    ContactTier.HIRING_MANAGER: [
        "Technical specificity appropriate for a hiring manager",
        "Shows understanding of team/role scope, not generic interest",
    ],
    ContactTier.TEAM_ENGINEER: [
        "Collegial engineer-to-engineer tone",
        "Appropriate technical depth for a peer IC",
    ],
    ContactTier.ROLE_RECRUITER: [
        "Role title and fit are easy to forward to HM",
        "Balanced technical summary (not too deep, not too vague)",
    ],
    ContactTier.GENERAL_RECRUITER: [
        "Plain language; minimal unexplained jargon",
        "Clear role interest without technical overload",
    ],
    ContactTier.CMU_ALUMNI: [
        "CMU connection feels natural, not forced",
        "Tone matches alumni outreach (warm, low pressure)",
    ],
}

_MANAGER_TITLE_RE = re.compile(
    r"\b(director|head of|vp|vice president|manager|lead|principal|staff|distinguished)\b",
    re.I,
)
_RECRUITER_TITLE_RE = re.compile(
    r"\b(recruiter|recruiting|talent acquisition|talent partner|sourcer|hr\b|human resources)\b",
    re.I,
)
_ENGINEER_TITLE_RE = re.compile(
    r"\b(engineer|developer|scientist|architect|swe\b|sde\b|ml\b|researcher)\b",
    re.I,
)


def resolve_contact_tier(contact: Contact) -> ContactTier:
    """Read tier from discovery metadata, or infer a coarse tier from job title."""
    meta = contact.metadata_json or {}
    tier_name = meta.get("tier")
    if tier_name:
        try:
            return ContactTier[tier_name]
        except KeyError:
            pass
    return infer_tier_from_title(contact.title)


def infer_tier_from_title(title: str | None) -> ContactTier:
    if not title:
        return ContactTier.OTHER
    title_l = title.lower()
    if _RECRUITER_TITLE_RE.search(title_l):
        if "technical" in title_l or "engineering" in title_l:
            return ContactTier.ROLE_RECRUITER
        return ContactTier.GENERAL_RECRUITER
    if _MANAGER_TITLE_RE.search(title_l) and not (
        _ENGINEER_TITLE_RE.search(title_l)
        and not re.search(r"\b(manager|director|head of|vp)\b", title_l, re.I)
    ):
        return ContactTier.HIRING_MANAGER
    if _ENGINEER_TITLE_RE.search(title_l):
        return ContactTier.TEAM_ENGINEER
    return ContactTier.OTHER


def tier_label(tier: ContactTier) -> str:
    return _TIER_LABELS.get(tier, _TIER_LABELS[ContactTier.OTHER])


def build_draft_system_prompt(
    *,
    tier: ContactTier,
    revision_feedback: str | None = None,
    graduation: str | None = None,
    role_search: str | None = None,
) -> str:
    audience = _TIER_INSTRUCTIONS.get(tier, _TIER_INSTRUCTIONS[ContactTier.OTHER])
    parts = [
        "Write personalized outreach drafts for a job seeker reaching out about a specific role.",
        _COMMON_RULES,
        _RELATED_WORK_RULE,
        audience,
    ]
    if graduation:
        parts.append(
            _CLOSING_RULE_TEMPLATE.format(
                graduation=graduation,
                role_search=role_search or "full-time roles",
            )
        )
    parts.append(_JSON_FORMAT)
    system = " ".join(parts)
    if revision_feedback:
        system += " Revise the previous draft using revision_feedback — do not ignore it."
    return system


def evaluation_criteria_for_tier(
    tier: ContactTier,
    *,
    graduation: str | None = None,
    role_search: str | None = None,
) -> list[str]:
    base = [
        "Specific hook from research (not generic)",
        "Names 1–2 concrete related projects/experiences from resume, GitHub, or LinkedIn",
        "Under length limits (email ~150 words, LinkedIn ~280 chars)",
        "Professional human tone, no corporate boilerplate",
        "Clear ask without being pushy",
        "No placeholders or invented facts",
    ]
    if graduation:
        role = role_search or "full-time roles"
        base.append(f"Mentions graduating in {graduation} and asks about {role}")
    return base + _EVAL_CRITERIA_EXTRA.get(tier, [])
