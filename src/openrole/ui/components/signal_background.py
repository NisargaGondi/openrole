"""Signal theme — floating connection mesh + cursor glow."""

from __future__ import annotations

import streamlit.components.v1 as components

_SIGNAL_BG_HTML = """
<script>
(function () {
  const doc = window.parent.document;
  if (doc.getElementById("or-signal-bg")) return;

  const css = doc.createElement("style");
  css.id = "or-signal-bg-css";
  css.textContent = `
    #or-signal-bg {
      position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
    }
    #or-signal-bg svg { width: 100%; height: 100%; }
    #or-signal-glow {
      position: fixed; width: 380px; height: 380px; border-radius: 50%;
      background: radial-gradient(circle, rgba(99,102,241,0.12) 0%, rgba(249,115,22,0.04) 40%, transparent 70%);
      transform: translate(-50%, -50%); pointer-events: none; z-index: 0; opacity: 0;
      transition: opacity 0.3s;
    }
    @keyframes or-sig-pulse { 0%,100%{opacity:0.35} 50%{opacity:0.85} }
    @keyframes or-sig-flow { to { stroke-dashoffset: -40; } }
    .or-sig-edge { stroke-dasharray: 8 8; animation: or-sig-flow 3s linear infinite; }
  `;
  doc.head.appendChild(css);

  const glow = doc.createElement("div");
  glow.id = "or-signal-glow";
  doc.body.appendChild(glow);

  const wrap = doc.createElement("div");
  wrap.id = "or-signal-bg";
  wrap.innerHTML = `
    <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="sig-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.08"/>
          <stop offset="100%" stop-color="#f97316" stop-opacity="0.06"/>
        </linearGradient>
      </defs>
      <rect width="1440" height="900" fill="url(#sig-grad)"/>
      <g id="or-sig-lines" stroke="#6366f1" stroke-opacity="0.12" stroke-width="1" fill="none">
        <line class="or-sig-edge" x1="120" y1="200" x2="400" y2="350"/>
        <line class="or-sig-edge" x1="400" y1="350" x2="720" y2="280"/>
        <line class="or-sig-edge" x1="720" y1="280" x2="1100" y2="400"/>
        <line class="or-sig-edge" x1="200" y1="600" x2="550" y2="500"/>
        <line class="or-sig-edge" x1="550" y1="500" x2="900" y2="650"/>
        <line class="or-sig-edge" x1="900" y1="650" x2="1300" y2="550"/>
      </g>
      <circle cx="720" cy="450" r="3" fill="#6366f1" opacity="0.25">
        <animate attributeName="r" values="3;6;3" dur="4s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.25;0.5;0.25" dur="4s" repeatCount="indefinite"/>
      </circle>
    </svg>`;
  doc.body.insertBefore(wrap, doc.body.firstChild);

  window.parent.addEventListener("mousemove", (e) => {
    glow.style.left = e.clientX + "px";
    glow.style.top = e.clientY + "px";
    glow.style.opacity = "1";
  }, { passive: true });
  window.parent.addEventListener("mouseleave", () => { glow.style.opacity = "0"; });
})();
</script>
"""


def render_signal_background() -> None:
    components.html(_SIGNAL_BG_HTML, height=0)
