(function() {
  if (window.matchMedia && window.matchMedia('(hover: none)').matches) return;

  function boot() {
    var style = document.createElement('style');
    style.textContent = [
      'html, html * { cursor: none !important; }',
      '#cem-dot {',
      '  position: fixed; width: 6px; height: 6px;',
      '  background: #00C9B1; border-radius: 50%;',
      '  pointer-events: none; z-index: 2147483647;',
      '  transform: translate(-50%,-50%);',
      '  box-shadow: 0 0 8px #00C9B1, 0 0 16px rgba(0,201,177,0.35);',
      '  transition: width 0.15s, height 0.15s;',
      '  will-change: transform; top: 0; left: 0;',
      '}',
      '#cem-ring {',
      '  position: fixed; width: 32px; height: 32px;',
      '  border: 1.5px solid rgba(0,201,177,0.55);',
      '  border-radius: 50%;',
      '  pointer-events: none; z-index: 2147483646;',
      '  transform: translate(-50%,-50%);',
      '  transition: width 0.2s, height 0.2s, border-color 0.2s;',
      '  will-change: transform; top: 0; left: 0;',
      '}',
      '@keyframes cem-ring-pulse {',
      '  0%,100% { opacity: 0.55; }',
      '  50%      { opacity: 0.85; }',
      '}',
      '#cem-ring { animation: cem-ring-pulse 2.4s ease-in-out infinite; }'
    ].join('');
    document.head.appendChild(style);

    var dot = document.createElement('div');
    dot.id = 'cem-dot';
    document.body.appendChild(dot);

    var ring = document.createElement('div');
    ring.id = 'cem-ring';
    document.body.appendChild(ring);

    var mx = -200, my = -200;
    var rx = -200, ry = -200;

    function lerp(a, b, t) { return a + (b - a) * t; }

    function frame() {
      rx = lerp(rx, mx, 0.12);
      ry = lerp(ry, my, 0.12);
      dot.style.left = mx + 'px';
      dot.style.top  = my + 'px';
      ring.style.left = rx + 'px';
      ring.style.top  = ry + 'px';
      requestAnimationFrame(frame);
    }
    frame();

    document.addEventListener('mousemove', function(e) {
      mx = e.clientX;
      my = e.clientY;
    }, {passive: true});

    document.addEventListener('mouseleave', function() {
      dot.style.opacity = '0';
      ring.style.opacity = '0';
    });

    document.addEventListener('mouseenter', function() {
      dot.style.opacity = '1';
      ring.style.opacity = '1';
    });

    document.addEventListener('mouseover', function(e) {
      var el = e.target;
      var tag = el.tagName.toLowerCase();
      var isClickable = tag === 'a' || tag === 'button' || tag === 'input' ||
        el.getAttribute('onclick') || el.style.cursor === 'pointer' ||
        getComputedStyle(el).cursor === 'pointer';

      if (isClickable) {
        dot.style.width = '10px';
        dot.style.height = '10px';
        ring.style.width = '44px';
        ring.style.height = '44px';
        ring.style.borderColor = 'rgba(0,201,177,0.9)';
      } else {
        dot.style.width = '6px';
        dot.style.height = '6px';
        ring.style.width = '32px';
        ring.style.height = '32px';
        ring.style.borderColor = 'rgba(0,201,177,0.55)';
      }
    }, {passive: true});

    document.addEventListener('mousedown', function() {
      ring.style.width = '18px';
      ring.style.height = '18px';
      ring.style.borderColor = '#00C9B1';
    });

    document.addEventListener('mouseup', function() {
      ring.style.width = '32px';
      ring.style.height = '32px';
      ring.style.borderColor = 'rgba(0,201,177,0.55)';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
