// nav.js — Single source of truth for CEM topbar + ticker
// Injected into every page via <script src="/nav.js"></script>
(function() {
  var page = location.pathname.replace(/^\//, '').replace(/\.html$/, '') || 'index';
  var labActive = (page === 'lab') ? ' active' : '';
  var profileActive = (page === 'user-profile') ? ' active' : '';

  var topbarHTML =
    '<div id="topbar">' +
      '<a href="/" class="cem-logo" style="text-decoration:none;margin-right:36px;">' +
        'CEM<em>TRADING</em><span class="logo-888">888</span>' +
      '</a>' +
      '<div class="nav-links">' +
        '<a href="/lab.html" class="nav-btn' + labActive + '" id="nav-lab">THE LAB</a>' +
        '<a href="/user-profile.html" class="nav-btn' + profileActive + '" id="nav-profile">PROFILE</a>' +
      '</div>' +
      '<div class="topbar-right">' +
        '<div class="live-indicator">' +
          '<div class="live-dot"></div>' +
          '<span class="live-label">LIVE</span>' +
        '</div>' +
        '<button class="avatar-btn" id="user-avatar" onclick="window.location.href=\'/user-profile.html\'">C</button>' +
      '</div>' +
    '</div>';

  var tickerHTML =
    '<div id="ticker-bar">' +
      '<div class="ticker-track">' +
        '<div class="ticker-item"><span class="ticker-sym">MGC</span><span class="ticker-price" id="tp-MGC">—</span><span class="chg-pill pos" id="tc-MGC">—</span></div>' +
        '<div class="ticker-item"><span class="ticker-sym">MES</span><span class="ticker-price" id="tp-MES">—</span><span class="chg-pill neg" id="tc-MES">—</span></div>' +
        '<div class="ticker-item"><span class="ticker-sym">MNQ</span><span class="ticker-price" id="tp-MNQ">—</span><span class="chg-pill neg" id="tc-MNQ">—</span></div>' +
        '<div class="ticker-item"><span class="ticker-sym">BTC</span><span class="ticker-price" id="tp-BTC">—</span><span class="chg-pill pos" id="tc-BTC">—</span></div>' +
        '<div class="ticker-item"><span class="ticker-sym">ETH</span><span class="ticker-price" id="tp-ETH">—</span><span class="chg-pill neg" id="tc-ETH">—</span></div>' +
        '<div class="ticker-item" style="border-right:none"><span class="ticker-sym">BEST</span><span class="ticker-price">—</span><span class="chg-pill pos">—</span></div>' +
      '</div>' +
    '</div>';

  function inject() {
    if (document.getElementById('topbar')) return;

    var frag = document.createElement('div');
    frag.innerHTML = topbarHTML + tickerHTML;

    var topbar = frag.firstElementChild;
    var ticker = frag.lastElementChild;

    document.body.insertBefore(ticker, document.body.firstChild);
    document.body.insertBefore(topbar, document.body.firstChild);

    var content = document.getElementById('main')
      || document.getElementById('profile-shell')
      || document.querySelector('main')
      || document.body.children[2];
    if (content && content.id !== 'topbar' && content.id !== 'ticker-bar') {
      content.style.paddingTop = '80px';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
