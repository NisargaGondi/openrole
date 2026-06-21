"""Signal network graph — You → Company → Contacts for Home."""

from __future__ import annotations

import json

import streamlit.components.v1 as components

from openrole.db.models import Job
from openrole.db.repository import list_contacts_for_job, list_outreach_drafts
from openrole.db.session import get_session_factory


def _node_state(job: Job, active_step: str) -> dict:
    factory = get_session_factory()
    contacts = []
    with factory() as session:
        if job.company_id:
            contacts = list_contacts_for_job(
                session, company_id=job.company_id, source_job_id=job.id
            )[:6]
        drafts = list_outreach_drafts(session, job_id=job.id, limit=5)

    researched = [c for c in contacts if c.research_brief]
    return {
        "you": "You",
        "company": (job.company.name if job.company else "Company")[:18],
        "title": job.title[:32],
        "score": (job.raw_payload or {}).get("scout", {}).get("relevance_score"),
        "contacts": [{"name": c.full_name.split()[0][:10], "id": c.id[:6]} for c in contacts],
        "researched": len(researched),
        "drafts": len(drafts),
        "active": active_step,
    }


def render_signal_network_graph(*, job: Job, active_step: str, height: int = 320) -> None:
    data = _node_state(job, active_step)
    payload = json.dumps(data).replace("\\", "\\\\").replace("'", "\\'")
    components.html(
        f"""
<div id="sg-root"></div>
<script>
(function() {{
  const data = JSON.parse('{payload}');
  const active = data.active;
  const stepLit = {{
    role: true,
    people: data.contacts.length > 0 || active === 'people',
    research: data.researched > 0 || active === 'research',
    outreach: data.drafts > 0 || active === 'outreach',
    apply: active === 'apply',
  }};
  const w = 520, h = 280;
  const cx = w/2, cy = h/2 + 10;
  let svg = `<svg width="100%" height="{height}" viewBox="0 0 ${{w}} ${{h}}" xmlns="http://www.w3.org/2000/svg">`;
  svg += `<defs><filter id="glow"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>`;

  function edge(x1,y1,x2,y2,lit) {{
    const c = lit ? '#f97316' : '#c7d2fe';
    const sw = lit ? 2.5 : 1.2;
    const dash = lit ? '' : 'stroke-dasharray="4 4"';
    svg += `<line x1="${{x1}}" y1="${{y1}}" x2="${{x2}}" y2="${{y2}}" stroke="${{c}}" stroke-width="${{sw}}" ${{dash}} opacity="${{lit?0.9:0.45}}">`;
    if (lit) svg += `<animate attributeName="stroke-opacity" values="0.5;1;0.5" dur="2s" repeatCount="indefinite"/>`;
    svg += `</line>`;
  }}
  function node(x,y,r,label,sub,lit,fill) {{
    const stroke = lit ? '#f97316' : '#6366f1';
    svg += `<circle cx="${{x}}" cy="${{y}}" r="${{r}}" fill="${{fill||'#fff'}}" stroke="${{stroke}}" stroke-width="${{lit?3:2}}" filter="${{lit?'url(#glow)':''}}">`;
    if (lit) svg += `<animate attributeName="r" values="${{r}};${{r+2}};${{r}}" dur="2.5s" repeatCount="indefinite"/>`;
    svg += `</circle>`;
    svg += `<text x="${{x}}" y="${{y+4}}" text-anchor="middle" font-size="11" font-weight="700" fill="#1e1b4b">${{label}}</text>`;
    if (sub) svg += `<text x="${{x}}" y="${{y+r+14}}" text-anchor="middle" font-size="9" fill="#64748b">${{sub}}</text>`;
  }}

  node(cx, cy+40, 22, 'You', '', true, '#eef2ff');
  node(cx, cy-30, 26, data.company, 'Company', stepLit.people || active==='role', '#fff');
  edge(cx, cy+18, cx, cy-4, stepLit.people || active==='role');

  const n = data.contacts.length;
  for (let i = 0; i < Math.max(n, 3); i++) {{
    const angle = Math.PI + (i - (Math.max(n,3)-1)/2) * 0.55;
    const x = cx + Math.cos(angle) * 130;
    const y = cy - 30 + Math.sin(angle) * 55;
    const lit = i < n && (stepLit.people || active==='people');
    const lbl = i < n ? data.contacts[i].name : '·';
    node(x, y, 16, lbl, i<n?'contact':'', lit && i<n, '#faf5ff');
    if (i < n) edge(cx, cy-30, x, y, lit);
  }}

  if (data.score) {{
    svg += `<text x="${{w-12}}" y="24" text-anchor="end" font-size="13" font-weight="800" fill="#6366f1">${{data.score}} match</text>`;
  }}
  svg += '</svg>';
  document.getElementById('sg-root').innerHTML = svg;
}})();
</script>
""",
        height=height,
    )
