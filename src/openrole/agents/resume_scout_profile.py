"""Derive scout search terms and job-match signals from a selected resume."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Common tech / domain vocabulary (used to boost extraction, not as a fixed filter list)
_TECH_VOCAB = frozenset(
    {
        "python",
        "java",
        "javascript",
        "typescript",
        "c++",
        "go",
        "rust",
        "sql",
        "pytorch",
        "tensorflow",
        "keras",
        "scikit-learn",
        "sklearn",
        "pandas",
        "numpy",
        "spark",
        "hadoop",
        "kubernetes",
        "docker",
        "aws",
        "gcp",
        "azure",
        "linux",
        "git",
        "nlp",
        "llm",
        "transformer",
        "bert",
        "gpt",
        "rag",
        "cv",
        "opencv",
        "ml",
        "ai",
        "machine",
        "learning",
        "deep",
        "neural",
        "security",
        "cybersecurity",
        "infosec",
        "cryptography",
        "penetration",
        "malware",
        "forensics",
        "kubernetes",
        "microservices",
        "distributed",
        "backend",
        "frontend",
        "api",
        "grpc",
        "redis",
        "postgresql",
        "mongodb",
        "react",
        "node",
        "flask",
        "fastapi",
        "django",
        "spring",
        "cuda",
        "gpu",
        "inference",
        "training",
        "reinforcement",
        "computer",
        "vision",
        "adversarial",
        "federated",
        "privacy",
    }
)

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "your",
        "our",
        "you",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "using",
        "used",
        "work",
        "worked",
        "team",
        "project",
        "projects",
        "experience",
        "university",
        "college",
        "school",
        "carnegie",
        "mellon",
        "cmu",
        "may",
        "june",
        "july",
        "august",
        "present",
        "intern",
        "internship",
    }
)

_ROLE_TITLE_RE = re.compile(
    r"\b("
    r"(?:machine learning|ml|ai|software|security|cyber(?:security)?|data|research|applied|"
    r"platform|cloud|backend|front[\s-]?end|full[\s-]?stack|devops|site reliability|"
    r"product|systems|network|application|red team|offensive|defensive)"
    r"\s+"
    r"(?:engineer|developer|scientist|researcher|architect|analyst|intern)"
    r"|research\s+scientist|applied\s+scientist"
    r")\b",
    re.I,
)

_LABEL_ROLE_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bml\b|machine.?learning", re.I), "machine learning engineer"),
    (re.compile(r"ai.?sec|ai.?security", re.I), "AI security engineer"),
    (re.compile(r"cyber|infosec|security", re.I), "cybersecurity engineer"),
    (re.compile(r"\bswe\b|software", re.I), "software engineer"),
    (re.compile(r"research", re.I), "research engineer"),
]


@dataclass(frozen=True)
class ScoutResumeProfile:
    resume_label: str
    skills: frozenset[str]
    phrases: frozenset[str]
    role_titles: tuple[str, ...]
    search_terms: tuple[str, ...]
    focus_summary: str

    def to_dict(self) -> dict:
        return {
            "resume_label": self.resume_label,
            "skills": sorted(self.skills)[:40],
            "phrases": sorted(self.phrases)[:20],
            "role_titles": list(self.role_titles),
            "search_terms": list(self.search_terms),
            "focus_summary": self.focus_summary,
        }


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]{2,}", text.lower()))


def _bigrams(text: str) -> set[str]:
    words = [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOPWORDS]
    return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}


def _extract_role_titles(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _ROLE_TITLE_RE.finditer(text):
        title = re.sub(r"\s+", " ", match.group(0)).strip()
        key = title.lower()
        if key not in seen and len(title) > 5:
            seen.add(key)
            found.append(title)
    # Experience lines: "Title, Company" or "Title | Company"
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 120:
            continue
        for part in re.split(r"\s+[-@|]\s+|\s+at\s+", line, maxsplit=1):
            part = part.strip(" •\t")
            if _ROLE_TITLE_RE.search(part):
                title = re.sub(r"\s+", " ", _ROLE_TITLE_RE.search(part).group(0)).strip()
                if title.lower() not in seen:
                    seen.add(title.lower())
                    found.append(title)
    return found[:8]


def _skills_from_label(label: str) -> set[str]:
    base = Path(label).stem.lower().replace("_", " ").replace("-", " ")
    return _tokenize(base) - _STOPWORDS


def _search_terms_from_profile(
    *,
    label: str,
    role_titles: list[str],
    skills: set[str],
) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        t = term.strip()
        key = t.lower()
        if t and key not in seen:
            seen.add(key)
            terms.append(t)

    for title in role_titles[:3]:
        add(title)

    label_l = label.lower()
    for pattern, hint in _LABEL_ROLE_HINTS:
        if pattern.search(label_l):
            add(hint)

    # Skill-driven query: top domain tokens from resume
    domain_hits = [s for s in skills if s in _TECH_VOCAB]
    if any(s in domain_hits for s in ("machine", "learning", "pytorch", "tensorflow", "llm", "nlp")):
        add("machine learning engineer")
    if any(s in domain_hits for s in ("security", "cybersecurity", "infosec", "adversarial")):
        add("security engineer")
    if "cybersecurity" in skills or "cyber" in label_l:
        add("cybersecurity engineer")
    if not terms:
        add("software engineer")

    return terms[:5]


def build_scout_resume_profile(*, text: str, label: str) -> ScoutResumeProfile:
    """Parse one resume into scout search terms and match vocabulary."""
    clean = re.sub(r"\s+", " ", text).strip()
    lower = clean.lower()
    tokens = _tokenize(lower) - _STOPWORDS
    phrases = _bigrams(lower)

    # Skills: vocab hits + tokens from Skills/Technical sections
    skills = {t for t in tokens if t in _TECH_VOCAB or len(t) >= 4}
    skills |= _skills_from_label(label)

    section_skills: set[str] = set()
    for header in ("skills", "technical skills", "technologies", "tools", "expertise"):
        idx = lower.find(header)
        if idx >= 0:
            chunk = lower[idx : idx + 800]
            section_skills |= _tokenize(chunk) - _STOPWORDS
    skills |= {t for t in section_skills if t in _TECH_VOCAB or len(t) >= 3}

    role_titles = _extract_role_titles(clean)
    search_terms = _search_terms_from_profile(label=label, role_titles=role_titles, skills=skills)

    focus_parts = []
    if role_titles:
        focus_parts.append(role_titles[0])
    top_skills = sorted(skills & _TECH_VOCAB)[:6]
    if top_skills:
        focus_parts.append(", ".join(top_skills))
    focus_summary = " · ".join(focus_parts) if focus_parts else label

    return ScoutResumeProfile(
        resume_label=label,
        skills=frozenset(skills),
        phrases=frozenset(phrases),
        role_titles=tuple(role_titles),
        search_terms=tuple(search_terms),
        focus_summary=focus_summary,
    )


def job_matches_resume(
    job_text: str,
    title: str,
    profile: ScoutResumeProfile,
    *,
    min_skill_hits: int = 2,
) -> tuple[bool, int, list[str]]:
    """Return (matches, hit_count, matched_terms)."""
    blob = f"{title} {job_text}".lower()
    job_tokens = _tokenize(blob)
    job_phrases = _bigrams(blob)

    matched_skills = sorted(profile.skills & job_tokens)
    matched_phrases = sorted(profile.phrases & job_phrases)

    title_l = (title or "").lower()
    title_hit = any(rt.lower() in title_l or title_l in rt.lower() for rt in profile.role_titles)

    hit_count = len(matched_skills) + len(matched_phrases) * 2 + (5 if title_hit else 0)
    if title_hit:
        return True, hit_count, matched_skills[:10]
    if len(matched_phrases) >= 1 and len(matched_skills) >= 1:
        return True, hit_count, matched_skills[:10]
    if len(matched_skills) >= min_skill_hits:
        return True, hit_count, matched_skills[:10]
    # Label-driven fallback: ML resume should still match obvious ML titles
    for term in profile.search_terms:
        if term.lower() in title_l:
            return True, hit_count + 3, matched_skills[:10]
    return False, hit_count, matched_skills[:10]
