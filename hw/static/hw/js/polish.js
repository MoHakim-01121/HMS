// Back button: inject above page-header on non-home pages
(function () {
  var HOME_PATHS = ['/', '/company/'];
  var LIST_ROOTS = ['/cl/', '/invoice/', '/services/', '/clients/', '/hotels/', '/users/', '/calendar/', '/search/', '/remittance/'];
  var path = window.location.pathname;
  if (HOME_PATHS.indexOf(path) !== -1) return;
  var header = document.querySelector('.page-header');
  if (!header) return;

  var backUrl;
  if (LIST_ROOTS.indexOf(path) !== -1) {
    backUrl = '/';
  } else {
    var base = path.split('/').filter(Boolean)[0];
    backUrl = base ? '/' + base + '/' : '/';
  }

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'page-back';
  btn.title = 'Kembali (Esc)';
  btn.innerHTML = '<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg>Kembali';
  btn.addEventListener('click', function () {
    location.href = backUrl;
  });
  header.parentNode.insertBefore(btn, header);
})();

// Form submit: disable button + show loading spinner
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('form').forEach(function (form) {
    if (form.id === 'delete-form') return;
    if (form.hasAttribute('data-no-loading')) return;
    form.addEventListener('submit', function () {
      form.querySelectorAll('button[type="submit"]').forEach(function (btn) {
        btn.disabled = true;
        btn.classList.add('btn-loading');
      });
    });
  });

  // Autofocus first visible, editable input in a form
  const firstInput = document.querySelector(
    'form:not(#delete-form):not(.filter-bar) input:not([type=hidden]):not([type=submit]):not([readonly]), ' +
    'form:not(#delete-form):not(.filter-bar) select:not([readonly])'
  );
  if (firstInput) firstInput.focus();
});

// Bottom nav: highlight active item based on current path
(function () {
  var items = document.querySelectorAll('.bnav-item[data-path]');
  if (!items.length) return;
  var path = window.location.pathname;
  var best = null, bestLen = 0;
  items.forEach(function (item) {
    var p = item.getAttribute('data-path');
    if (p === '/' ? path === '/' : path.startsWith(p)) {
      if (p.length > bestLen) { best = item; bestLen = p.length; }
    }
  });
  if (best) best.classList.add('active');
})();

// Keyboard shortcuts — only when not typing in a field
document.addEventListener('keydown', function (e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  const map = {
    'h': '[data-shortcut="home"]',
    'n': '[data-shortcut="new"]',
    'e': '[data-shortcut="edit"]',
    'p': '[data-shortcut="pdf"]',
  };

  const selector = map[e.key.toLowerCase()];
  if (selector) {
    const el = document.querySelector(selector);
    if (el) { e.preventDefault(); el.click(); }
  }

  if (e.key === 'Escape' || e.key.toLowerCase() === 'q') {
    const backBtn = document.querySelector('.page-back');
    if (backBtn) { e.preventDefault(); backBtn.click(); }
  }
});
