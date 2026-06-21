"""Fixed interactive SVG background — mouse/touch parallax + time drift."""

from __future__ import annotations

import streamlit.components.v1 as components

# Injects aurora + parallax into the parent Streamlit document (iframe hack).
_BACKGROUND_HTML = """
<div id="or-bg-mount"></div>
<script>
(function () {
  const parentDoc = window.parent.document;
  if (parentDoc.getElementById("or-bg-layer")) return;

  const style = parentDoc.createElement("style");
  style.id = "or-bg-styles";
  style.textContent = `
    #or-bg-layer {
      position: fixed;
      inset: 0;
      z-index: 0;
      pointer-events: none;
      overflow: hidden;
    }
    #or-bg-layer svg { width: 100%; height: 100%; display: block; }
    #or-bg-layer .or-layer {
      transform-box: fill-box;
      transform-origin: center;
      will-change: transform;
    }
    section.main, [data-testid="stSidebar"] {
      position: relative;
      z-index: 1;
    }
    .stApp {
      background: #0a0a0f !important;
    }
    @keyframes or-drift-a {
      0%, 100% { transform: translate(0, 0); }
      50% { transform: translate(14px, -20px); }
    }
    @keyframes or-drift-b {
      0%, 100% { transform: translate(0, 0); }
      50% { transform: translate(-18px, 12px); }
    }
    @keyframes or-pulse {
      0%, 100% { opacity: 0.3; }
      50% { opacity: 0.5; }
    }
    @media (prefers-reduced-motion: reduce) {
      #or-bg-layer .or-anim { animation: none !important; }
    }
  `;
  parentDoc.head.appendChild(style);

  const layer = parentDoc.createElement("div");
  layer.id = "or-bg-layer";
  layer.setAttribute("aria-hidden", "true");
  layer.innerHTML = `
    <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="or-g1" cx="28%" cy="18%" r="55%">
          <stop offset="0%" stop-color="#1ed760" stop-opacity="0.2"/>
          <stop offset="100%" stop-color="#1ed760" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="or-g2" cx="80%" cy="75%" r="52%">
          <stop offset="0%" stop-color="#818cf8" stop-opacity="0.18"/>
          <stop offset="100%" stop-color="#818cf8" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="or-g3" cx="50%" cy="50%" r="45%">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.1"/>
          <stop offset="100%" stop-opacity="0"/>
        </radialGradient>
        <filter id="or-blur"><feGaussianBlur stdDeviation="52"/></filter>
      </defs>
      <rect width="1440" height="900" fill="#0a0a0f"/>
      <g class="or-layer or-anim" data-speed="0.05" style="animation:or-drift-a 24s ease-in-out infinite">
        <ellipse cx="300" cy="170" rx="300" ry="230" fill="url(#or-g1)" filter="url(#or-blur)"/>
      </g>
      <g class="or-layer or-anim" data-speed="-0.07" style="animation:or-drift-b 30s ease-in-out infinite">
        <ellipse cx="1150" cy="650" rx="340" ry="270" fill="url(#or-g2)" filter="url(#or-blur)"/>
      </g>
      <g class="or-layer or-anim" data-speed="0.03" style="animation:or-pulse 20s ease-in-out infinite">
        <ellipse cx="720" cy="430" rx="220" ry="220" fill="url(#or-g3)" filter="url(#or-blur)"/>
      </g>
      <g class="or-layer" data-speed="0.1" opacity="0.5">
        <circle cx="160" cy="710" r="3" fill="#1ed760"/>
        <circle cx="400" cy="110" r="2" fill="#c4b5fd"/>
        <circle cx="1000" cy="260" r="2.5" fill="#22d3ee"/>
        <circle cx="1300" cy="150" r="2" fill="#1ed760"/>
        <path d="M100 380 Q340 300 500 420 T860 360" fill="none" stroke="#1ed760" stroke-opacity="0.07" stroke-width="1"/>
      </g>
    </svg>`;
  parentDoc.body.prepend(layer);

  const layers = layer.querySelectorAll(".or-layer[data-speed]");
  let tx = 0, ty = 0, cx = 0, cy = 0, raf = null;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function move(clientX, clientY) {
    const w = window.parent.innerWidth || 1;
    const h = window.parent.innerHeight || 1;
    tx = (clientX / w - 0.5) * 2;
    ty = (clientY / h - 0.5) * 2;
    if (!raf) raf = window.parent.requestAnimationFrame(tick);
  }

  function tick() {
    cx += (tx - cx) * 0.07;
    cy += (ty - cy) * 0.07;
    layers.forEach((el) => {
      const s = parseFloat(el.getAttribute("data-speed") || "0");
      el.style.transform = "translate(" + (cx * s * 70) + "px," + (cy * s * 70) + "px)";
    });
    if (Math.abs(tx - cx) > 0.002 || Math.abs(ty - cy) > 0.002) {
      raf = window.parent.requestAnimationFrame(tick);
    } else raf = null;
  }

  if (!reduced) {
    window.parent.addEventListener("mousemove", (e) => move(e.clientX, e.clientY), { passive: true });
    window.parent.addEventListener("touchmove", (e) => {
      if (e.touches && e.touches[0]) move(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });
  }
})();
</script>
"""


def render_interactive_background() -> None:
    """Mount parallax aurora on the Streamlit parent page."""
    components.html(_BACKGROUND_HTML, height=0, scrolling=False)
