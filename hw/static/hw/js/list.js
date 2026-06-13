// After search submit: restore focus + cursor to end; otherwise leave input unfocused
(function () {
  const input = document.querySelector('form.filter-bar input[name="q"]');
  if (!input) return;
  const q = new URLSearchParams(window.location.search).get('q');
  if (q) {
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  }
})();

// Persist filters across navigation via sessionStorage
(function () {
  const form = document.querySelector('form.filter-bar');
  if (!form) return;

  const KEY     = 'filter:' + window.location.pathname;
  const CLR_KEY = KEY + ':cleared';
  const params  = new URLSearchParams(window.location.search);
  const FILTER_KEYS = ['q', 'status', 'date_from', 'date_to', 'city', 'stars', 'area'];
  const hasActive = FILTER_KEYS.some(function (k) { return params.has(k); });

  if (sessionStorage.getItem(CLR_KEY)) {
    // Reset was just clicked — wipe saved state, don't restore
    sessionStorage.removeItem(CLR_KEY);
    sessionStorage.removeItem(KEY);
  } else if (hasActive) {
    sessionStorage.setItem(KEY, window.location.search);
  } else if (!params.toString() || !hasActive) {
    var saved = sessionStorage.getItem(KEY);
    if (saved) {
      window.location.replace(window.location.pathname + saved);
      return;
    }
  }

  // Mark storage for clearing when Reset / Reset semua is clicked
  document.querySelectorAll('#fp-reset-all, [data-reset-all]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      sessionStorage.setItem(CLR_KEY, '1');
    });
  });
})();

// Export dropdown toggle
document.querySelectorAll('.export-dropdown').forEach(function (dd) {
  dd.querySelector('.export-btn').addEventListener('click', function (e) {
    e.stopPropagation();
    dd.classList.toggle('open');
  });
});
document.addEventListener('click', function () {
  document.querySelectorAll('.export-dropdown.open').forEach(function (dd) {
    dd.classList.remove('open');
  });
});


// Sortable table columns
(function () {
  const table = document.querySelector('.table-wrap table');
  if (!table) return;
  const ths = table.querySelectorAll('thead th[data-col]');
  let activeCol = null, ascending = true;

  ths.forEach(function (th) {
    th.addEventListener('click', function () {
      const col = parseInt(th.dataset.col, 10);
      if (activeCol === col) {
        ascending = !ascending;
      } else {
        ascending = true;
        if (activeCol !== null) {
          const prev = table.querySelector('thead th[data-col="' + activeCol + '"]');
          if (prev) delete prev.dataset.sort;
        }
      }
      activeCol = col;
      th.dataset.sort = ascending ? 'asc' : 'desc';

      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function (a, b) {
        const aText = (a.cells[col] ? a.cells[col].textContent : '').trim();
        const bText = (b.cells[col] ? b.cells[col].textContent : '').trim();
        const aNum = parseFloat(aText.replace(/[^0-9.-]/g, ''));
        const bNum = parseFloat(bText.replace(/[^0-9.-]/g, ''));
        const cmp = (!isNaN(aNum) && !isNaN(bNum))
          ? aNum - bNum
          : aText.localeCompare(bText, undefined, { sensitivity: 'base' });
        return ascending ? cmp : -cmp;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    });
  });
})();
