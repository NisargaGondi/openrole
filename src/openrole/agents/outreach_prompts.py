"""Outreach draft prompts keyed by contact tier (executive, HM, engineer, alumni, recruiter)."""

from __future__ import annotations

import re
from typing import Any

from openrole.db.models import Contact
from openrole.schemas.contact import ContactTier

_JSON_FORMAT = (
    'Return ONLY JSON: '
    '{"email": {"subject": "...", "body": "..."}, '
    '"linkedin": {"subject": null, "body": "..."}}. '
    "No placeholders like [Your Name] or [insert X]. "
    "Sign off with the candidate's first name from candidate_profile.name."
)

_COMMON_RULES = (
    "Use candidate_profile.full_context (resume, GitHub, LinkedIn, website) for credentials — "
    "do not invent experience. "
    "Open with research.primary_hook or the strongest research.outreach_angle — not a generic intro. "
    "Cite 1–2 concrete projects/tools from full_context that map to the job description. "
    "Never use bracket placeholders; every sentence must be send-ready."
)

_VISA_RULE = (
    "If candidate_profile.visa_status is set, mention work authorization only when natural "
    "(typically for recruiters or when asking about timeline) — one brief clause, not the focus."
)

# Per-tier templates: structure, limits, subject patterns, tone, CTA, LinkedIn strategy.
_TIER_TEMPLATES: dict[ContactTier, dict[str, Any]] = {
    ContactTier.EXECUTIVE: {
        "label": "Executive / senior leader (VP, Head of, C-level)",
        "email_words": "70-100",
        "linkedin_chars": "200-280",
        "subject_patterns": [
            "{Company} — {Role title} (CMU '{grad_short})",
            "Quick question on {Department or team} hiring",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) One-sentence hook from research (their public signal or team mission).\n"
            "2) One sentence: who you are + single strongest credential aligned to the role.\n"
            "3) State the exact role title you are pursuing.\n"
            "4) Ask who owns hiring for that role/team — do NOT ask for a long call or deep technical deep-dive.\n"
            "Keep total length 70–100 words. No bullet lists. No stack dumps."
        ),
        "tone": (
            "Respectful and concise — write to a senior leader whose time is scarce. "
            "Strategic, not peer-engineer jargon-heavy. No flattery or buzzwords."
        ),
        "cta": "Who on your team should I speak with about the {role} opening?",
        "linkedin": (
            "LINKEDIN: connection note only — hook + role interest + routing ask. "
            "No resume dump. Target 200–280 characters."
        ),
    },
    ContactTier.HIRING_MANAGER: {
        "label": "Hiring manager / engineering manager (team owner)",
        "email_words": "120-150",
        "linkedin_chars": "250-280",
        "subject_patterns": [
            "{Role title} — {specific tech or domain from JD}",
            "{Company} {Role title} — {your relevant project area}",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) Hook from research showing you understand what their team builds.\n"
            "2) Two sentences on concrete projects from full_context that map to the JD (stack, domain, scale).\n"
            "3) One thoughtful question about team scope or technical challenge — not 'any openings?'.\n"
            "4) Closing: graduation timing + interest in this specific role.\n"
            "Target 120–150 words."
        ),
        "tone": (
            "Peer-level technical — builder to builder. Show you read the JD and their research. "
            "Avoid HR-speak and credential laundry lists."
        ),
        "cta": "Would you be open to a brief chat about whether your team is the right fit for this role?",
        "linkedin": (
            "LINKEDIN: lead with shared technical interest from research; one project hook; "
            "low-pressure ask about the team. 250–280 chars."
        ),
    },
    ContactTier.TEAM_ENGINEER: {
        "label": "Team engineer (referral / peer path)",
        "email_words": "100-130",
        "linkedin_chars": "250-280",
        "subject_patterns": [
            "{Shared technical topic} @ {Company}",
            "Quick note on {Role title} team",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) Collegial opener tied to their work (research.public_signals or outreach_angle).\n"
            "2) One relatable project or stack overlap from full_context.\n"
            "3) Mention you are applying to / interested in {role title} on their team.\n"
            "4) Low-pressure ask: perspective on the team or openness to a referral — not a hard sell.\n"
            "Target 100–130 words. Slightly informal."
        ),
        "tone": (
            "Engineer-to-engineer, collegial, slightly informal. "
            "Skip management framing and corporate language."
        ),
        "cta": "Would you be open to sharing how the team is structured or pointing me to the right hiring contact?",
        "linkedin": (
            "LINKEDIN: casual peer tone; strongest technical hook first; optional referral ask. "
            "250–280 chars."
        ),
    },
    ContactTier.CMU_ALUMNI: {
        "label": "CMU alumni (warm network path)",
        "email_words": "100-140",
        "linkedin_chars": "250-280",
        "subject_patterns": [
            "Fellow CMU alum — {Role title} @ {Company}",
            "CMU → {Company} ({Role title})",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) First or second sentence MUST mention CMU / Carnegie Mellon (shared connection).\n"
            "2) Research hook tied to their role at the company.\n"
            "3) Brief fit: one project + interest in {role title}.\n"
            "4) Warm, low-pressure ask: advice, brief chat, or intro — not demanding.\n"
            "Technical depth should match contact.title (more technical for engineers/leaders).\n"
            "Target 100–140 words."
        ),
        "tone": "Warm, genuine, alumni-to-alumni. No forced flattery.",
        "cta": "I'd really value any advice you have as a CMU alum at {Company} — or whether you'd be open to a quick chat.",
        "linkedin": (
            "LINKEDIN: CMU mention in first line; one hook; soft ask. 250–280 chars."
        ),
    },
    ContactTier.ROLE_RECRUITER: {
        "label": "Role / technical recruiter",
        "email_words": "120-150",
        "linkedin_chars": "250-280",
        "subject_patterns": [
            "{Role title} — {Your name} — CMU {graduation}",
            "Application interest: {Role title} @ {Company}",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) State exact role title and company in sentence one.\n"
            "2) Three crisp bullets (use • or -) summarizing fit they can forward to the HM.\n"
            "3) Graduation date and location/start if in profile.\n"
            "4) Offer to share resume; ask to be routed to the right requisition.\n"
            "Target 120–150 words. Scannable."
        ),
        "tone": "Professional, clear, forwardable. Moderate technical detail — not a deep dive.",
        "cta": "Could you help route my profile to the hiring manager for this requisition?",
        "linkedin": (
            "LINKEDIN: role title + 2-line fit summary + ask to connect about this opening. "
            "250–280 chars."
        ),
    },
    ContactTier.GENERAL_RECRUITER: {
        "label": "General recruiter / HR",
        "email_words": "80-120",
        "linkedin_chars": "200-280",
        "subject_patterns": [
            "Interest in {Role title} at {Company}",
            "{Role title} — {Your name}",
        ],
        "structure": (
            "EMAIL structure (strict):\n"
            "1) Role title + why this company (one sentence each).\n"
            "2) Two-sentence human summary of qualifications — plain language.\n"
            "3) Graduation timing if relevant.\n"
            "4) Polite ask about process or right contact.\n"
            "Target 80–120 words. Minimal jargon and acronyms."
        ),
        "tone": "Warm, plain language. No architecture or paper citations unless JD is highly technical.",
        "cta": "Could you point me to the right person or process for this role?",
        "linkedin": "LINKEDIN: plain-language role interest + short qualification line. 200–280 chars.",
    },
    ContactTier.OTHER: {
        "label": "Related contact (tier unclear)",
        "email_words": "100-130",
        "linkedin_chars": "250-280",
        "subject_patterns": ["{Role title} @ {Company}", "Quick question on {Company} {team}"],
        "structure": (
            "EMAIL: research hook → brief fit (1 project) → clear ask about the role or routing. "
            "100–130 words. Match technical depth to contact.title."
        ),
        "tone": "Balanced professional.",
        "cta": "Would you be open to pointing me in the right direction for this role?",
        "linkedin": "LINKEDIN: hook + role interest + soft ask. 250–280 chars.",
    },
}

