"""Fixed ambient SVG layer — time-animated + pointer-reactive (via Streamlit html component)."""

from __future__ import annotations

import streamlit.components.v1 as components

_AMBIENT_HTML = """
<!DOCTYPE html>
<html>
<head>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100%;
    height: 100%;
    overflow: hidden;
    background: transparent;
  }
  svg {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .orb {
    transform-origin: center;
    transition: transform 0.35s ease-out;
  }
  @keyframes drift-a {
    0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.55; }
    33% { transform: translate(28px, -18px) scale(1.06); opacity: 0.7; }
    66% { transform: translate(-16px, 22px) scale(0.96); opacity: 0.5; }
  }
  @keyframes drift-b {
    0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.45; }
    50% { transform: translate(-32px, -12px) scale(1.08); opacity: 0.62; }
  }
  @keyframes drift-c {
    0%, 100% { transform: translate(0, 0); opacity: 0.35; }
    40% { transform: translate(20px, 30px); opacity: 0.5; }
    80% { transform: translate(-24px, -8px); opacity: 0.38; }
  }
  @keyframes pulse-ring {
    0%, 100% { r: 120; opacity: 0.08; }
    50% { r: 140; opacity: 0.14; }
  }
  #orb-a { animation: drift-a 18s ease-in-out infinite; }
  #orb-b { animation: drift-b 24s ease-in-out infinite; }
  #orb-c { animation: drift-c 21s ease-in-out infinite; }
  #ring { animation: pulse-ring 8s ease-in-out infinite; }
  @media (prefers-reduced-motion: reduce) {
    .orb, #ring { animation: none !important; }
  }
</style>
</head>
<body>
<svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="g1" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#818cf8" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#818cf8" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="g2" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#34d399" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#34d399" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="g3" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#f472b6" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#f472b6" stop-opacity="0"/>
    </radialGradient>
    <filter id="blur"><feGaussianBlur stdDeviation="48"/></filter>
  </defs>
  <g filter="url(#blur)" id="layer">
    <circle id="orb-a" class="orb" cx="220" cy="180" r="200" fill="url(#g1)"/>
    <circle id="orb-b" class="orb" cx="1180" cy="320" r="240" fill="url(#g2)"/>
    <circle id="orb-c" class="orb" cx="680" cy="720" r="180" fill="url(#g3)"/>
    <circle id="ring" cx="720" cy="450" r="120" fill="none" stroke="#6366f1" stroke-width="1"/>
  </g>
</svg>
<script>
  const layer = document.getElementById('layer');
  const orbs = ['orb-a', 'orb-b', 'orb-c'].map(id => document.getElementById(id));
  let tx = 0, ty = 0, cx = 0, cy = 0;
  function tick() {
    cx += (tx - cx) * 0.06;
    cy += (ty - cy) * 0.06;
    orbs.forEach((el, i) => {
      if (!el) return;
      const f = (i + 1) * 14;
      el.style.transform = `translate(${cx * f}px, ${cy * f}px)`;
    });
    requestAnimationFrame(tick);
  }
  tick();
  function setTarget(x, y) {
    tx = (x / window.innerWidth - 0.5) * 2;
    ty = (y / window.innerHeight - 0.5) * 2;
  }
  window.addEventListener('mousemove', e => setTarget(e.clientX, e.clientY));
  window.addEventListener('touchmove', e => {
    if (e.touches[0]) setTarget(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });
</script>
</body>
</html>
"""


def render_ambient_background() -> None:
    """Mount pointer-reactive ambient layer (fixed, behind main content)."""
    components.html(_AMBIENT_HTML, height=0, scrolling=False)
