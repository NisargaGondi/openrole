"""Scout expanding signal graph — resume → sources → jobs."""

from __future__ import annotations

import streamlit.components.v1 as components


def render_scout_signal_graph(*, running: bool = False, height: int = 200) -> None:
    pulse = "true" if running else "false"
    components.html(
        f"""
<div id="scout-sg"></div>
<script>
(function() {{
  const running = {pulse};
  const w=480,h=180,cx=80,cy=h/2;
  let s = `<svg width="100%" height="{height}" viewBox="0 0 ${{w}} ${{h}}">`;
  const sources = [
    {{x:280,y:40,l:'Indeed'}},{{x:360,y:90,l:'LinkedIn'}},
    {{x:300,y:140,l:'Tavily'}},{{x:400,y:50,l:'ATS'}}
  ];
  s += `<circle cx="${{cx}}" cy="${{cy}}" r="28" fill="#eef2ff" stroke="#6366f1" stroke-width="2.5"/>`;
  s += `<text x="${{cx}}" y="${{cy+4}}" text-anchor="middle" font-size="10" font-weight="700" fill="#4338ca">Resume</text>`;
  sources.forEach((src,i) => {{
    s += `<line x1="${{cx+28}}" y1="${{cy}}" x2="${{src.x-18}}" y2="${{src.y}}" stroke="#c7d2fe" stroke-width="1.5" stroke-dasharray="5 4"/>`;
    if (running) s += `<circle r="4" fill="#f97316"><animateMotion dur="${{1.5+i*0.3}}s" repeatCount="indefinite" path="M${{cx+28}},${{cy}} L${{src.x-18}},${{src.y}}"/></circle>`;
    s += `<circle cx="${{src.x}}" cy="${{src.y}}" r="20" fill="#fff" stroke="#6366f1" stroke-width="2"/>`;
    s += `<text x="${{src.x}}" y="${{src.y+4}}" text-anchor="middle" font-size="9" font-weight="600" fill="#1e1b4b">${{src.l}}</text>`;
    s += `<circle cx="${{src.x+32}}" cy="${{src.y-8}}" r="8" fill="#faf5ff" stroke="#f97316" stroke-width="1.5"/>`;
    s += `<text x="${{src.x+32}}" y="${{src.y-5}}" text-anchor="middle" font-size="7" fill="#f97316">job</text>`;
  }});
  if (running) {{
    s += `<circle cx="${{cx}}" cy="${{cy}}" r="35" fill="none" stroke="#f97316" stroke-width="1" opacity="0.5"><animate attributeName="r" values="35;55;35" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite"/></circle>`;
  }}
  s += '</svg>';
  document.getElementById('scout-sg').innerHTML = s;
}})();
</script>
""",
        height=height,
    )