_TIER_LABELS: dict[ContactTier, str] = {
    ContactTier.EXECUTIVE: "Executive / senior leader",
    ContactTier.HIRING_MANAGER: "Hiring manager / team lead",
    ContactTier.TEAM_ENGINEER: "Team engineer (referral)",
    ContactTier.ROLE_RECRUITER: "Role / technical recruiter",
    ContactTier.GENERAL_RECRUITER: "General recruiter / HR",
    ContactTier.CMU_ALUMNI: "CMU alumni",
    ContactTier.OTHER: "Related contact",
}

_EVAL_CRITERIA_EXTRA: dict[ContactTier, list[str]] = {
    ContactTier.EXECUTIVE: [
        "Email under ~100 words — concise for a senior leader",
        "Ask is routing/referral to hiring owner, not a deep technical interview request",
        "No long bullet lists or stack dumps",
    ],
    ContactTier.HIRING_MANAGER: [
        "Technical specificity appropriate for a hiring manager",
        "Shows understanding of team/role scope, not generic interest",
        "Includes a thoughtful question about the team's work",
    ],
    ContactTier.TEAM_ENGINEER: [
        "Collegial engineer-to-engineer tone",
        "Low-pressure referral or team perspective ask",
    ],
    ContactTier.ROLE_RECRUITER: [
        "Role title and fit are easy to forward to HM (bullets or crisp summary)",
        "Balanced technical summary (not too deep, not too vague)",
    ],
    ContactTier.GENERAL_RECRUITER: [
        "Plain language; minimal unexplained jargon",
        "Clear role interest without technical overload",
    ],
    ContactTier.CMU_ALUMNI: [
        "CMU / Carnegie Mellon mentioned in the first two sentences of the email",
        "Warm alumni tone; low pressure",
    ],
}

