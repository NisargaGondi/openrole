"""Light-theme interactive SVG background — cursor parallax + time drift."""

from __future__ import annotations

import streamlit.components.v1 as components

_COSMOS_HTML = """
<script>
(function () {
  const doc = window.parent.document;
  if (doc.getElementById("or-cosmos")) return;

  const css = doc.createElement("style");
  css.id = "or-cosmos-css";
  css.textContent = `
    #or-cosmos {
      position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
    }
    #or-cosmos svg { width: 100%; height: 100%; display: block; }
    #or-cursor-glow {
      position: fixed; width: 420px; height: 420px; border-radius: 50%;
      background: radial-gradient(circle, rgba(99,102,241,0.14) 0%, transparent 70%);
      transform: translate(-50%, -50%); pointer-events: none; z-index: 0;
      transition: opacity 0.35s ease; opacity: 0;
    }
    @keyframes or-float-a { 0%,100%{transform:translate(0,0)} 50%{transform:translate(24px,-18px)} }
    @keyframes or-float-b { 0%,100%{transform:translate(0,0)} 50%{transform:translate(-20px,16px)} }
    @keyframes or-float-c { 0%,100%{transform:translate(0,0) scale(1)} 50%{transform:translate(10px,8px) scale(1.04)} }
    @media (prefers-reduced-motion: reduce) {
      #or-cosmos .or-anim { animation: none !important; }
      #or-cursor-glow { display: none; }
    }
  `;
  doc.head.appendChild(css);

  const glow = doc.createElement("div");
  glow.id = "or-cursor-glow";
  doc.body.appendChild(glow);

  const layer = doc.createElement("div");
  layer.id = "or-cosmos";
  layer.innerHTML = `
    <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="og1" cx="20%" cy="15%" r="50%">
          <stop offset="0%" stop-color="#818cf8" stop-opacity="0.28"/>
          <stop offset="100%" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="og2" cx="85%" cy="70%" r="48%">
          <stop offset="0%" stop-color="#34d399" stop-opacity="0.22"/>
          <stop offset="100%" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="og3" cx="55%" cy="45%" r="40%">
          <stop offset="0%" stop-color="#f472b6" stop-opacity="0.12"/>
          <stop offset="100%" stop-opacity="0"/>
        </radialGradient>
        <filter id="og-blur"><feGaussianBlur stdDeviation="48"/></filter>
      </defs>
      <rect width="1440" height="900" fill="transparent"/>
      <g id="or-blob-a" class="or-anim" style="animation:or-float-a 26s ease-in-out infinite">
        <ellipse cx="280" cy="160" rx="320" ry="240" fill="url(#og1)" filter="url(#og-blur)"/>
      </g>
      <g id="or-blob-b" class="or-anim" style="animation:or-float-b 32s ease-in-out infinite">
        <ellipse cx="1120" cy="640" rx="300" ry="220" fill="url(#og2)" filter="url(#og-blur)"/>
      </g>
      <g id="or-blob-c" class="or-anim" style="animation:or-float-c 20s ease-in-out infinite">
        <ellipse cx="720" cy="420" rx="200" ry="180" fill="url(#og3)" filter="url(#og-blur)"/>
      </g>
    </svg>`;
  doc.body.insertBefore(layer, doc.body.firstChild);

  let mx = 0.5, my = 0.5, tx = 0.5, ty = 0.5;
  const blobs = [
    doc.getElementById("or-blob-a"),
    doc.getElementById("or-blob-b"),
    doc.getElementById("or-blob-c"),
  ];
  const speeds = [18, -14, 10];

  function onMove(e) {
    const w = window.parent.innerWidth || 1440;
    const h = window.parent.innerHeight || 900;
    tx = e.clientX / w;
    ty = e.clientY / h;
    glow.style.left = e.clientX + "px";
    glow.style.top = e.clientY + "px";
    glow.style.opacity = "1";
  }
  window.parent.addEventListener("mousemove", onMove, { passive: true });
  window.parent.addEventListener("mouseleave", () => { glow.style.opacity = "0"; });

  function tick() {
    mx += (tx - mx) * 0.06;
    my += (ty - my) * 0.06;
    blobs.forEach((el, i) => {
      if (!el) return;
      const dx = (mx - 0.5) * speeds[i];
      const dy = (my - 0.5) * speeds[i];
      el.style.transform = `translate(${dx}px, ${dy}px)`;
    });
    requestAnimationFrame(tick);
  }
  tick();
})();
</script>
"""


def render_cosmos_background() -> None:
    components.html(_COSMOS_HTML, height=0)
