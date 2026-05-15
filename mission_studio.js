(function () {
  const DEFAULT_CONFIG = {
    accent: '#00ffcc',
    secondary: '#ff6600',
    watermark: 'CEMTrading888',
    logoText: 'CEM★TRADING★888',
    brandText: 'BUILD YOUR EDGE.',
    assetCountKey: 'cem_design_lab_assets',
    supabaseUrl: 'https://gsnbqohzprencuzkirui.supabase.co',
    supabaseKey:
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdzbmJxb2h6cHJlbmN1emtpcnVpIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQyOTYzMjMsImV4cCI6MjA4OTg3MjMyM30.YsMOVJyz4XYWOT0e_lQjNHDArNLiEdF38RXZuoR1iq8',
    createdBy: '',
  };

  const UNDRAW_MANIFEST_URL = 'https://cdn.jsdelivr.net/npm/undraw-svg@latest/illustrations.json';
  const SVG_REPO_SEARCH_URL = 'https://www.svgrepo.com/api/search';
  const UNDRAW_TINT_TOKENS = ['#6c63ff', '#ff6584', '#6f67ff', '#4f46e5'];
  const CEMBOT_DRAWER_CLOSED = 'translateY(calc(100% - 48px))';
  const CEMBOT_ACCENT = '#00ffcc';
  const UNDRAW_FALLBACK = [
    { title: 'Finance', slug: 'finance', keywords: ['finance', 'money', 'business'] },
    { title: 'Personal Finance', slug: 'personal-finance', keywords: ['budget', 'money', 'finance'] },
    { title: 'Growth Analytics', slug: 'growth-analytics', keywords: ['growth', 'analytics', 'chart'] },
    { title: 'Growth Chart', slug: 'growth-chart', keywords: ['growth', 'chart', 'finance'] },
    { title: 'Analytics Setup', slug: 'analytics-setup', keywords: ['analytics', 'dashboard', 'data'] },
    { title: 'Dashboard', slug: 'dashboard', keywords: ['dashboard', 'report', 'ui'] },
    { title: 'Teamwork', slug: 'teamwork', keywords: ['team', 'collaboration'] },
    { title: 'Success', slug: 'success', keywords: ['success', 'win', 'goal'] },
    { title: 'Goals', slug: 'goals', keywords: ['goal', 'target', 'success'] },
    { title: 'Business Call', slug: 'business-call', keywords: ['business', 'meeting', 'team'] },
  ];
  const SVG_REPO_FALLBACK = [
    {
      title: 'Bar Chart',
      url: 'https://cdn.svgrepo.com/show/90050/bar-chart.svg',
      keywords: ['chart', 'bar', 'analytics', 'finance'],
    },
    {
      title: 'Arrow Up',
      url: 'https://cdn.svgrepo.com/show/327620/arrow-up.svg',
      keywords: ['arrow', 'up', 'growth', 'trend'],
    },
    {
      title: 'Money Bag',
      url: 'https://cdn.svgrepo.com/show/204745/money-bag-money.svg',
      keywords: ['money', 'bag', 'cash', 'finance'],
    },
    {
      title: 'Analytics Graph',
      url: 'https://cdn.svgrepo.com/show/379930/analytics-graph-chart.svg',
      keywords: ['analytics', 'graph', 'chart', 'data'],
    },
    {
      title: 'Line Graph',
      url: 'https://cdn.svgrepo.com/show/283613/line-chart-line-graph.svg',
      keywords: ['line', 'graph', 'chart', 'trend'],
    },
    {
      title: 'Approved Check',
      url: 'https://cdn.svgrepo.com/show/422131/approved-check-mark.svg',
      keywords: ['check', 'approved', 'success', 'done'],
    },
    {
      title: 'Star',
      url: 'https://cdn.svgrepo.com/show/90882/star.svg',
      keywords: ['star', 'favorite', 'rating'],
    },
    {
      title: 'Trophy',
      url: 'https://cdn.svgrepo.com/show/213608/trophy-sports-and-competition.svg',
      keywords: ['trophy', 'winner', 'success', 'award'],
    },
  ];
  const DESIGN_LAB_FONTS = Object.freeze([
    'Share Tech Mono',
    'Barlow',
    'Barlow Condensed',
    'Arial',
    'Georgia',
  ]);
  const DESIGN_LAB_TEMPLATES = Object.freeze({
    bot_logo: {
      background: '#05070d',
      build() {
        return [
          {
            kind: 'circle',
            label: 'Neon Ring',
            props: {
              left: 140,
              top: 120,
              radius: 92,
              fill: 'transparent',
              stroke: '#00ffcc',
              strokeWidth: 6,
              opacity: 0.88,
            },
          },
          {
            kind: 'rect',
            label: 'Core Panel',
            props: {
              left: 188,
              top: 168,
              width: 184,
              height: 96,
              rx: 14,
              ry: 14,
              fill: '#0d1f1a',
              stroke: '#ff6600',
              strokeWidth: 2,
            },
          },
          {
            kind: 'text',
            label: 'Logo Title',
            props: {
              left: 220,
              top: 182,
              text: 'CEMBOT',
              fontSize: 34,
              fill: '#00ffcc',
              fontFamily: 'Barlow Condensed',
              fontWeight: 'bold',
              charSpacing: 140,
            },
          },
          {
            kind: 'text',
            label: 'Logo Subtitle',
            props: {
              left: 232,
              top: 226,
              text: 'BUILD YOUR EDGE.',
              fontSize: 14,
              fill: '#ffffff',
              fontFamily: 'Share Tech Mono',
              charSpacing: 120,
            },
          },
        ];
      },
    },
    social_post: {
      background: '#060810',
      build() {
        return [
          {
            kind: 'rect',
            label: 'Hero Card',
            props: {
              left: 72,
              top: 62,
              width: 656,
              height: 386,
              rx: 18,
              ry: 18,
              fill: '#0d141f',
              stroke: '#00ffcc',
              strokeWidth: 2,
            },
          },
          {
            kind: 'text',
            label: 'Hook Headline',
            props: {
              left: 110,
              top: 118,
              text: 'THE MARKET\nTRICKS THE BEST.',
              fontSize: 48,
              fill: '#00ffcc',
              fontFamily: 'Barlow Condensed',
              fontWeight: 'bold',
              lineHeight: 0.92,
            },
          },
          {
            kind: 'text',
            label: 'Body Copy',
            props: {
              left: 114,
              top: 244,
              width: 420,
              text: 'Run the backtest.\nSee the edge.\nDeploy with conviction.',
              fontSize: 24,
              fill: '#ffffff',
              fontFamily: 'Barlow',
              lineHeight: 1.2,
            },
          },
          {
            kind: 'rect',
            label: 'CTA',
            props: {
              left: 112,
              top: 362,
              width: 228,
              height: 54,
              rx: 14,
              ry: 14,
              fill: '#ff6b35',
            },
          },
          {
            kind: 'text',
            label: 'CTA Label',
            props: {
              left: 146,
              top: 378,
              text: 'ENTER THE LAB',
              fontSize: 20,
              fill: '#05070d',
              fontFamily: 'Share Tech Mono',
              fontWeight: 'bold',
              charSpacing: 90,
            },
          },
        ];
      },
    },
    banner: {
      background: '#050505',
      build() {
        return [
          {
            kind: 'rect',
            label: 'Banner Frame',
            props: {
              left: 42,
              top: 104,
              width: 716,
              height: 236,
              rx: 16,
              ry: 16,
              fill: '#101822',
              stroke: '#ff6600',
              strokeWidth: 2,
            },
          },
          {
            kind: 'line',
            label: 'Accent Line',
            props: {
              points: [78, 148, 726, 148],
              stroke: '#00ffcc',
              strokeWidth: 4,
            },
          },
          {
            kind: 'text',
            label: 'Banner Title',
            props: {
              left: 76,
              top: 176,
              text: 'ALGORITHMIC TRADING.\nHUMAN EDGE.',
              fontSize: 44,
              fill: '#ffffff',
              fontFamily: 'Barlow Condensed',
              fontWeight: 'bold',
              lineHeight: 0.92,
            },
          },
          {
            kind: 'text',
            label: 'Banner Tag',
            props: {
              left: 486,
              top: 262,
              text: 'CEMTRADING888',
              fontSize: 20,
              fill: '#00ffcc',
              fontFamily: 'Share Tech Mono',
              charSpacing: 120,
            },
          },
        ];
      },
    },
  });
  const DESIGN_LAB_STYLE_TAG_ID = 'cem-design-lab-runtime-styles';

  const state = {
    config: { ...DEFAULT_CONFIG },
    fabric: null,
    renderer: null,
    scene: null,
    camera: null,
    animId: null,
    objects: [],
    primaryLight: null,
    secondaryLight: null,
    grid: null,
    mouseDown: false,
    lastMouse: { x: 0, y: 0 },
    phi: Math.PI / 4,
    theta: Math.PI / 6,
    radius: 8,
    mode: '2d',
    assetTab: 'ai',
    librarySource: 'undraw',
    wireframe: false,
    resizeBound: false,
    undrawManifest: null,
    undrawTintCache: {},
    cembotOpen: false,
    cembotHistory: [],
    cembotHintTimer: null,
    cembotPending: false,
    cembotWelcomed: false,
    cembotVoiceMode: false,
    cembotListening: false,
    cembotSpeaking: false,
    cembotRecognition: null,
    cembotQueuedMessages: [],
    cembotVoiceNoticeShown: false,
    cembotVoiceTimer: null,
    history: [],
    historyIndex: -1,
    historyLocked: false,
    toolBindingsReady: false,
    keyboardBound: false,
    canvasZoom: 1,
    runtimeStylesReady: false,
  };

  function hexToNumber(value, fallback) {
    if (!value) return fallback;
    return parseInt(String(value).replace('#', '0x'), 16);
  }

  function hasSavedCEMProfile() {
    try {
      const tier = String(
        localStorage.getItem('cem_user_tier') ||
        localStorage.getItem('cem_trader_tier') ||
        ''
      ).trim();
      if (tier) return true;
      const rawProfile = localStorage.getItem('cem_user_profile');
      if (!rawProfile) return false;
      const parsed = JSON.parse(rawProfile);
      return !!(parsed && typeof parsed === 'object');
    } catch (err) {
      return false;
    }
  }

  function recordStudioEvent(type, payload) {
    const assetTypes = new Set(['generate', 'image-added', 'export', 'screenshot']);
    if (assetTypes.has(type)) {
      const key = state.config.assetCountKey;
      const count = Number(localStorage.getItem(key) || '0') + 1;
      localStorage.setItem(key, String(count));
    }
    if (typeof window.onMissionStudioEvent === 'function') {
      try {
        window.onMissionStudioEvent(type, payload || {});
      } catch (err) {
        console.error(err);
      }
    }
  }

  function applyStudioAuthLinks() {
    const isVisible = hasSavedCEMProfile();
    document.querySelectorAll('[data-auth-only]').forEach((el) => {
      el.style.display = isVisible ? (el.dataset.display || 'flex') : 'none';
    });
  }

  function getEl(id) {
    return document.getElementById(id);
  }

  function get2DCanvasElement() {
    return getEl('dl-canvas');
  }

  function get3DCanvasElement() {
    return getEl('dl-3d-canvas');
  }

  function setStatus(message, isError) {
    const el = getEl('dl-status');
    if (!el) return;
    el.textContent = message || '';
    el.style.color = isError ? '#ff3333' : '#888';
  }

  function clearGalleryPlaceholder() {
    const gallery = getEl('dl-gallery');
    if (!gallery) return;
    const empty = gallery.querySelector('[data-empty]');
    if (empty) gallery.innerHTML = '';
  }

  function addGalleryEmptyState(copy) {
    const gallery = getEl('dl-gallery');
    if (!gallery) return;
    gallery.innerHTML = `<div data-empty style="color:#444; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">${copy}</div>`;
  }

  function isProbablySvgUrl(url) {
    return /^data:image\/svg\+xml/i.test(String(url || '')) || /\.svg(?:$|\?)/i.test(String(url || ''));
  }

  function svgToDataUrl(svg) {
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, (char) => {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      }[char];
    });
  }

  function expandHex(value) {
    const hex = String(value || '').trim();
    if (/^#[0-9a-f]{3}$/i.test(hex)) {
      return `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`.toLowerCase();
    }
    return /^#[0-9a-f]{6}$/i.test(hex) ? hex.toLowerCase() : '';
  }

  function toHexColor(value, fallback) {
    const direct = expandHex(value);
    if (direct) return direct;
    const rgb = String(value || '')
      .trim()
      .match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
    if (rgb) {
      const [, r, g, b] = rgb.map((part, index) => (index ? Math.max(0, Math.min(255, Number(part) || 0)) : part));
      return `#${[r, g, b].map((part) => part.toString(16).padStart(2, '0')).join('')}`;
    }
    return expandHex(fallback) || '#00ffcc';
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function isTextObject(obj) {
    return !!obj && ['text', 'i-text', 'textbox'].includes(String(obj.type || '').toLowerCase());
  }

  function isGroupObject(obj) {
    return !!obj && typeof obj.getObjects === 'function';
  }

  function getActiveCanvasObject() {
    return state.fabric ? state.fabric.getActiveObject() : null;
  }

  function getNonWatermarkObjects() {
    return state.fabric ? state.fabric.getObjects().filter((obj) => obj && !obj.__cemWatermark) : [];
  }

  function getObjectDisplayName(obj, index) {
    if (!obj) return 'No active selection';
    return (
      String(obj.__cemLabel || '').trim() ||
      (isTextObject(obj) ? `Text ${index + 1}` : `${String(obj.type || 'Layer').replace(/(^|-)(\w)/g, (_, sep, chr) => `${sep ? ' ' : ''}${chr.toUpperCase()}`)} ${index + 1}`)
    );
  }

  function forEachStylableObject(obj, handler) {
    if (!obj || typeof handler !== 'function') return;
    if (obj.type === 'activeSelection' && typeof obj.forEachObject === 'function') {
      obj.forEachObject((item) => handler(item));
      return;
    }
    if (isGroupObject(obj) && !isTextObject(obj) && Array.isArray(obj._objects)) {
      obj._objects.forEach((item) => handler(item));
      return;
    }
    handler(obj);
  }

  function ensureRuntimeStyles() {
    if (state.runtimeStylesReady || typeof document === 'undefined') return;
    if (document.getElementById(DESIGN_LAB_STYLE_TAG_ID)) {
      state.runtimeStylesReady = true;
      return;
    }
    const style = document.createElement('style');
    style.id = DESIGN_LAB_STYLE_TAG_ID;
    style.textContent = `
      @keyframes dl-mic-pulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(0, 255, 204, 0.28), 0 0 12px rgba(0, 255, 204, 0.22); }
        50% { box-shadow: 0 0 0 8px rgba(0, 255, 204, 0.06), 0 0 22px rgba(0, 255, 204, 0.48); }
      }
      #dl-cembot-mic.dl-mic-live {
        color: #05070d !important;
        background: #00ffcc !important;
        border-color: #00ffcc !important;
        animation: dl-mic-pulse 1.2s ease-in-out infinite;
      }
      .dl-layer-row {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 8px;
        padding: 8px 10px;
        border: 1px solid #1a1a1a;
        border-radius: 8px;
        background: #0d0d0d;
      }
      .dl-layer-row.active {
        border-color: ${state.config.accent};
        box-shadow: 0 0 0 1px ${state.config.accent}33;
      }
      .dl-layer-meta {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .dl-layer-name {
        color: #f4f7fb;
        font-size: 11px;
      }
      .dl-layer-type {
        color: #666;
        font-size: 9px;
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .dl-layer-actions {
        display: flex;
        gap: 4px;
        align-items: center;
      }
      .dl-icon-btn {
        min-width: 28px;
        height: 28px;
        padding: 0 8px;
        border-radius: 6px;
        border: 1px solid #333;
        background: #111;
        color: #ccc;
        cursor: pointer;
        font-size: 11px;
      }
      .dl-icon-btn:hover {
        border-color: ${state.config.accent};
        color: ${state.config.accent};
      }
      .dl-template-btn.is-active,
      .dl-font-btn.is-active {
        border-color: ${state.config.accent};
        color: ${state.config.accent};
        background: ${state.config.accent}22;
      }
    `;
    document.head.appendChild(style);
    state.runtimeStylesReady = true;
  }

  function resolveCreatedBy() {
    if (state.config.createdBy) return String(state.config.createdBy).trim().toLowerCase();
    const path = String(window.location.pathname || '').toLowerCase();
    if (path.includes('kayla')) return 'kayla';
    if (path.includes('user-profile')) {
      try {
        const user = JSON.parse(localStorage.getItem('cem_user') || 'null');
        return String(user?.username || user?.displayName || 'explorer').trim().toLowerCase();
      } catch (err) {
        return 'explorer';
      }
    }
    return 'chandler';
  }

  function resolveSupabaseAuth() {
    const key =
      window.SUPABASE_ANON_KEY ||
      window.SUPABASE_PUBLISHABLE_KEY ||
      window.SUPABASE_KEY ||
      state.config.supabaseKey ||
      '';
    const url = window.SUPABASE_URL || state.config.supabaseUrl || '';
    return { key, url };
  }

  function setLibraryStatus(message, isError) {
    const status = getEl('dl-lib-status');
    if (!status) return;
    status.textContent = message || '';
    status.style.color = isError ? '#ff3333' : '#666';
  }

  function updateAssetTabButtons(tab) {
    ['ai', 'library', 'mine'].forEach((name) => {
      const btn = getEl(`dltab-${name}`);
      if (!btn) return;
      const active = name === tab;
      btn.classList.toggle('active', active);
      btn.style.color = active ? state.config.accent : '#666';
      btn.style.borderBottomColor = active ? state.config.accent : 'transparent';
    });
  }

  function updateLibrarySourceButtons(source) {
    ['undraw', 'svgrepo'].forEach((name) => {
      const btn = getEl(`dlsrc-${name}`);
      if (!btn) return;
      const active = name === source;
      btn.classList.toggle('dl-src-active', active);
      btn.style.color = active ? state.config.accent : '#ccc';
      btn.style.borderColor = active ? state.config.accent : '#333';
      btn.style.background = active ? `${state.config.accent}22` : '#111';
    });
    const colorRow = getEl('dl-undraw-color-row');
    if (colorRow) colorRow.style.display = source === 'undraw' ? 'flex' : 'none';
  }

  function ensureCembotMicButton() {
    const existing = getEl('dl-cembot-mic');
    if (existing) return existing;
    const send = getEl('dl-cembot-send');
    if (!send || !send.parentElement) return null;
    const mic = document.createElement('button');
    mic.id = 'dl-cembot-mic';
    mic.type = 'button';
    mic.textContent = '🎙️';
    mic.title = 'Toggle voice conversation';
    mic.style.cssText =
      'background:#111;color:#ccc;border:1px solid #333;padding:8px 12px;border-radius:4px;cursor:pointer;font-family:inherit;';
    mic.onclick = () => {
      if (typeof window.dlCembotToggleVoice === 'function') window.dlCembotToggleVoice();
    };
    send.parentElement.insertBefore(mic, send);
    return mic;
  }

  function getCembotDrawerElements() {
    return {
      drawer: getEl('dl-cembot-drawer'),
      messages: getEl('dl-cembot-messages'),
      input: getEl('dl-cembot-input'),
      send: getEl('dl-cembot-send'),
      mic: getEl('dl-cembot-mic'),
      chevron: getEl('dl-cembot-chevron'),
      orb: getEl('dl-cembot-orb'),
    };
  }

  function syncCembotVoiceUi() {
    const mic = ensureCembotMicButton();
    if (!mic) return;
    const active = !!state.cembotVoiceMode;
    mic.classList.toggle('dl-mic-live', active);
    mic.style.borderColor = active ? state.config.accent : '#333';
    mic.style.color = active ? '#05070d' : '#ccc';
    mic.style.background = active ? state.config.accent : '#111';
    mic.setAttribute('aria-pressed', active ? 'true' : 'false');
    mic.title = active ? 'Stop voice conversation' : 'Start voice conversation';
  }

  function syncCembotDrawerUi() {
    const { drawer, chevron } = getCembotDrawerElements();
    if (!drawer || !chevron) return;
    drawer.style.transform = state.cembotOpen ? 'translateY(0)' : CEMBOT_DRAWER_CLOSED;
    chevron.textContent = state.cembotOpen ? '▼' : '▲';
    syncCembotVoiceUi();
  }

  function scrollCembotMessages() {
    const { messages } = getCembotDrawerElements();
    if (messages) messages.scrollTop = messages.scrollHeight;
  }

  function initAssetPanels() {
    ensureRuntimeStyles();
    ensureCembotMicButton();
    updateAssetTabButtons(state.assetTab || 'ai');
    updateLibrarySourceButtons(state.librarySource || 'undraw');
    ['ai', 'library', 'mine'].forEach((name) => {
      const panel = getEl(`dlpanel-${name}`);
      if (!panel) return;
      panel.style.display = name === (state.assetTab || 'ai') ? 'flex' : 'none';
    });
    syncCembotDrawerUi();
  }

  function createCardShell() {
    const card = document.createElement('div');
    card.style.cssText =
      'cursor:pointer; border:1px solid #1a1a1a; border-radius:4px; overflow:hidden; background:#0d0d0d; padding:8px; display:flex; flex-direction:column; align-items:center; gap:4px; transition:border-color 0.2s;';
    card.onmouseover = () => {
      card.style.borderColor = state.config.accent;
    };
    card.onmouseout = () => {
      card.style.borderColor = '#1a1a1a';
    };
    return card;
  }

  function createAssetPreview(url, height) {
    const img = document.createElement('img');
    img.src = url;
    img.loading = 'lazy';
    img.style.cssText = `width:100%; height:${height || 80}px; object-fit:contain;`;
    return img;
  }

  function makeAssetDraggable(card, payload) {
    if (!card || !payload?.url) return;
    card.draggable = true;
    card.addEventListener('dragstart', (event) => {
      if (!event.dataTransfer) return;
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData('text/cem-asset', JSON.stringify(payload));
    });
  }

  async function addRasterToCanvas(url, width, position, label) {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric || !window.fabric) return false;
    return new Promise((resolve) => {
      fabric.Image.fromURL(
        url,
        (img) => {
          if (!img) {
            resolve(false);
            return;
          }
          img.scaleToWidth(width || 240);
          img.set({
            left: position?.x || 100,
            top: position?.y || 100,
          });
          addObjectToCanvas(img, label || 'Image');
          resolve(true);
        },
        { crossOrigin: 'anonymous' }
      );
    });
  }

  async function addSvgToCanvasInternal(url, width, position, label) {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric || !window.fabric) return false;
    return new Promise((resolve) => {
      fabric.loadSVGFromURL(
        url,
        async (objects, options) => {
          if (!objects || !objects.length) {
            const added = await addRasterToCanvas(url, width || 220, position, label);
            resolve(added);
            return;
          }
          const group = fabric.util.groupSVGElements(objects, options);
          group.scaleToWidth(width || 220);
          group.set({ left: position?.x || 100, top: position?.y || 100 });
          addObjectToCanvas(group, label || 'SVG Asset');
          resolve(true);
        },
        null,
        { crossOrigin: 'anonymous' }
      );
    });
  }

  async function addAnyAssetToCanvas(url, width, position, label) {
    if (isProbablySvgUrl(url)) return addSvgToCanvasInternal(url, width, position, label);
    return addRasterToCanvas(url, width, position, label);
  }

  async function fetchUndrawManifest() {
    if (Array.isArray(state.undrawManifest) && state.undrawManifest.length) return state.undrawManifest;
    const res = await fetch(UNDRAW_MANIFEST_URL);
    if (!res.ok) throw new Error(`unDraw manifest unavailable (${res.status})`);
    const data = await res.json();
    state.undrawManifest = Array.isArray(data) ? data : [];
    return state.undrawManifest;
  }

  function tintUndrawSvg(svgText, color) {
    let next = String(svgText || '');
    UNDRAW_TINT_TOKENS.forEach((token) => {
      next = next.replace(new RegExp(token, 'ig'), color);
    });
    return next;
  }

  async function getTintedUndrawDataUrl(item, color) {
    const sourceUrl = item.media || `https://cdn.jsdelivr.net/npm/undraw-svg@latest/svgs/${item.slug}.svg`;
    const cacheKey = `${sourceUrl}|${color}`;
    if (state.undrawTintCache[cacheKey]) return state.undrawTintCache[cacheKey];
    const res = await fetch(sourceUrl);
    if (!res.ok) throw new Error(`Illustration unavailable (${res.status})`);
    const svgText = await res.text();
    const tinted = tintUndrawSvg(svgText, color);
    const dataUrl = svgToDataUrl(tinted);
    state.undrawTintCache[cacheKey] = dataUrl;
    return dataUrl;
  }

  function normalizeSvgRepoItem(raw) {
    if (!raw) return null;
    const title = String(raw.title || raw.name || 'Icon').trim();
    const rawUrl = String(raw.svg_url || raw.image_url || raw.url || raw.href || '').trim();
    let url = rawUrl;
    if (!url && raw.id && raw.slug) {
      url = `https://cdn.svgrepo.com/show/${raw.id}/${raw.slug}.svg`;
    } else if (/\/svg\/\d+\//.test(url)) {
      url = url.replace('://www.svgrepo.com/svg/', '://cdn.svgrepo.com/show/') + '.svg';
    } else if (url.startsWith('/svg/')) {
      url = `https://cdn.svgrepo.com/show/${url.replace('/svg/', '')}.svg`;
    }
    if (!url) return null;
    return { title, url };
  }

  function renderAssetCards(root, items, emptyCopy, buildCard) {
    if (!root) return;
    root.innerHTML = '';
    if (!items.length) {
      root.innerHTML = `<div style="color:#444; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">${emptyCopy}</div>`;
      return;
    }
    items.forEach((item) => {
      const card = buildCard(item);
      if (card) root.appendChild(card);
    });
  }

  async function saveAssetRecord(record) {
    const { key, url } = resolveSupabaseAuth();
    if (!key || !url) return false;
    try {
      const res = await fetch(`${url}/rest/v1/cem_assets`, {
        method: 'POST',
        headers: {
          apikey: key,
          Authorization: `Bearer ${key}`,
          'Content-Type': 'application/json',
          Prefer: 'return=minimal',
        },
        body: JSON.stringify({
          created_by: resolveCreatedBy(),
          asset_type: record.asset_type || 'generated_image',
          prompt: record.prompt || '',
          model_used: record.model_used || '',
          url: record.url || '',
          filename: record.filename || '',
          tags: Array.isArray(record.tags) ? record.tags : [],
          metadata: record.metadata || {},
        }),
      });
      return res.ok;
    } catch (err) {
      console.error(err);
      return false;
    }
  }

  function ensureWatermark() {
    if (!state.fabric || !window.fabric) return;
    const existing = state.fabric.getObjects().find((obj) => obj && obj.__cemWatermark);
    if (existing) return;
    const wm = new fabric.Text(state.config.watermark, {
      left: 10,
      top: 10,
      fontSize: 11,
      fill: `${state.config.accent}33`,
      selectable: false,
      evented: false,
      hoverCursor: 'default',
      fontFamily: 'Courier New',
    });
    wm.__cemWatermark = true;
    state.fabric.add(wm);
    state.fabric.sendToBack(wm);
  }

  function decorateCanvasObject(obj, label) {
    if (!obj) return null;
    obj.__cemLabel = String(label || obj.__cemLabel || '').trim();
    if (!obj.__cemWatermark) {
      obj.set({
        transparentCorners: false,
        borderColor: state.config.accent,
        cornerColor: state.config.accent,
        cornerStrokeColor: '#05070d',
        padding: 5,
      });
    }
    return obj;
  }

  function addObjectToCanvas(obj, label, options) {
    if (!obj || !state.fabric) return null;
    decorateCanvasObject(obj, label);
    if (options?.position) {
      obj.set({
        left: options.position.x,
        top: options.position.y,
      });
    }
    state.fabric.add(obj);
    if (!obj.__cemWatermark && options?.select !== false) state.fabric.setActiveObject(obj);
    state.fabric.renderAll();
    return obj;
  }

  function captureCanvasSnapshot() {
    if (!state.fabric) return '';
    return JSON.stringify(
      state.fabric.toDatalessJSON([
        '__cemWatermark',
        '__cemLabel',
        'visible',
        'selectable',
        'evented',
        'fontFamily',
        'fontWeight',
        'fontStyle',
      ])
    );
  }

  function syncUndoRedoButtons() {
    const undo = getEl('dl-undo');
    const redo = getEl('dl-redo');
    if (undo) undo.disabled = state.historyIndex <= 0;
    if (redo) redo.disabled = state.historyIndex >= state.history.length - 1;
  }

  function updateZoomLabel() {
    const label = getEl('dl-zoom-label');
    if (label) label.textContent = `${Math.round((state.canvasZoom || 1) * 100)}%`;
  }

  function syncTextStyleButtons(obj) {
    const bold = getEl('dl-text-bold');
    const italic = getEl('dl-text-italic');
    const activeText = isTextObject(obj) ? obj : null;
    if (bold) bold.classList.toggle('is-active', !!activeText && String(activeText.fontWeight || '').toLowerCase() === 'bold');
    if (italic) italic.classList.toggle('is-active', !!activeText && String(activeText.fontStyle || '').toLowerCase() === 'italic');
  }

  function syncToolControls() {
    const obj = getActiveCanvasObject();
    const fontSelect = getEl('dl-font-family');
    const fontSize = getEl('dl-font-size');
    const fillColor = getEl('dl-fill-color');
    const strokeColor = getEl('dl-stroke-color');
    const bgColor = getEl('dl-bg-color');
    if (fontSelect && isTextObject(obj) && DESIGN_LAB_FONTS.includes(String(obj.fontFamily || ''))) {
      fontSelect.value = String(obj.fontFamily || 'Share Tech Mono');
    }
    if (fontSize && isTextObject(obj)) fontSize.value = String(Math.round(Number(obj.fontSize) || 32));
    if (fillColor) {
      const fill = obj ? obj.fill : state.config.accent;
      fillColor.value = toHexColor(fill, state.config.accent);
    }
    if (strokeColor) {
      const stroke = obj ? obj.stroke : state.config.secondary;
      strokeColor.value = toHexColor(stroke, state.config.secondary);
    }
    if (bgColor && state.fabric) {
      bgColor.value = toHexColor(state.fabric.backgroundColor, '#0a0a0a');
    }
    syncTextStyleButtons(obj);
    renderLayerPanel();
    syncUndoRedoButtons();
    updateZoomLabel();
  }

  function pushCanvasHistory(force) {
    if (!state.fabric || state.historyLocked) return;
    const snapshot = captureCanvasSnapshot();
    if (!snapshot) return;
    if (!force && state.history[state.historyIndex] === snapshot) {
      syncUndoRedoButtons();
      return;
    }
    state.history = state.history.slice(0, state.historyIndex + 1);
    state.history.push(snapshot);
    if (state.history.length > 50) state.history.shift();
    state.historyIndex = state.history.length - 1;
    syncUndoRedoButtons();
  }

  function loadCanvasSnapshot(snapshot) {
    if (!state.fabric || !snapshot) return;
    state.historyLocked = true;
    state.fabric.loadFromJSON(snapshot, () => {
      ensureWatermark();
      state.fabric.renderAll();
      state.historyLocked = false;
      syncToolControls();
    });
  }

  function bindElementOnce(id, eventName, handler) {
    const el = getEl(id);
    if (!el) return null;
    const key = `cemBound${eventName}`;
    if (el.dataset[key]) return el;
    el.addEventListener(eventName, handler);
    el.dataset[key] = '1';
    return el;
  }

  function renderLayerPanel() {
    const root = getEl('dl-layer-list');
    if (!root || !state.fabric) return;
    const active = getActiveCanvasObject();
    const layers = state.fabric
      .getObjects()
      .map((obj, absoluteIndex) => ({ obj, absoluteIndex }))
      .filter((entry) => entry.obj && !entry.obj.__cemWatermark)
      .reverse();
    if (!layers.length) {
      root.innerHTML =
        '<div style="color:#555;font-size:11px;text-align:center;padding:18px;border:1px dashed #1a1a1a;border-radius:8px;">No layers yet. Add text, shapes, images, or AI assets to build your stack.</div>';
      return;
    }
    root.innerHTML = '';
    layers.forEach(({ obj, absoluteIndex }, index) => {
      const row = document.createElement('div');
      row.className = `dl-layer-row${obj === active ? ' active' : ''}`;
      const meta = document.createElement('div');
      meta.className = 'dl-layer-meta';
      meta.innerHTML = `<span class="dl-layer-name">${escapeHtml(getObjectDisplayName(obj, index))}</span><span class="dl-layer-type">${escapeHtml(String(obj.type || 'layer'))}</span>`;
      meta.onclick = () => window.dlSelectLayer(absoluteIndex);
      const actions = document.createElement('div');
      actions.className = 'dl-layer-actions';
      const buttons = [
        { text: obj.visible === false ? '🙈' : '👁', title: 'Show / hide', handler: () => window.dlToggleLayerVisibility(absoluteIndex) },
        { text: '↑', title: 'Move forward', handler: () => window.dlMoveLayer(absoluteIndex, 1) },
        { text: '↓', title: 'Move backward', handler: () => window.dlMoveLayer(absoluteIndex, -1) },
        { text: '✕', title: 'Delete layer', handler: () => window.dlDeleteLayer(absoluteIndex) },
      ];
      buttons.forEach((config) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'dl-icon-btn';
        btn.textContent = config.text;
        btn.title = config.title;
        btn.onclick = config.handler;
        actions.appendChild(btn);
      });
      row.appendChild(meta);
      row.appendChild(actions);
      root.appendChild(row);
    });
  }

  function bindCanvasShortcuts() {
    if (state.keyboardBound) return;
    document.addEventListener('keydown', (event) => {
      const key = String(event.key || '').toLowerCase();
      const isMeta = event.metaKey || event.ctrlKey;
      if (!isMeta) return;
      if (key === 'z' && !event.shiftKey) {
        event.preventDefault();
        if (typeof window.dlUndo === 'function') window.dlUndo();
      } else if (key === 'y' || (key === 'z' && event.shiftKey)) {
        event.preventDefault();
        if (typeof window.dlRedo === 'function') window.dlRedo();
      }
    });
    state.keyboardBound = true;
  }

  function bindCanvasDropTarget(target) {
    if (!target || target.dataset.cemDropBound) return;
    target.dataset.cemDropBound = '1';
    target.addEventListener('dragover', (event) => {
      if (!event.dataTransfer) return;
      if ([...event.dataTransfer.types].includes('text/cem-asset')) {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
      }
    });
    target.addEventListener('drop', (event) => {
      if (!event.dataTransfer) return;
      const raw = event.dataTransfer.getData('text/cem-asset');
      if (!raw) return;
      event.preventDefault();
      let payload = null;
      try {
        payload = JSON.parse(raw);
      } catch (err) {
        payload = null;
      }
      if (!payload?.url) return;
      const rect = target.getBoundingClientRect();
      const zoom = state.canvasZoom || 1;
      const position = {
        x: clamp((event.clientX - rect.left) / zoom - 110, 10, Math.max(10, (state.fabric?.getWidth() || 640) - 240)),
        y: clamp((event.clientY - rect.top) / zoom - 60, 10, Math.max(10, (state.fabric?.getHeight() || 420) - 140)),
      };
      const addPromise = payload.kind === 'svg'
        ? window.dlAddSvgToCanvas(payload.url, payload.title || 'Asset', {
            source: payload.source,
            persistUrl: payload.persistUrl || payload.url,
            position,
          })
        : addAnyAssetToCanvas(payload.url, payload.width || 260, position).then((added) => {
            if (added) recordStudioEvent('image-added', { type: 'drag-asset', source: payload.source || 'library' });
          });
      Promise.resolve(addPromise).catch(() => {});
    });
  }

  function bindCanvasEvents() {
    if (!state.fabric || state.fabric.__cemBindingsReady) return;
    const refresh = () => syncToolControls();
    const persist = (event) => {
      if (event?.target?.__cemWatermark) return;
      pushCanvasHistory();
      refresh();
    };
    state.fabric.on('object:added', persist);
    state.fabric.on('object:modified', persist);
    state.fabric.on('object:removed', persist);
    state.fabric.on('selection:created', refresh);
    state.fabric.on('selection:updated', refresh);
    state.fabric.on('selection:cleared', refresh);
    state.fabric.__cemBindingsReady = true;
  }

  function applyTextControlsToSelection() {
    if (!state.fabric) return;
    const obj = getActiveCanvasObject();
    if (!isTextObject(obj)) return;
    const fontFamily = (getEl('dl-font-family') || {}).value || 'Share Tech Mono';
    const fontSize = clamp(Number((getEl('dl-font-size') || {}).value || obj.fontSize || 32), 10, 180);
    const fill = (getEl('dl-fill-color') || {}).value || state.config.accent;
    const bold = getEl('dl-text-bold');
    const italic = getEl('dl-text-italic');
    obj.set({
      fontFamily,
      fontSize,
      fill,
      fontWeight: bold?.classList.contains('is-active') ? 'bold' : 'normal',
      fontStyle: italic?.classList.contains('is-active') ? 'italic' : 'normal',
    });
    state.fabric.renderAll();
    pushCanvasHistory();
    syncToolControls();
  }

  function applyFillColor(value) {
    if (!state.fabric) return;
    const obj = getActiveCanvasObject();
    if (obj && !obj.__cemWatermark) {
      forEachStylableObject(obj, (item) => {
        if (typeof item.set === 'function' && typeof item.fill !== 'undefined') item.set('fill', value);
      });
      state.fabric.renderAll();
      pushCanvasHistory();
      syncToolControls();
      return;
    }
    syncToolControls();
  }

  function applyStrokeColor(value) {
    if (!state.fabric) return;
    const obj = getActiveCanvasObject();
    if (!obj || obj.__cemWatermark) return;
    forEachStylableObject(obj, (item) => {
      if (typeof item.set === 'function' && typeof item.stroke !== 'undefined') {
        item.set('stroke', value);
        if (!item.strokeWidth) item.set('strokeWidth', 2);
      }
    });
    state.fabric.renderAll();
    pushCanvasHistory();
    syncToolControls();
  }

  function applyCanvasBackground(value) {
    if (!state.fabric) return;
    state.fabric.backgroundColor = value;
    state.fabric.renderAll();
    pushCanvasHistory();
    syncToolControls();
  }

  function setCanvasZoom(nextZoom) {
    if (!state.fabric || !window.fabric) return;
    const zoom = clamp(Number(nextZoom) || 1, 0.4, 2.6);
    const center = new fabric.Point(state.fabric.getWidth() / 2, state.fabric.getHeight() / 2);
    state.fabric.zoomToPoint(center, zoom);
    state.canvasZoom = zoom;
    state.fabric.renderAll();
    updateZoomLabel();
  }

  function buildDesignLabSystemPrompt() {
    return [
      'You are CEMbot, the AI creative assistant inside the CEMTrading888 Design Lab.',
      'You help with bot logos, trading dashboards, social media graphics, brand assets, social captions, and grant-application creative support.',
      'Tools available in this lab: Fabric.js 2D canvas with text, layers, colors, uploads, templates, shapes, and export; Three.js 3D Studio; Asset Library with unDraw illustrations, SVG Repo icons, and My Assets from Supabase.',
      'You can generate AI images, suggest color palettes, recommend layouts, and explain exactly which Design Lab tools to use next.',
      'The CEM brand is TRON Legacy meets Bloomberg Terminal with teal #00ffd5 and orange #ff6b35 on deep dark backgrounds.',
      'Be conversational, encouraging, visually minded, and give concrete build steps inside the lab whenever the user describes something they want to create.',
    ].join(' ');
  }

  function initToolBindings() {
    ensureRuntimeStyles();
    ensureCembotMicButton();
    bindCanvasShortcuts();
    const fontSelect = getEl('dl-font-family');
    if (fontSelect && !fontSelect.options.length) {
      DESIGN_LAB_FONTS.forEach((name) => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        fontSelect.appendChild(option);
      });
      fontSelect.value = 'Share Tech Mono';
    }
    bindElementOnce('dl-font-family', 'change', () => applyTextControlsToSelection());
    bindElementOnce('dl-font-size', 'input', () => applyTextControlsToSelection());
    bindElementOnce('dl-fill-color', 'change', (event) => applyFillColor(event.target.value));
    bindElementOnce('dl-stroke-color', 'change', (event) => applyStrokeColor(event.target.value));
    bindElementOnce('dl-bg-color', 'change', (event) => applyCanvasBackground(event.target.value));
    bindElementOnce('dl-text-bold', 'click', (event) => {
      event.currentTarget.classList.toggle('is-active');
      applyTextControlsToSelection();
    });
    bindElementOnce('dl-text-italic', 'click', (event) => {
      event.currentTarget.classList.toggle('is-active');
      applyTextControlsToSelection();
    });
    const canvasEl = get2DCanvasElement();
    if (canvasEl?.parentElement) bindCanvasDropTarget(canvasEl.parentElement);
    syncToolControls();
  }

  function initDesignLab() {
    const canvasEl = get2DCanvasElement();
    if (!canvasEl || !window.fabric) return;

    const container = canvasEl.parentElement;
    const width = Math.max(640, (container?.offsetWidth || 800) - 2);
    const height = Math.max(420, (container?.offsetHeight || 520) - 2);

    if (!state.fabric) {
      state.fabric = new fabric.Canvas('dl-canvas', {
        width,
        height,
        backgroundColor: '#0a0a0a',
        preserveObjectStacking: true,
      });
      state.canvasZoom = 1;
      ensureWatermark();
      state.fabric.renderAll();
    } else {
      state.fabric.setWidth(width);
      state.fabric.setHeight(height);
      state.fabric.renderAll();
    }

    updateModeButtons(state.mode || '2d');
    initAssetPanels();
    bindCanvasEvents();
    initToolBindings();
    if (!state.history.length) pushCanvasHistory(true);
    if (!state.resizeBound) {
      window.addEventListener('resize', onStudioResize);
      state.resizeBound = true;
    }
  }

  function onStudioResize() {
    if (state.fabric) initDesignLab();
    if (state.renderer && state.camera) resize3D();
  }

  function resize3D() {
    const canvas = get3DCanvasElement();
    if (!canvas || !state.renderer || !state.camera) return;
    const width = canvas.parentElement.offsetWidth || 800;
    const height = canvas.parentElement.offsetHeight || 520;
    state.camera.aspect = width / Math.max(height, 1);
    state.camera.updateProjectionMatrix();
    state.renderer.setSize(width, height);
  }

  function updateModeButtons(mode) {
    const btn2d = getEl('dl-mode-2d');
    const btn3d = getEl('dl-mode-3d');
    if (!btn2d || !btn3d) return;
    const activeBg = `${state.config.accent}22`;
    const activeColor = state.config.accent;
    btn2d.style.background = mode === '2d' ? activeBg : 'transparent';
    btn2d.style.color = mode === '2d' ? activeColor : '#666';
    btn3d.style.background = mode === '3d' ? activeBg : 'transparent';
    btn3d.style.color = mode === '3d' ? activeColor : '#666';
  }

  function ensure3DScene() {
    const canvas = get3DCanvasElement();
    if (!canvas || !window.THREE) return;

    if (state.renderer) {
      resize3D();
      return;
    }

    const width = canvas.parentElement.offsetWidth || 800;
    const height = canvas.parentElement.offsetHeight || 520;
    const primaryColor = hexToNumber(state.config.accent, 0x00ffcc);
    const secondaryColor = hexToNumber(state.config.secondary, 0xff6600);

    state.scene = new THREE.Scene();
    state.scene.background = new THREE.Color(0x050505);
    state.scene.fog = new THREE.FogExp2(0x050505, 0.035);

    state.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    state.camera.position.set(5, 4, 8);
    state.camera.lookAt(0, 0, 0);

    state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    state.renderer.setSize(width, height);
    state.renderer.setPixelRatio(window.devicePixelRatio || 1);
    state.renderer.shadowMap.enabled = true;
    state.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    const ambient = new THREE.AmbientLight(0x111111, 1.05);
    state.scene.add(ambient);

    state.primaryLight = new THREE.PointLight(primaryColor, 2, 20);
    state.primaryLight.position.set(3, 5, 3);
    state.primaryLight.castShadow = true;
    state.scene.add(state.primaryLight);

    state.secondaryLight = new THREE.PointLight(secondaryColor, 1.5, 16);
    state.secondaryLight.position.set(-4, 2, -3);
    state.scene.add(state.secondaryLight);

    state.grid = new THREE.GridHelper(20, 20, primaryColor, 0x111111);
    state.scene.add(state.grid);

    addDefaultBox();
    bind3DEvents(canvas);
    animate3D();
    onStudioResize();
  }

  function bind3DEvents(canvas) {
    canvas.addEventListener('mousedown', (event) => {
      state.mouseDown = true;
      state.lastMouse = { x: event.clientX, y: event.clientY };
    });
    canvas.addEventListener('mouseup', () => {
      state.mouseDown = false;
    });
    canvas.addEventListener('mouseleave', () => {
      state.mouseDown = false;
    });
    canvas.addEventListener('mousemove', (event) => {
      if (!state.mouseDown) return;
      const dx = event.clientX - state.lastMouse.x;
      const dy = event.clientY - state.lastMouse.y;
      state.theta -= dx * 0.01;
      state.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.1, state.phi - dy * 0.01));
      state.lastMouse = { x: event.clientX, y: event.clientY };
      update3DCamera();
    });
    canvas.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        state.radius = Math.max(2, Math.min(30, state.radius + event.deltaY * 0.01));
        update3DCamera();
      },
      { passive: false }
    );
  }

  function update3DCamera() {
    if (!state.camera) return;
    state.camera.position.set(
      state.radius * Math.sin(state.theta) * Math.cos(state.phi),
      state.radius * Math.sin(state.phi),
      state.radius * Math.cos(state.theta) * Math.cos(state.phi)
    );
    state.camera.lookAt(0, 0, 0);
  }

  function animate3D() {
    if (!state.renderer || !state.scene || !state.camera) return;
    state.animId = requestAnimationFrame(animate3D);
    state.objects.forEach((obj, index) => {
      obj.rotation.y += 0.005 * (index % 2 === 0 ? 1 : -1);
    });
    state.renderer.render(state.scene, state.camera);
  }

  function addDefaultBox() {
    if (!state.scene || !window.THREE) return;
    const geo = new THREE.BoxGeometry(1.5, 1.5, 1.5);
    const mat = new THREE.MeshStandardMaterial({
      color: hexToNumber(state.config.accent, 0x00ffcc),
      wireframe: false,
      metalness: 0.8,
      roughness: 0.2,
    });
    const box = new THREE.Mesh(geo, mat);
    box.castShadow = true;
    box.position.set(0, 0.75, 0);
    state.scene.add(box);
    state.objects.push(box);
    update3DCamera();
  }

  function add3DObject(mesh) {
    if (!mesh || !state.scene) return;
    state.scene.add(mesh);
    state.objects.push(mesh);
    recordStudioEvent('image-added', { type: '3d-object' });
  }

  function downloadUrl(url, filename) {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  window.initMissionStudio = function initMissionStudio(config) {
    state.config = { ...DEFAULT_CONFIG, ...(config || {}) };
    window.dlActiveSource = state.librarySource;
    applyStudioAuthLinks();
    initDesignLab();
    initAssetPanels();
  };

  window.applyStudioAuthLinks = applyStudioAuthLinks;

  window.dlSetAssetTab = function dlSetAssetTab(tab) {
    state.assetTab = ['ai', 'library', 'mine'].includes(tab) ? tab : 'ai';
    window.dlActiveSource = state.librarySource;
    initAssetPanels();
    if (state.assetTab === 'library') {
      const root = getEl('dl-lib-results');
      if (root && !root.querySelector('[data-loaded]')) {
        window.dlLibSearch(state.librarySource);
      }
    }
    if (state.assetTab === 'mine') window.dlLoadMyAssets();
  };

  window.dlSetMode = function dlSetMode(mode) {
    state.mode = mode === '3d' ? '3d' : '2d';
    const panel2d = getEl('dl-2d-panel');
    const panel3d = getEl('dl-3d-panel');
    if (panel2d) panel2d.style.display = state.mode === '2d' ? 'flex' : 'none';
    if (panel3d) panel3d.style.display = state.mode === '3d' ? 'flex' : 'none';
    updateModeButtons(state.mode);
    if (state.mode === '2d') {
      initDesignLab();
    } else {
      setTimeout(ensure3DScene, 50);
    }
  };

  window.initDesignLab = initDesignLab;

  window.dlAddText = function dlAddText() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const fontFamily = (getEl('dl-font-family') || {}).value || 'Share Tech Mono';
    const fontSize = clamp(Number((getEl('dl-font-size') || {}).value || 32), 10, 180);
    const fill = (getEl('dl-fill-color') || {}).value || state.config.accent;
    const text = new fabric.IText('Your text here', {
      left: 100,
      top: 100,
      fontSize,
      fill,
      fontFamily,
    });
    addObjectToCanvas(text, 'Text');
    text.enterEditing();
    syncToolControls();
  };

  window.dlAddRect = function dlAddRect() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const fill = (getEl('dl-fill-color') || {}).value || 'transparent';
    const stroke = (getEl('dl-stroke-color') || {}).value || state.config.accent;
    const rect = new fabric.Rect({
      left: 100,
      top: 100,
      width: 200,
      height: 120,
      fill,
      stroke,
      strokeWidth: 2,
      rx: 6,
      ry: 6,
    });
    addObjectToCanvas(rect, 'Rectangle');
  };

  window.dlAddCircle = function dlAddCircle() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const circle = new fabric.Circle({
      left: 130,
      top: 120,
      radius: 72,
      fill: (getEl('dl-fill-color') || {}).value || 'transparent',
      stroke: (getEl('dl-stroke-color') || {}).value || state.config.accent,
      strokeWidth: 2,
    });
    addObjectToCanvas(circle, 'Circle');
  };

  window.dlAddTriangle = function dlAddTriangle() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const triangle = new fabric.Triangle({
      left: 160,
      top: 120,
      width: 160,
      height: 140,
      fill: (getEl('dl-fill-color') || {}).value || 'transparent',
      stroke: (getEl('dl-stroke-color') || {}).value || state.config.accent,
      strokeWidth: 2,
    });
    addObjectToCanvas(triangle, 'Triangle');
  };

  window.dlAddLine = function dlAddLine() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const line = new fabric.Line([80, 110, 280, 190], {
      left: 0,
      top: 0,
      stroke: (getEl('dl-stroke-color') || {}).value || state.config.accent,
      strokeWidth: 4,
    });
    addObjectToCanvas(line, 'Line');
  };

  window.dlAddImage = function dlAddImage() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        fabric.Image.fromURL(ev.target.result, (img) => {
          img.scaleToWidth(300);
          addObjectToCanvas(img, file.name || 'Upload');
          recordStudioEvent('image-added', { type: 'upload' });
        });
      };
      reader.readAsDataURL(file);
    };
    input.click();
  };

  window.dlDeleteSelected = function dlDeleteSelected() {
    if (!state.fabric) return;
    const obj = state.fabric.getActiveObject();
    if (!obj || obj.__cemWatermark) return;
    if (obj.type === 'activeSelection' && typeof obj.forEachObject === 'function') {
      obj.forEachObject((item) => state.fabric.remove(item));
      state.fabric.discardActiveObject();
    } else {
      state.fabric.remove(obj);
    }
    state.fabric.requestRenderAll();
  };

  window.dlClear = function dlClear() {
    if (!state.fabric) return;
    if (window.confirm('Clear canvas? This cannot be undone.')) {
      state.historyLocked = true;
      state.fabric.clear();
      state.fabric.backgroundColor = (getEl('dl-bg-color') || {}).value || '#0a0a0a';
      ensureWatermark();
      state.fabric.renderAll();
      state.historyLocked = false;
      pushCanvasHistory(true);
      syncToolControls();
    }
  };

  window.dlExport = function dlExport() {
    if (!state.fabric) return;
    const fmt = (getEl('dl-export-format') || {}).value || 'png';
    if (fmt === 'svg') {
      const svg = state.fabric.toSVG();
      const blob = new Blob([svg], { type: 'image/svg+xml' });
      const url = URL.createObjectURL(blob);
      downloadUrl(url, `cem-design-${Date.now()}.svg`);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } else {
      const url = state.fabric.toDataURL({ format: fmt, multiplier: 2, quality: 0.92 });
      downloadUrl(url, `cem-design-${Date.now()}.${fmt}`);
    }
    recordStudioEvent('export', { format: fmt });
  };

  window.dlInsertColor = function dlInsertColor(hex) {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const obj = state.fabric.getActiveObject();
    if (obj && !obj.__cemWatermark) {
      forEachStylableObject(obj, (item) => {
        if (typeof item.fill !== 'undefined') item.set('fill', hex);
      });
      state.fabric.renderAll();
      pushCanvasHistory();
      syncToolControls();
      return;
    }
    const rect = new fabric.Rect({
      left: 120,
      top: 120,
      width: 120,
      height: 80,
      fill: hex,
      stroke: (getEl('dl-stroke-color') || {}).value || 'transparent',
      rx: 6,
      ry: 6,
    });
    addObjectToCanvas(rect, 'Color Block');
  };

  window.dlAddLogo = function dlAddLogo() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const text = new fabric.Text(state.config.logoText, {
      left: 80,
      top: 80,
      fontSize: 18,
      fill: state.config.accent,
      fontFamily: 'Courier New',
      fontWeight: 'bold',
      charSpacing: 150,
    });
    addObjectToCanvas(text, 'Brand Logo');
  };

  window.dlAddBrandText = function dlAddBrandText() {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const text = new fabric.Text(state.config.brandText, {
      left: 80,
      top: 130,
      fontSize: 28,
      fill: '#ffffff',
      fontFamily: 'Courier New',
      fontWeight: 'bold',
    });
    addObjectToCanvas(text, 'Brand Text');
  };

  window.dlUndo = function dlUndo() {
    if (state.historyIndex <= 0) return;
    state.historyIndex -= 1;
    syncUndoRedoButtons();
    loadCanvasSnapshot(state.history[state.historyIndex]);
  };

  window.dlRedo = function dlRedo() {
    if (state.historyIndex >= state.history.length - 1) return;
    state.historyIndex += 1;
    syncUndoRedoButtons();
    loadCanvasSnapshot(state.history[state.historyIndex]);
  };

  window.dlZoomIn = function dlZoomIn() {
    setCanvasZoom((state.canvasZoom || 1) + 0.1);
  };

  window.dlZoomOut = function dlZoomOut() {
    setCanvasZoom((state.canvasZoom || 1) - 0.1);
  };

  window.dlZoomReset = function dlZoomReset() {
    if (state.fabric) state.fabric.setViewportTransform([1, 0, 0, 1, 0, 0]);
    state.canvasZoom = 1;
    updateZoomLabel();
    if (state.fabric) state.fabric.renderAll();
    syncToolControls();
  };

  window.dlSelectLayer = function dlSelectLayer(absoluteIndex) {
    if (!state.fabric) return;
    const obj = state.fabric.getObjects()[absoluteIndex];
    if (!obj || obj.__cemWatermark) return;
    state.fabric.setActiveObject(obj);
    state.fabric.renderAll();
    syncToolControls();
  };

  window.dlToggleLayerVisibility = function dlToggleLayerVisibility(absoluteIndex) {
    if (!state.fabric) return;
    const obj = state.fabric.getObjects()[absoluteIndex];
    if (!obj || obj.__cemWatermark) return;
    obj.set('visible', obj.visible === false);
    state.fabric.renderAll();
    pushCanvasHistory();
    syncToolControls();
  };

  window.dlMoveLayer = function dlMoveLayer(absoluteIndex, delta) {
    if (!state.fabric) return;
    const objects = state.fabric.getObjects();
    const obj = objects[absoluteIndex];
    if (!obj || obj.__cemWatermark) return;
    const watermarkIndex = objects.findIndex((item) => item && item.__cemWatermark);
    const nextIndex = clamp(absoluteIndex + delta, Math.max(0, watermarkIndex + 1), objects.length - 1);
    state.fabric.moveTo(obj, nextIndex);
    state.fabric.setActiveObject(obj);
    state.fabric.renderAll();
    pushCanvasHistory();
    syncToolControls();
  };

  window.dlDeleteLayer = function dlDeleteLayer(absoluteIndex) {
    if (!state.fabric) return;
    const obj = state.fabric.getObjects()[absoluteIndex];
    if (!obj || obj.__cemWatermark) return;
    state.fabric.remove(obj);
    state.fabric.renderAll();
    syncToolControls();
  };

  window.dlApplyTemplate = function dlApplyTemplate(name) {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) return;
    const template = DESIGN_LAB_TEMPLATES[name];
    if (!template) return;
    if (getNonWatermarkObjects().length && !window.confirm('Replace the current canvas with this template?')) return;
    state.historyLocked = true;
    state.fabric.clear();
    state.fabric.backgroundColor = template.background || '#0a0a0a';
    ensureWatermark();
    template.build().forEach((item) => {
      let obj = null;
      if (item.kind === 'rect') obj = new fabric.Rect(item.props);
      if (item.kind === 'circle') obj = new fabric.Circle(item.props);
      if (item.kind === 'triangle') obj = new fabric.Triangle(item.props);
      if (item.kind === 'line') {
        const { points, ...rest } = item.props;
        obj = new fabric.Line(points, rest);
      }
      if (item.kind === 'text') {
        const props = { ...item.props };
        const textValue = props.text || '';
        delete props.text;
        obj = new fabric.Textbox(textValue, props);
      }
      if (obj) addObjectToCanvas(obj, item.label, { select: false });
    });
    state.fabric.renderAll();
    state.historyLocked = false;
    document.querySelectorAll('.dl-template-btn').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.template === name);
    });
    pushCanvasHistory(true);
    syncToolControls();
    recordStudioEvent('image-added', { type: 'template', template: name });
  };

  function getDesignLabGenerateStyle(model) {
    const styleByModel = {
      grok: 'photoreal trading dashboard, cinematic fintech ad, TRON x Bloomberg aesthetic',
      flux: 'stylized futuristic trading dashboard, neon teal and orange concept art',
      dalle: 'clean trading brand graphic, polished marketing composition, text-friendly layout',
      cembot: 'on-brand trading dashboard, premium CEM campaign visual, teal and orange highlights',
    };
    return styleByModel[String(model || '').trim().toLowerCase()] || 'trading dashboard';
  }

  window.dlGenerate = async function dlGenerate() {
    const prompt = (getEl('dl-prompt') || {}).value?.trim();
    const model = (getEl('dl-model') || {}).value || 'grok';
    const btn = getEl('dl-generate-btn');
    const style = getDesignLabGenerateStyle(model);
    if (!prompt) {
      setStatus('Enter a prompt first.', true);
      return;
    }
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⚡ Generating...';
    }
    setStatus(`Generating with ${model}...`, false);
    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, style, model }),
      });
      let data = {};
      try {
        data = await res.json();
      } catch (err) {
        data = {};
      }
      const generatedUrl = data.url || data.image_url || '';
      if (res.ok && generatedUrl) {
        window.dlAddGeneratedImage(generatedUrl, data.prompt || prompt, model);
        const added = await addAnyAssetToCanvas(
          generatedUrl,
          300,
          null,
          data.prompt || prompt || 'Generated Image'
        );
        if (added) recordStudioEvent('image-added', { type: 'generated-image', model });
        void saveAssetRecord({
          asset_type: 'generated_image',
          prompt: data.prompt || prompt,
          model_used: model,
          url: generatedUrl,
          tags: ['design-lab', 'ai', 'pollinations'],
          metadata: { source: 'ai-generate', provider: data.provider || 'pollinations', style },
        });
        setStatus(
          added ? '✓ Generated and added to canvas.' : '✓ Generated. Click the gallery tile to add it.',
          false
        );
      } else {
        const message = data.error || data.message || 'Image generation failed.';
        setStatus(message, true);
      }
    } catch (err) {
      setStatus('Could not generate image. Check that /api/generate is deployed.', true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚡ GENERATE';
      }
      recordStudioEvent('generate', { prompt, model });
    }
  };

  window.dlAddGeneratedImage = function dlAddGeneratedImage(url, prompt, model) {
    const gallery = getEl('dl-gallery');
    if (!gallery) return;
    clearGalleryPlaceholder();
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative; cursor:pointer; border:1px solid #333; border-radius:4px; overflow:hidden;';
    wrapper.title = `${model}: ${prompt}`;
    wrapper.onclick = () => {
      void addAnyAssetToCanvas(url, 300, null, prompt || 'Generated Image').then((added) => {
        if (added) recordStudioEvent('image-added', { type: 'generated-image', model });
      });
    };
    makeAssetDraggable(wrapper, {
      url,
      width: 300,
      source: model,
      title: prompt,
      kind: isProbablySvgUrl(url) ? 'svg' : 'raster',
      persistUrl: url,
    });
    const img = document.createElement('img');
    img.src = url;
    img.style.cssText = 'width:100%; display:block;';
    wrapper.appendChild(img);
    gallery.prepend(wrapper);
  };

  window.dlAddPlaceholderTile = function dlAddPlaceholderTile(prompt, model, message) {
    const gallery = getEl('dl-gallery');
    if (!gallery) return;
    clearGalleryPlaceholder();
    const wrapper = document.createElement('div');
    wrapper.style.cssText = `position:relative; cursor:pointer; border:1px solid ${state.config.accent}33; border-radius:4px; padding:8px; background:#0d1f1a;`;
    wrapper.onclick = () => {
      if (!state.fabric || !window.fabric) initDesignLab();
      if (!state.fabric) return;
      const block = new fabric.Textbox(prompt.slice(0, 80), {
        left: 90,
        top: 90,
        width: 260,
        fontSize: 18,
        fill: state.config.accent,
        fontFamily: 'Courier New',
      });
      state.fabric.add(block);
      state.fabric.setActiveObject(block);
    };
    wrapper.innerHTML = `<div style="color:${state.config.accent}; font-size:10px; margin-bottom:4px;">${escapeHtml(model)}</div><div style="color:#888; font-size:10px;">${escapeHtml(prompt.slice(0, 60))}...</div><div style="color:#444; font-size:9px; margin-top:4px;">${escapeHtml(message)}</div>`;
    gallery.prepend(wrapper);
  };

  window.dlLibSearch = async function dlLibSearch(source) {
    state.librarySource = source === 'svgrepo' ? 'svgrepo' : 'undraw';
    window.dlActiveSource = state.librarySource;
    updateLibrarySourceButtons(state.librarySource);
    const query = (getEl('dl-lib-query') || {}).value?.trim() || 'business';
    const results = getEl('dl-lib-results');
    if (results) {
      results.innerHTML =
        '<div style="color:#666; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">Searching...</div>';
    }
    setLibraryStatus('', false);
    if (state.librarySource === 'undraw') {
      await window.dlSearchUndraw(query);
      return;
    }
    await window.dlSearchSvgrepo(query);
  };

  window.dlSearchUndraw = async function dlSearchUndraw(query) {
    const results = getEl('dl-lib-results');
    const color = String((getEl('dl-undraw-color') || {}).value || state.config.accent).trim();
    if (!results) return;
    const normalizedQuery = String(query || 'business').trim().toLowerCase();
    try {
      const manifest = await fetchUndrawManifest();
      const matches = manifest
        .filter((item) => {
          const haystack = [item.title, item.slug, ...(item.keywords || [])].join(' ').toLowerCase();
          return haystack.includes(normalizedQuery);
        })
        .slice(0, 12);
      if (!matches.length) {
        renderAssetCards(
          results,
          [],
          `No results for "${query}". Try business, finance, growth, dashboard, or goals.`,
          () => null
        );
        setLibraryStatus('No unDraw matches found.', false);
        results.dataset.loaded = 'true';
        return;
      }
      const tintedMatches = await Promise.all(
        matches.map(async (item) => ({
          title: item.title,
          sourceUrl: item.media,
          dataUrl: await getTintedUndrawDataUrl(item, color),
        }))
      );
      renderAssetCards(results, tintedMatches, '', (item) => {
        const card = createCardShell();
        const img = createAssetPreview(item.dataUrl, 80);
        const label = document.createElement('span');
        label.style.cssText = 'color:#666; font-size:9px; text-align:center;';
        label.textContent = item.title;
        card.appendChild(img);
        card.appendChild(label);
        makeAssetDraggable(card, {
          url: item.dataUrl,
          width: 220,
          source: 'undraw',
          title: item.title,
          kind: 'svg',
          persistUrl: item.dataUrl,
        });
        card.onclick = () => {
          void window.dlAddSvgToCanvas(item.dataUrl, item.title, {
            source: 'undraw',
            persistUrl: item.dataUrl,
          });
        };
        return card;
      });
      results.dataset.loaded = 'true';
      setLibraryStatus(`${tintedMatches.length} results · Click to add to canvas`, false);
    } catch (err) {
      const fallback = UNDRAW_FALLBACK.filter((item) => {
        const haystack = [item.title, item.slug, ...(item.keywords || [])].join(' ').toLowerCase();
        return haystack.includes(normalizedQuery);
      });
      const matches = fallback.length ? fallback.slice(0, 12) : UNDRAW_FALLBACK.slice(0, 8);
      const tintedMatches = await Promise.all(
        matches.map(async (item) => ({
          title: item.title,
          dataUrl: await getTintedUndrawDataUrl(
            {
              slug: item.slug,
              media: `https://cdn.jsdelivr.net/npm/undraw-svg@latest/svgs/${item.slug}.svg`,
            },
            color
          ),
        }))
      );
      renderAssetCards(results, tintedMatches, '', (item) => {
        const card = createCardShell();
        const img = createAssetPreview(item.dataUrl, 80);
        const label = document.createElement('span');
        label.style.cssText = 'color:#666; font-size:9px; text-align:center;';
        label.textContent = item.title;
        card.appendChild(img);
        card.appendChild(label);
        makeAssetDraggable(card, {
          url: item.dataUrl,
          width: 220,
          source: 'undraw',
          title: item.title,
          kind: 'svg',
          persistUrl: item.dataUrl,
        });
        card.onclick = () => {
          void window.dlAddSvgToCanvas(item.dataUrl, item.title, {
            source: 'undraw',
            persistUrl: item.dataUrl,
          });
        };
        return card;
      });
      results.dataset.loaded = 'true';
      setLibraryStatus(`Showing curated unDraw fallback · ${err.message}`, false);
    }
  };

  window.dlSearchSvgrepo = async function dlSearchSvgrepo(query) {
    const results = getEl('dl-lib-results');
    if (!results) return;
    const normalizedQuery = String(query || 'chart').trim().toLowerCase();
    try {
      const res = await fetch(`${SVG_REPO_SEARCH_URL}?query=${encodeURIComponent(query)}&limit=20`);
      if (!res.ok) throw new Error(`SVG Repo unavailable (${res.status})`);
      const data = await res.json();
      const items = (data.results || data.vectors || data || [])
        .map(normalizeSvgRepoItem)
        .filter(Boolean)
        .slice(0, 12);
      if (!items.length) throw new Error('No SVG Repo results');
      renderAssetCards(results, items, '', (item) => {
        const card = createCardShell();
        const img = createAssetPreview(item.url, 60);
        img.style.filter = 'invert(0.82)';
        const label = document.createElement('span');
        label.style.cssText = 'color:#666; font-size:9px; text-align:center;';
        label.textContent = item.title.slice(0, 24);
        card.appendChild(img);
        card.appendChild(label);
        makeAssetDraggable(card, {
          url: item.url,
          width: 220,
          source: 'svgrepo',
          title: item.title,
          kind: 'svg',
          persistUrl: item.url,
        });
        card.onclick = () => {
          void window.dlAddSvgToCanvas(item.url, item.title, {
            source: 'svgrepo',
            persistUrl: item.url,
          });
        };
        return card;
      });
      results.dataset.loaded = 'true';
      setLibraryStatus(`${items.length} results · Free commercial use · Click to add`, false);
    } catch (err) {
      const fallback = SVG_REPO_FALLBACK.filter((item) => {
        const haystack = [item.title, ...(item.keywords || [])].join(' ').toLowerCase();
        return haystack.includes(normalizedQuery);
      });
      const items = fallback.length ? fallback : SVG_REPO_FALLBACK;
      renderAssetCards(results, items, '', (item) => {
        const card = createCardShell();
        const img = createAssetPreview(item.url, 60);
        img.style.filter = 'invert(0.82)';
        const label = document.createElement('span');
        label.style.cssText = 'color:#666; font-size:9px; text-align:center;';
        label.textContent = item.title;
        card.appendChild(img);
        card.appendChild(label);
        makeAssetDraggable(card, {
          url: item.url,
          width: 220,
          source: 'svgrepo',
          title: item.title,
          kind: 'svg',
          persistUrl: item.url,
        });
        card.onclick = () => {
          void window.dlAddSvgToCanvas(item.url, item.title, {
            source: 'svgrepo',
            persistUrl: item.url,
          });
        };
        return card;
      });
      results.dataset.loaded = 'true';
      setLibraryStatus(`Showing curated SVG Repo fallback · ${err.message}`, false);
    }
  };

  window.dlAddSvgToCanvas = async function dlAddSvgToCanvas(url, title, options) {
    if (!state.fabric || !window.fabric) initDesignLab();
    if (!state.fabric) {
      window.alert('Switch to 2D Canvas mode first.');
      return;
    }
    const added = await addSvgToCanvasInternal(url, 220, options?.position, title);
    if (!added) {
      setLibraryStatus('Could not add this asset to the canvas.', true);
      return;
    }
    recordStudioEvent('image-added', { type: 'library-asset', source: options?.source || state.librarySource });
    setLibraryStatus(`✓ "${title}" added to canvas`, false);
    await saveAssetRecord({
      asset_type: 'library_asset',
      prompt: title,
      model_used: options?.source || state.librarySource,
      url: options?.persistUrl || url,
      tags: ['design-lab', 'library'],
      metadata: { source: options?.source || state.librarySource },
    });
  };

  window.dlLoadMyAssets = async function dlLoadMyAssets() {
    const results = getEl('dl-mine-results');
    if (!results) return;
    results.innerHTML =
      '<div style="color:#666; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">Loading...</div>';
    const { key, url } = resolveSupabaseAuth();
    if (!key || !url) {
      results.innerHTML =
        '<div style="color:#444; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">Supabase publishable key is missing for the asset library.</div>';
      return;
    }
    try {
      const res = await fetch(
        `${url}/rest/v1/cem_assets?select=id,created_by,asset_type,prompt,model_used,url,filename,created_at&order=created_at.desc&limit=20`,
        {
          headers: {
            apikey: key,
            Authorization: `Bearer ${key}`,
          },
        }
      );
      if (!res.ok) throw new Error(`Asset library unavailable (${res.status})`);
      const data = (await res.json()).filter((item) => item && item.url);
      if (!data.length) {
        results.innerHTML =
          '<div style="color:#444; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">No saved assets yet. Generate or save assets to build your library.</div>';
        return;
      }
      results.innerHTML = '';
      data.forEach((asset) => {
        const card = createCardShell();
        const img = createAssetPreview(asset.url, 80);
        img.style.objectFit = isProbablySvgUrl(asset.url) ? 'contain' : 'cover';
        const meta = document.createElement('div');
        meta.style.cssText = 'width:100%; padding-top:2px;';
        meta.innerHTML = `<div style="color:#666; font-size:9px;">${escapeHtml(asset.model_used || asset.created_by || 'asset')}</div><div style="color:#444; font-size:9px;">${escapeHtml(String(asset.prompt || asset.filename || 'Saved asset').slice(0, 36))}</div>`;
        card.appendChild(img);
        card.appendChild(meta);
        makeAssetDraggable(card, {
          url: asset.url,
          width: isProbablySvgUrl(asset.url) ? 220 : 260,
          source: asset.model_used || asset.created_by || 'saved',
          title: asset.prompt || asset.filename || 'Saved asset',
          kind: isProbablySvgUrl(asset.url) ? 'svg' : 'raster',
          persistUrl: asset.url,
        });
        card.onclick = () => {
          void addAnyAssetToCanvas(
            asset.url,
            isProbablySvgUrl(asset.url) ? 220 : 260,
            null,
            asset.prompt || asset.filename || 'Saved asset'
          ).then((added) => {
            if (added) {
              recordStudioEvent('image-added', { type: 'my-asset', source: asset.model_used || asset.created_by || 'saved' });
            }
          });
        };
        results.appendChild(card);
      });
    } catch (err) {
      results.innerHTML =
        '<div style="color:#444; font-size:11px; grid-column:1/-1; text-align:center; padding:20px;">Could not load assets. Check Supabase connection.</div>';
    }
  };

  window.dlCembotAddMessage = function dlCembotAddMessage(role, text, isPrompt) {
    const { messages } = getCembotDrawerElements();
    if (!messages) return;
    const div = document.createElement('div');
    if (isPrompt) {
      div.className = 'dl-msg-prompt';
      div.title = 'Click to use this prompt';
      div.onclick = () => {
        const promptInput = getEl('dl-prompt');
        if (promptInput) {
          promptInput.value = text;
          if (typeof window.dlSetAssetTab === 'function') window.dlSetAssetTab('ai');
          if (state.cembotOpen) window.dlToggleCembot();
          promptInput.focus();
        }
        if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).catch(() => {});
      };
      div.innerHTML = `⚡ <strong>Ready-to-use prompt</strong> (click to use):<br>${escapeHtml(text)}`;
    } else {
      div.className = role === 'bot' ? 'dl-msg-bot' : 'dl-msg-user';
      div.textContent = text;
    }
    messages.appendChild(div);
    scrollCembotMessages();
  };

  window.dlToggleCembot = function dlToggleCembot() {
    const { input } = getCembotDrawerElements();
    state.cembotOpen = !state.cembotOpen;
    syncCembotDrawerUi();
    if (state.cembotOpen && !state.cembotWelcomed) {
      const welcome =
        "Hey! I'm CEMbot, your creative co-pilot in the Design Lab. I can help you plan content, write image prompts, pick the right model, and keep everything on brand. What are we creating today?";
      window.dlCembotAddMessage('bot', welcome);
      state.cembotHistory.push({ role: 'assistant', content: welcome });
      state.cembotWelcomed = true;
    }
    if (state.cembotOpen && input) window.setTimeout(() => input.focus(), 30);
  };

  window.dlCembotQuick = function dlCembotQuick(text) {
    const { input } = getCembotDrawerElements();
    if (!input) return;
    input.value = text;
    window.dlCembotSend();
  };

  window.dlHintCembotPulse = function dlHintCembotPulse() {
    clearTimeout(state.cembotHintTimer);
    state.cembotHintTimer = window.setTimeout(() => {
      if (state.cembotOpen) return;
      const { orb } = getCembotDrawerElements();
      if (!orb) return;
      const original = orb.style.boxShadow;
      orb.style.boxShadow = '0 0 30px #00ffcccc';
      window.setTimeout(() => {
        if (orb && !state.cembotOpen) orb.style.boxShadow = original || '';
      }, 2000);
    }, 3000);
  };

  function getSpeechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function stopCembotRecognition() {
    clearTimeout(state.cembotVoiceTimer);
    if (!state.cembotRecognition) return;
    try {
      state.cembotRecognition.stop();
    } catch (err) {
      // Browser may throw if recognition is not active.
    }
  }

  function startCembotRecognition() {
    const RecognitionCtor = getSpeechRecognitionCtor();
    if (!RecognitionCtor) {
      state.cembotVoiceMode = false;
      syncCembotVoiceUi();
      window.dlCembotAddMessage('bot', 'Voice mode requires Web Speech API support in this browser.');
      return;
    }
    if (!state.cembotRecognition) {
      const recognition = new RecognitionCtor();
      recognition.continuous = true;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      recognition.onstart = () => {
        state.cembotListening = true;
        syncCembotVoiceUi();
        if (!state.cembotVoiceNoticeShown) {
          window.dlCembotAddMessage('bot', '🎙️ Listening...');
          state.cembotVoiceNoticeShown = true;
        }
      };
      recognition.onresult = (event) => {
        const transcript = Array.from(event.results || [])
          .slice(event.resultIndex || 0)
          .map((result) => result?.[0]?.transcript || '')
          .join(' ')
          .trim();
        if (transcript) window.dlCembotSend(transcript);
      };
      recognition.onerror = (event) => {
        const error = String(event?.error || '');
        if (error && !['aborted', 'no-speech'].includes(error)) {
          window.dlCembotAddMessage('bot', `Voice input issue: ${error}.`);
        }
        if (error === 'not-allowed' || error === 'service-not-allowed') {
          state.cembotVoiceMode = false;
          state.cembotVoiceNoticeShown = false;
        }
        syncCembotVoiceUi();
      };
      recognition.onend = () => {
        state.cembotListening = false;
        syncCembotVoiceUi();
        if (state.cembotVoiceMode && !state.cembotSpeaking) {
          clearTimeout(state.cembotVoiceTimer);
          state.cembotVoiceTimer = window.setTimeout(() => startCembotRecognition(), 250);
        }
      };
      state.cembotRecognition = recognition;
    }
    try {
      state.cembotRecognition.start();
    } catch (err) {
      if (!/already started/i.test(String(err?.message || err || ''))) {
        state.cembotVoiceMode = false;
        state.cembotListening = false;
        syncCembotVoiceUi();
        window.dlCembotAddMessage('bot', 'Voice mode could not start. Try refreshing the page or switching browsers.');
      }
    }
  }

  function pickPreferredSpeechVoice(voices) {
    const list = Array.isArray(voices) ? voices : [];
    const preferred = [
      'Samantha',
      'Karen',
      'Moira',
      'Google US English',
      'Google UK English Female',
      'Microsoft Aria Online (Natural)',
      'Microsoft Jenny Online (Natural)',
    ];
    for (const name of preferred) {
      const match = list.find((voice) =>
        String(voice?.name || '')
          .toLowerCase()
          .includes(name.toLowerCase())
      );
      if (match) return match;
    }
    return (
      list.find((voice) => String(voice?.lang || '').toLowerCase().startsWith('en') && !voice.default) ||
      list.find((voice) => String(voice?.lang || '').toLowerCase().startsWith('en')) ||
      list[0] ||
      null
    );
  }

  function finishCembotSpeech() {
    state.cembotSpeaking = false;
    if (state.cembotVoiceMode) {
      clearTimeout(state.cembotVoiceTimer);
      state.cembotVoiceTimer = window.setTimeout(() => startCembotRecognition(), 180);
    }
  }

  window.dlSpeak = function dlSpeak(text) {
    if (!text || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
      finishCembotSpeech();
      return;
    }
    const speakNow = () => {
      const voices = window.speechSynthesis.getVoices();
      const utterance = new SpeechSynthesisUtterance(text);
      const chosen = pickPreferredSpeechVoice(voices);
      if (chosen) utterance.voice = chosen;
      utterance.lang = chosen?.lang || 'en-US';
      utterance.rate = 0.95;
      utterance.pitch = 1.05;
      utterance.volume = 1.0;
      utterance.onend = () => finishCembotSpeech();
      utterance.onerror = () => finishCembotSpeech();
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    };
    if (window.speechSynthesis.getVoices().length === 0) {
      if (typeof window.speechSynthesis.addEventListener === 'function') {
        window.speechSynthesis.addEventListener(
          'voiceschanged',
          () => {
            if (state.cembotSpeaking) window.dlSpeak(text);
          },
          { once: true }
        );
        return;
      }
    }
    speakNow();
  };

  function speakCembotReply(reply) {
    if (!state.cembotVoiceMode || !reply || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
    state.cembotSpeaking = true;
    if (state.cembotListening) stopCembotRecognition();
    window.dlSpeak(reply);
  }

  window.dlCembotToggleVoice = function dlCembotToggleVoice() {
    if (state.cembotVoiceMode) {
      state.cembotVoiceMode = false;
      state.cembotListening = false;
      state.cembotSpeaking = false;
      state.cembotVoiceNoticeShown = false;
      clearTimeout(state.cembotVoiceTimer);
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      stopCembotRecognition();
      syncCembotVoiceUi();
      window.dlCembotAddMessage('bot', 'Voice mode stopped.');
      return;
    }
    if (!state.cembotOpen) window.dlToggleCembot();
    state.cembotVoiceMode = true;
    state.cembotSpeaking = false;
    state.cembotVoiceNoticeShown = false;
    syncCembotVoiceUi();
    startCembotRecognition();
  };

  window.dlCembotSend = async function dlCembotSend(overrideText) {
    const { input, messages, send } = getCembotDrawerElements();
    if (!input || !messages) return;
    const text =
      typeof overrideText === 'string' ? overrideText.trim() : String(input.value || '').trim();
    if (!text) return;
    if (state.cembotPending) {
      state.cembotQueuedMessages.push(text);
      return;
    }
    if (typeof overrideText !== 'string') input.value = '';

    window.dlCembotAddMessage('user', text);
    state.cembotHistory.push({ role: 'user', content: text });

    const thinking = document.createElement('div');
    thinking.className = 'dl-msg-bot';
    thinking.id = 'dl-cembot-thinking';
    thinking.textContent = '⚡ Thinking...';
    messages.appendChild(thinking);
    scrollCembotMessages();

    state.cembotPending = true;
    input.disabled = true;
    if (send) send.disabled = true;

    try {
      const res = await fetch('/api/coach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: 'chat',
          context: 'design_lab',
          system: buildDesignLabSystemPrompt(),
          message: text,
          history: state.cembotHistory.slice(-8),
          brand: {
            name: 'CEMTrading888',
            colors: { primary: '#00FFCC', secondary: '#FF6600', background: '#0a0a0a' },
            aesthetic: 'TRON Legacy meets Bloomberg Terminal',
            platforms: ['TikTok', 'Instagram', 'YouTube'],
            niche: 'algorithmic trading, micro futures, bot building',
          },
          designContext: {
            mode: state.mode,
            activeTab: state.assetTab,
            selectedModel: (getEl('dl-model') || {}).value || 'grok',
            promptDraft: (getEl('dl-prompt') || {}).value || '',
            layerCount: getNonWatermarkObjects().length,
            selectedObject: getObjectDisplayName(getActiveCanvasObject(), 0),
            zoom: Math.round((state.canvasZoom || 1) * 100),
            availableTools: [
              'Fabric.js text tool',
              'shape tools',
              'image upload',
              'AI image generate',
              'asset library',
              'brand kit',
              'layer panel',
              'undo redo',
              'zoom controls',
              'Three.js studio',
              'templates',
            ],
            voiceMode: state.cembotVoiceMode,
          },
        }),
      });
      let data = {};
      try {
        data = await res.json();
      } catch (err) {
        data = {};
      }
      const thinkingEl = getEl('dl-cembot-thinking');
      if (thinkingEl) thinkingEl.remove();

      const reply = data.response || data.message || data.advice || 'I had trouble with that. Try again.';
      state.cembotHistory.push({ role: 'assistant', content: reply });
      window.dlCembotAddMessage('bot', reply);
      speakCembotReply(reply);

      const promptMatch = reply.match(/["“]([^"”]{30,260})["”]/);
      if (
        promptMatch &&
        /(prompt|generate|try:|use this|copy this|grok|flux|dall-e|dalle)/i.test(reply)
      ) {
        window.dlCembotAddMessage('bot', promptMatch[1], true);
      }
    } catch (err) {
      const thinkingEl = getEl('dl-cembot-thinking');
      if (thinkingEl) thinkingEl.remove();
      window.dlCembotAddMessage(
        'bot',
        'Connection issue. Check that the server is running and /api/coach is available.'
      );
    } finally {
      state.cembotPending = false;
      input.disabled = false;
      if (send) send.disabled = false;
      input.focus();
      if (state.cembotQueuedMessages.length) {
        const queued = state.cembotQueuedMessages.shift();
        window.setTimeout(() => window.dlCembotSend(queued), 120);
      }
    }
  };

  window.dl3dAddBox = function dl3dAddBox() {
    ensure3DScene();
    if (!state.scene || !window.THREE) return;
    const geo = new THREE.BoxGeometry(1, 1, 1);
    const mat = new THREE.MeshStandardMaterial({
      color: hexToNumber(state.config.accent, 0x00ffcc),
      metalness: 0.7,
      roughness: 0.3,
      wireframe: state.wireframe,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set((Math.random() - 0.5) * 4, 0.5, (Math.random() - 0.5) * 4);
    mesh.castShadow = true;
    add3DObject(mesh);
  };

  window.dl3dAddSphere = function dl3dAddSphere() {
    ensure3DScene();
    if (!state.scene || !window.THREE) return;
    const geo = new THREE.SphereGeometry(0.6, 32, 32);
    const mat = new THREE.MeshStandardMaterial({
      color: hexToNumber(state.config.secondary, 0xff6600),
      metalness: 0.5,
      roughness: 0.5,
      emissive: hexToNumber(state.config.secondary, 0xff3300),
      emissiveIntensity: 0.2,
      wireframe: state.wireframe,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set((Math.random() - 0.5) * 4, 0.6, (Math.random() - 0.5) * 4);
    add3DObject(mesh);
  };

  window.dl3dAddPlane = function dl3dAddPlane() {
    ensure3DScene();
    if (!state.scene || !window.THREE) return;
    const geo = new THREE.PlaneGeometry(3, 2);
    const mat = new THREE.MeshStandardMaterial({
      color: hexToNumber(state.config.accent, 0x00ffcc),
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.7,
      wireframe: state.wireframe,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.x = -Math.PI / 6;
    mesh.position.set(0, 1, 0);
    add3DObject(mesh);
  };

  window.dl3dAddParticles = function dl3dAddParticles() {
    ensure3DScene();
    if (!state.scene || !window.THREE) return;
    const count = 300;
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count * 3; i += 1) positions[i] = (Math.random() - 0.5) * 10;
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const mat = new THREE.PointsMaterial({
      color: hexToNumber(state.config.accent, 0x00ffcc),
      size: 0.05,
      transparent: true,
      opacity: 0.8,
    });
    const particles = new THREE.Points(geo, mat);
    add3DObject(particles);
  };

  window.dl3dAddText = function dl3dAddText() {
    ensure3DScene();
    if (!state.scene || !window.THREE) return;
    const offscreen = document.createElement('canvas');
    offscreen.width = 512;
    offscreen.height = 128;
    const ctx = offscreen.getContext('2d');
    ctx.clearRect(0, 0, 512, 128);
    ctx.fillStyle = state.config.accent;
    ctx.font = 'bold 60px Courier New';
    ctx.textAlign = 'center';
    ctx.fillText('CEM★888', 256, 80);
    const tex = new THREE.CanvasTexture(offscreen);
    const geo = new THREE.PlaneGeometry(4, 1);
    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(0, 2, 0);
    add3DObject(mesh);
  };

  window.dl3dToggleWireframe = function dl3dToggleWireframe() {
    state.wireframe = !state.wireframe;
    state.objects.forEach((obj) => {
      if (obj.material && typeof obj.material.wireframe !== 'undefined') {
        obj.material.wireframe = state.wireframe;
      }
    });
  };

  window.dl3dReset = function dl3dReset() {
    if (!state.scene) return;
    state.objects.forEach((obj) => state.scene.remove(obj));
    state.objects = [];
    state.radius = 8;
    state.phi = Math.PI / 4;
    state.theta = Math.PI / 6;
    state.wireframe = false;
    addDefaultBox();
    update3DCamera();
  };

  window.dl3dScreenshot = function dl3dScreenshot() {
    ensure3DScene();
    if (!state.renderer || !state.camera || !state.scene) return;
    state.renderer.render(state.scene, state.camera);
    const url = state.renderer.domElement.toDataURL('image/png');
    downloadUrl(url, `cem-3d-${Date.now()}.png`);
    recordStudioEvent('screenshot', {});
  };
})();
