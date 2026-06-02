# OpenRole

Job search tooling that does the boring research so you can write the emails that actually get read.

Most job boards tell you *what* is open. OpenRole is built around *who* is hiring, *which team* owns the role, and *how* to reach them without sounding like you mailed five hundred people from the same template.

> **Status:** Early development. The pipeline is designed; implementation is in progress. APIs and data sources are still being evaluated.

**Repo:** https://github.com/NisargaGondi/openrole

---

## Table of contents

- [What it does](#what-it-does)
- [What it does not do](#what-it-does-not-do)
- [Collaboration & Git workflow](#collaboration--git-workflow)
- [Implementation plan](#implementation-plan)
- [Architecture](#architecture)
- [Project layout](#project-layout-planned)
- [Setup](#setup)
- [Configuration & costs](#configuration--costs)
- [Ethics & ToS](#ethics--tos)
- [Risks](#risks)
- [License](#license)

---

## What it does

You hand it a job link or a pasted job description. From there it runs a multi-step workflow:

1. **Parse the role** — title, company, department, locations (including multi-site postings), requirements, and where the listing lives (LinkedIn, Greenhouse, Workday, Handshake, etc.).
2. **Map the company** — figure out which org/team the role likely sits in, especially when the posting is vague.
3. **Find people worth talking to** — hiring managers, recruiters tied to the posting, engineers on the team, and alumni where that’s useful. Results are ranked; you’re not blasting the whole company directory.
4. **Research each contact** — enough context to reference something real (their work, a post, a shared thread) before you write.
5. **Draft outreach** — cold emails and short LinkedIn connection notes. **Drafts only.** Nothing sends without you reviewing it.
6. **Resume check** — compare your resume(s) against the JD for ATS gaps and concrete edit suggestions.
7. **Application help** — draft answers to written application questions when the form is accessible; same human tone, same review-before-send rule.

### Phase B (later)

A background scout runs a few times a week: similar roles, deduped against what you already have, synced to Notion / Google Sheets and a local database so nothing slips through because you forgot to refresh a board.

---

## What it does *not* do

- It does not auto-send email or LinkedIn messages.
- It does not pretend scraped data is always correct — you verify contacts before you reach out.
- It is not a replacement for career center advice, interview prep, or knowing why you want a role.

The goal is to remove hours of tab-hopping, not to remove you from the process.

---

## Who this is for

Built for a search targeting **ML/AI engineering**, **AI security**, and **security** roles (with software engineering as a lower priority). The architecture is role-agnostic if you change the search profile.

Graduation target: **May 2027**. Phase B and company targeting are timed around that horizon.

---

## Collaboration & Git workflow

Three branches on [GitHub](https://github.com/NisargaGondi/openrole):

| Branch | Owner | Purpose |
|--------|-------|---------|
| `main` | shared | Stable. Merged PRs only. |
| `ngondi` | Nisarga | Day-to-day work → PR into `main` |
| `sbellad` | collaborator | Day-to-day work → PR into `main` |

**Never commit directly to `main`.** Always work on your branch and open a pull request.

### Nisarga (`ngondi`)

One-time setup (already done if you cloned and checked out `ngondi`):

```bash
cd openrole
git fetch origin
git checkout ngondi
git branch -u origin/ngondi
```

**Start of a work session** (sync with latest `main`):

```bash
git checkout ngondi
git fetch origin
git merge origin/main    # or: git rebase origin/main
```

**Save and push your branch:**

```bash
git add .
git commit -m "Describe what changed and why"
git push origin ngondi
```

**Open a PR into `main`:**

```bash
gh pr create --base main --head ngondi --title "Short title" --body "## Summary
- ...

## Test plan
- [ ] ..."
```

Or use GitHub: **Compare & pull request** after `git push`.

**After your PR is merged:**

```bash
git checkout ngondi
git fetch origin
git merge origin/main
git push origin ngondi
```

### Collaborator (`sbellad`)

Same flow, replacing `ngondi` with `sbellad`.

### Rules

- Pull or merge `origin/main` into your branch before big new work.
- Use `.env` locally only; commit `.env.example` when we add it.
- Optional on GitHub: **Settings → Branches →** protect `main` (require PR, no direct push).

### Suggested work split (adjust as you like)

Split by **track** so you merge less often into the same modules:

| Track A — Data & ingestion | Track B — Outreach & agents |
|----------------------------|-----------------------------|
| `src/scrapers/` (Workday, CareerShift, ATS) | `src/agents/company_intel.py` |
| `src/agents/job_ingestion.py` | `src/agents/people_discovery.py` |
| `src/tools/jobspy_client.py`, `ats_apis` | `src/agents/person_research.py`, `email_writer.py` |
| `src/db/` models + migrations | `src/agents/resume_optimizer.py`, `app_assistant.py` |
| `src/agents/job_scout.py` (Phase B) | `src/graph/` LangGraph wiring |
| `scripts/seed_companies.py`, `migrate_db.py` | `src/ui/` Streamlit pages |

**Shared / pair on together:** `src/graph/state.py`, `config.py`, `.env.example`, integration tests, and anything that touches both tracks (define interfaces early — e.g. job JSON schema, contact record shape).

**Foundation (Week 1):** Do together or one person lands it on `main` before splitting.

---

## Implementation plan

Build in order. Each step should leave something you can run or test, even if the UI is rough.

### Milestones

| # | Milestone | Owner (fill in) | Status |
|---|-----------|-----------------|--------|
| 0 | Foundation — `pyproject.toml`, DB schema, `.env.example`, Streamlit shell | ngondi | [x] |
| 1 | Job ingestion — URL + pasted JD, structured output | | [ ] |
| 2 | People discovery + priority ranking | | [ ] |
| 3 | Person research + email / LinkedIn drafts | | [ ] |
| 4 | Resume ATS pass + application question drafts | | [ ] |
| 5 | LangGraph orchestration + human review gate in UI | | [ ] |
| 6 | Phase B — scheduled scout, dedup, Notion/Sheets sync | | [ ] |
| 7 | Polish — dashboard, notifications, docs | | [ ] |
| — | Company list seed (200–250 targets) — **not automated**; research doc → feeds scout | | [ ] |

### Timeline (rough)

| Weeks | Focus |
|-------|--------|
| 1 | Foundation + start job ingestion |
| 1–2 | Job ingestion complete (JobSpy, ATS APIs, Workday, Handshake path) |
| 2–3 | People discovery (Apollo, CareerShift automation, ranking) |
| 3–4 | Person research + email writer + review UI |
| 4 | Resume optimizer + application assistant |
| 4–5 | LangGraph StateGraph, checkpointing, error handling |
| 5–6 | Job scout, sync, polish |

### Tech stack

| Piece | Choice | Why |
|-------|--------|-----|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) | Branching pipelines, human review gates, resumable state |
| LLM components | LangChain inside graph nodes | Prompts, parsers, tools — not the main scheduler |
| Language / UI | Python + Streamlit | Fast iteration for a two-person project |
| Job listings | JobSpy, Greenhouse / Lever / Ashby APIs, Playwright for Workday | No single board exposes everything |
| People & email | Apollo.io (primary), CareerShift (CMU), Enrow / Hunter as backups | CareerShift has no public API |
| Database | PostgreSQL (likely Supabase) | Jobs, contacts, outreach history |
| Sync | Notion + Google Sheets | Existing tracking workflows |
| Scheduling (Phase B) | APScheduler | Scout 2–3× per week |

**Why not “Cursor-only” as the runtime?** Cursor is great for building and one-off runs, but we need persisted state, scheduled scouts, and a clear multi-agent graph — LangGraph handles that. Cursor stays the dev environment.

---

## Architecture

```mermaid
graph TD
    Input["Job URL / Job Description"] --> JobIngestion["Job Ingestion Agent"]
    JobIngestion --> CompanyIntel["Company Intelligence Agent"]
    CompanyIntel --> PeopleDiscovery["People Discovery Agent"]
    PeopleDiscovery --> PersonResearch["Person Research Agent"]
    PersonResearch --> ColdEmail["Cold Email / LinkedIn Writer"]
    JobIngestion --> ResumeOptimizer["Resume Optimizer Agent"]
    JobIngestion --> AppAssistant["Application Assistant Agent"]

    ColdEmail --> HumanReview["Human Review Gate"]
    HumanReview --> DraftStore["Draft Store DB"]

    JobScout["Job Scout Agent Phase B"] --> JobIngestion
    Scheduler["APScheduler"] --> JobScout

    DraftStore --> NotionSync["Notion Sync"]
    DraftStore --> SheetsSync["Google Sheets Sync"]
```

### Phase A — Agents

#### 1. Job Ingestion

**Input:** Job URL or pasted JD.

**Sources:**

| Platform | Approach |
|----------|----------|
| LinkedIn, Indeed, Glassdoor, ZipRecruiter | [`python-jobspy`](https://pypi.org/project/python-jobspy/) — Indeed most reliable; LinkedIn rate-limited (~100/IP) |
| Greenhouse | `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (no auth for read) |
| Lever | `GET https://api.lever.co/v0/postings/{client}` |
| Ashby | `GET https://api.ashbyhq.com/posting-api/job-board/{client}?includeCompensation=true` |
| Workday | Playwright per company portal (no unified API) |
| Handshake | MCP server or CMU EDU API (`edu-api.joinhandshake.com`) if available |

**Output fields:** title, company, department, location(s), full JD, skills, dates, apply URL, poster if known, company domain.

**Posting context:** Apollo org job postings API; LinkedIn HR/recruiter search cross-referenced with post date.

#### 2. Company Intelligence

Department mapping, org structure, multi-location handling (separate contact lists per site when needed).

**Sources:** Apollo org enrich + people search, company site / eng blog (LLM-assisted browse), Apollo news API.

#### 3. People Discovery

**Primary:** Apollo People Search (company domain + titles + seniority + location).

**Backup:** CareerShift via Playwright (no API — CMU login). Optional: NinjaPear, Enrow, Hunter.io.

**Priority order:**

1. Hiring managers / team leads in target department  
2. Recruiters tied to the role  
3. Engineers on the team (referrals)  
4. CMU alumni at the company  
5. General company recruiters  

#### 4. Person Research

Per contact: Apollo enrich, LinkedIn activity, publications/blogs (Tavily/SerpAPI), GitHub for technical roles, alumni overlap.

**Output:** research brief — background, talking points, tone cues, recommended angle.

#### 5. Cold Email / LinkedIn Writer

- No generic templates; one draft per person from the brief  
- Email under ~150 words; LinkedIn connect note under 300 characters  
- Draft-only → DB → Streamlit for review  

#### 6. Resume Optimizer

Parse PDF/DOCX, keyword gap vs JD, ATS formatting checks, match score.

#### 7. Application Assistant

Pull questions from Greenhouse/Lever APIs or Playwright on other forms; draft answers from resume + JD; human review before submit.

### Phase B — Database & scout

**Tables (PostgreSQL):** `jobs`, `companies`, `contacts`, `outreach`, `resumes`, `applications`.

**Scout:** 2–3×/week — JobSpy + ATS boards + Handshake; dedupe; relevance score; notify on strong matches. LangGraph checkpoints so runs can resume.

**Sync:** Notion + Google Sheets on a schedule (bidirectional where it makes sense).

### After-plan: company targeting (manual)

Not an agent deliverable. A shared doc with ~200–250 companies (Ambitious / Moderate / Safe), role types, hiring windows, ATS per company, and a timeline to May 2027. That list seeds the Phase B scout.

---

## Project layout (planned)

```
openrole/
├── pyproject.toml
├── .env.example
├── src/
│   ├── agents/
│   │   ├── job_ingestion.py
│   │   ├── company_intel.py
│   │   ├── people_discovery.py
│   │   ├── person_research.py
│   │   ├── email_writer.py
│   │   ├── resume_optimizer.py
│   │   ├── app_assistant.py
│   │   └── job_scout.py
│   ├── graph/
│   │   ├── main_graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── edges.py
│   ├── scrapers/
│   │   ├── workday.py
│   │   ├── careershift.py
│   │   └── ats_apis.py
│   ├── tools/
│   │   ├── apollo_client.py
│   │   ├── jobspy_client.py
│   │   ├── email_finder.py
│   │   └── web_search.py
│   ├── db/
│   │   ├── models.py
│   │   ├── sync_notion.py
│   │   └── sync_sheets.py
│   ├── ui/
│   │   ├── app.py
│   │   └── pages/
│   ├── config.py
│   └── scheduler.py
├── scripts/
│   ├── seed_companies.py
│   └── migrate_db.py
└── README.md
```

---

## Setup

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/) or pip.

```bash
git clone https://github.com/NisargaGondi/openrole.git
cd openrole
git checkout ngondi              # or: git checkout sbellad

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"

cp .env.example .env
# Edit .env — at minimum set GCP_PROJECT_ID for Gemini (or use ADC)

openrole-migrate                 # creates SQLite DB under data/
pytest                           # smoke tests

streamlit run src/openrole/ui/app.py
```

**Supabase / Postgres:** set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/openrole` in `.env`, then run `openrole-migrate` again.

**Vertex AI auth:** either set `GOOGLE_APPLICATION_CREDENTIALS` to a service account JSON, or run `gcloud auth application-default login` and set `GCP_PROJECT_ID` in `.env`.

---

## Configuration & costs

**Keys (local only):** OpenAI, Apollo, optional Enrow/Hunter, Supabase, Notion, Google Sheets. CMU tools (CareerShift, Handshake) use your own student session — not stored in the repo.

**Rough monthly cost** (shared project budget ~$50–150):

| Service | Est. |
|---------|------|
| Apollo.io Basic | ~$49 |
| OpenAI API | ~$30–60 |
| Enrow (optional backup) | ~$17 |
| Supabase | Free tier |
| Hosting (optional) | $0 local, or ~$5–10 on Railway/Render |

Data sources are still being evaluated — document new tools in a PR when you add one.

---

## Ethics & ToS

- Outreach is **draft-only** by design.  
- Prefer official APIs (e.g. Greenhouse job boards) over scraping where possible.  
- Respect platform terms; no credential sharing in git.  

---

## Risks

| Risk | Mitigation |
|------|------------|
| LinkedIn rate limits | Apollo for people; JobSpy + proxies; Indeed as job fallback |
| CareerShift has no API | Playwright; manual search + Apollo if automation breaks |
| Wrong contact data | Human verifies before send |
| Apollo credit cap | Track usage; Enrow/Hunter fallback |
| Workday varies by employer | Generic Playwright + LLM-assisted page parsing |

---

## License

TBD — likely MIT for code. Resumes, drafts, and contact lists stay with the contributors; don’t commit personal data to the repo.
