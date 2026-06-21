# People discovery — Tavily search queries

OpenRole does **not** use an LLM for Tavily people search. Each template below is sent directly to the [Tavily Search API](https://tavily.com) with `include_answer=true`. Results are parsed for `linkedin.com/in/*` URLs.

Implementation: `src/openrole/agents/tavily_people_discovery.py`

## Query passes (in order)

| Pass | Template | Example (Anthropic Safeguards) |
|------|----------|--------------------------------|
| **company_wide** | `{company} site:linkedin.com/in` | `Anthropic site:linkedin.com/in` |
| **department** | `"{dept terms}" "{company}" site:linkedin.com/in` | `"Safeguards Labs safeguards" "Anthropic" site:linkedin.com/in` |
| **department_location** | `"{dept}" "{company}" "{city}" site:linkedin.com/in` | `"safeguards" "Anthropic" "San Francisco" site:linkedin.com/in` |
| **role_title** | `"{company}" "{short title}" engineer site:linkedin.com/in` | `"Anthropic" "Research Engineer" engineer site:linkedin.com/in` |
| **alumni** | `"{company}" "{school}" site:linkedin.com/in` | `"Anthropic" "Carnegie Mellon" site:linkedin.com/in` |

## Search depth

- Each query runs **`basic`** first.
- If fewer than 2 LinkedIn profiles are parsed, the **same query** is retried with **`advanced`**.

## Company name normalization

Legal names from ingestion are shortened before search:

| Ingested | Tavily query uses |
|----------|-------------------|
| Amazon.com Services LLC | Amazon |
| Meta | Meta |
| Anthropic | Anthropic |
| D. E. Shaw Research | D. E. Shaw Research |
| Milwaukee Tool | Milwaukee Tool |

## Other sources (same pipeline)

| Source | Role | Email |
|--------|------|-------|
| **Tavily** | Primary discovery — LinkedIn URLs + titles | No |
| **Apollo** | Company-wide search, HMs, recruiters | Free plan: search only, no enrich |
| **CareerShift** | Dept + alumni search (search-only, no detail clicks) | Manual button later |
| **LLM email guess** | Pattern from any known `@company` email | Tagged **AI** |

## LLM prompts (separate from Tavily)

| Step | File | Purpose |
|------|------|---------|
| Job context | `agents/job_context.py` | Extract dept keywords + cities from JD |
| Contact relevance | `agents/contact_relevance.py` | Score/rank merged contacts |
| Email guess | `agents/email_guesser.py` | Infer email when none found |