_EXECUTIVE_TITLE_RE = re.compile(
    r"\b("
    r"head of|"
    r"vp|vice president|svp|evp|"
    r"chief\s+\w+\s+officer|ciso|cto|ceo|cfo|cpo|"
    r"president(?!\s+of\s+sales\s+application)"
    r")\b",
    re.I,
)
_MANAGER_TITLE_RE = re.compile(
    r"\b(director|manager|lead|principal|staff|distinguished)\b",
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

_RECRUITER_TIERS = frozenset({ContactTier.ROLE_RECRUITER, ContactTier.GENERAL_RECRUITER})


def is_leadership_tier(tier: ContactTier) -> bool:
    return tier in (ContactTier.EXECUTIVE, ContactTier.HIRING_MANAGER)


def resolve_contact_tier(contact: Contact) -> ContactTier:
    """Tier for outreach drafts; CMU alumni override unless contact is a recruiter."""
    meta = contact.metadata_json or {}
    stored: ContactTier | None = None
    tier_name = meta.get("tier")
    if tier_name:
        try:
            stored = ContactTier[tier_name]
        except KeyError:
            pass

    inferred = infer_tier_from_title(contact.title)

    if meta.get("is_cmu_alumni") and stored not in _RECRUITER_TIERS:
        return ContactTier.CMU_ALUMNI

    # Title-based executive overrides stale HIRING_MANAGER metadata from older discovery runs.
    if inferred == ContactTier.EXECUTIVE:
        return ContactTier.EXECUTIVE

    if stored is not None:
        return stored
    return inferred


def infer_tier_from_title(title: str | None) -> ContactTier:
    if not title:
        return ContactTier.OTHER
    title_l = title.lower()
    if _RECRUITER_TITLE_RE.search(title_l):
        if "technical" in title_l or "engineering" in title_l:
            return ContactTier.ROLE_RECRUITER
        return ContactTier.GENERAL_RECRUITER
    if _is_executive_title(title_l):
        return ContactTier.EXECUTIVE
    if _MANAGER_TITLE_RE.search(title_l) and not (
        _ENGINEER_TITLE_RE.search(title_l)
        and not re.search(r"\b(manager|director|head of|vp)\b", title_l, re.I)
    ):
        return ContactTier.HIRING_MANAGER
    if _ENGINEER_TITLE_RE.search(title_l):
        return ContactTier.TEAM_ENGINEER
    return ContactTier.OTHER


def _is_executive_title(title_l: str) -> bool:
    if _EXECUTIVE_TITLE_RE.search(title_l):
        return True
    if re.search(r"\bdistinguished\b", title_l, re.I) and not (
        _ENGINEER_TITLE_RE.search(title_l)
        and not re.search(r"\b(head of|director|vp)\b", title_l, re.I)
    ):
        return True
    return False


def tier_label(tier: ContactTier) -> str:
    return _TIER_LABELS.get(tier, _TIER_LABELS[ContactTier.OTHER])


def get_tier_template(tier: ContactTier) -> dict[str, Any]:
    return _TIER_TEMPLATES.get(tier, _TIER_TEMPLATES[ContactTier.OTHER])


def build_draft_system_prompt(
    *,
    tier: ContactTier,
    revision_feedback: str | None = None,
    graduation: str | None = None,
    role_search: str | None = None,
) -> str:
    template = get_tier_template(tier)
    parts = [
        "Write personalized cold outreach (email + LinkedIn connection note) for an F-1 student "
        "job seeker pursuing a specific opening.",
        _COMMON_RULES,
        _VISA_RULE,
        f"Audience: {template['label']}.",
        f"Tone: {template['tone']}",
        f"Email length: {template['email_words']} words.",
        f"Suggested subject patterns: {', '.join(template['subject_patterns'])}.",
        template["structure"],
        f"Primary CTA style: {template['cta']}.",
        template["linkedin"],
    ]
    if graduation:
        parts.append(
            f"Include graduation in {graduation} and interest in {role_search or 'full-time roles'} "
            "in the email close (before sign-off) unless tier rules say otherwise for executives "
            "(executives: graduation may be one short clause only)."
        )
    parts.append(_JSON_FORMAT)
    system = "\n\n".join(parts)
    if revision_feedback:
        system += f"\n\nRevise using this feedback — do not ignore it:\n{revision_feedback}"
    return system


def evaluation_criteria_for_tier(
    tier: ContactTier,
    *,
    graduation: str | None = None,
    role_search: str | None = None,
) -> list[str]:
    template = get_tier_template(tier)
    base = [
        "Opens with a specific research hook (not 'I hope this email finds you well')",
        "Names 1–2 concrete projects/experiences from candidate resume/GitHub — not generic claims",
        f"Email length appropriate for tier ({template['email_words']} words)",
        "LinkedIn note within character limit and different strategy than email (not a copy-paste)",
        "Professional human tone; no corporate boilerplate",
        "Clear ask without being pushy",
        "No placeholders or invented facts",
    ]
    if graduation and tier != ContactTier.EXECUTIVE:
        role = role_search or "full-time roles"
        base.append(f"Mentions graduating in {graduation} and interest in {role}")
    elif graduation and tier == ContactTier.EXECUTIVE:
        base.append(f"Graduation ({graduation}) mentioned briefly if at all — brevity prioritized")
    return base + _EVAL_CRITERIA_EXTRA.get(tier, [])


def build_evaluator_system_prompt(*, tier: ContactTier) -> str:
    template = get_tier_template(tier)
    return (
        "You evaluate cold outreach drafts for a technical job seeker (F-1 student). "
        f"The contact tier is {tier.name} ({template['label']}). "
        f"Email should be ~{template['email_words']} words. "
        "acceptable=true only if BOTH email and LinkedIn would plausibly earn a reply "
        "and meet tier-specific structure/tone. "
        "Return ONLY JSON: "
        '{"acceptable": bool, "grade": "good"|"needs_work", "feedback": "specific actionable fixes", '
        '"email_score": 0-100, "linkedin_score": 0-100}. '
        "feedback must cite what to fix (hook, length, tone, CTA, CMU mention, etc.)."
    )
