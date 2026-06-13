// After search submit: restore focus + cursor to end; otherwise leave input unfocused
(function () {
  var input = document.querySelector('form.filter-bar input[name="q"]');
  if (!input) return;
  var q = new URLSearchParams(window.location.search).get('q');
  if (q) {
    input.focus();
    var len = input.value.length;
    input.setSelectionRange(len, len);
  }
})();

// Persist filters across navigation via sessionStorage
(function () {
  var form = document.querySelector('form.filter-bar');
  if (!form) return;

  var KEY     = 'filter:' + window.location.pathname;
  var CLR_KEY = KEY + ':cleared';
  var params  = new URLSearchParams(window.location.search);
  var FILTER_KEYS = ['q', 'status', 'date_from', 'date_to', 'city', 'stars', 'area'];
  var hasActive = FILTER_KEYS.some(function (k) { return params.has(k); });

  if (sessionStorage.getItem(CLR_KEY)) {
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

  document.querySelectorAll('#fp-reset-all, [data-reset-all]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      sessionStorage.setItem(CLR_KEY, '1');
    });
  });
})();

// AJAX list: no full-page reload on search, filter, or pagination
(function () {
  var form = document.querySelector('form.filter-bar');
  if (!form) return;

  var KEY = 'filter:' + window.location.pathname;
  var FILTER_KEYS = ['q', 'status', 'date_from', 'date_to', 'city', 'stars', 'area'];

  function getCard() { return document.querySelector('.card'); }

  function updatePage(doc, url, push) {
    var newCard = doc.querySelector('.card');
    var newSub  = doc.querySelector('.page-sub');
    var card    = getCard();
    var pageSub = document.querySelector('.page-sub');
    if (newCard && card) {
      card.replaceWith(newCard);
      bindPagination();
      initSortable();
    }
    if (newSub && pageSub) pageSub.textContent = newSub.textContent;
    if (push) history.pushState(null, '', url);
  }

  function loadUrl(url, push) {
    fetch(url)
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, 'text/html');
        updatePage(doc, url, push);
      })
      .catch(function () { window.location.href = url; });
  }

  function handleSubmit(e) {
    if (e) e.preventDefault();
    var params = new URLSearchParams(new FormData(form));
    var toDelete = [];
    params.forEach(function (v, k) { if (!v) toDelete.push(k); });
    toDelete.forEach(function (k) { params.delete(k); });
    var qs = params.toString();
    var url = window.location.pathname + (qs ? '?' + qs : '');
    var hasActive = FILTER_KEYS.some(function (k) { return params.has(k); });
    if (hasActive) {
      sessionStorage.setItem(KEY, '?' + qs);
    } else {
      sessionStorage.removeItem(KEY);
    }
    loadUrl(url, true);
  }

  form.addEventListener('submit', handleSubmit);
  form.submit = function () { handleSubmit(null); };

  window.addEventListener('popstate', function () {
    var params = new URLSearchParams(window.location.search);
    var hasActive = FILTER_KEYS.some(function (k) { return params.has(k); });
    if (!hasActive) sessionStorage.removeItem(KEY);
    loadUrl(window.location.href, false);
  });

  function bindPagination() {
    var card = getCard();
    if (!card) return;
    card.querySelectorAll('.pagination a.pag-btn').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        loadUrl(a.href, true);
      });
    });
  }

  bindPagination();

  var searchInput = form.querySelector('input[name="q"]');
  if (searchInput) {
    searchInput.addEventListener('input', function () {
      if (searchInput.value === '') form.submit();
    });
  }
})();

// Export dropdown toggle
document.querySelectorAll('.export-dropdown').forEach(function (dd) {
  var btn = dd.querySelector('.export-btn');
  if (!btn) return;
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    dd.classList.toggle('open');
  });
});
document.addEventListener('click', function () {
  document.querySelectorAll('.export-dropdown.open').forEach(function (dd) {
    dd.classList.remove('open');
  });
});

// Sortable table columns — called on load and after each AJAX card replace
function initSortable() {
  var card  = document.querySelector('.card');
  var table = card && card.querySelector('.table-wrap table');
  if (!table) return;
  var ths = table.querySelectorAll('thead th[data-col]');
  var activeCol = null, ascending = true;
  ths.forEach(function (th) {
    th.addEventListener('click', function () {
      var col = parseInt(th.dataset.col, 10);
      if (activeCol === col) {
        ascending = !ascending;
      } else {
        ascending = true;
        if (activeCol !== null) {
          var prev = table.querySelector('thead th[data-col="' + activeCol + '"]');
          if (prev) delete prev.dataset.sort;
        }
      }
      activeCol = col;
      th.dataset.sort = ascending ? 'asc' : 'desc';
      var tbody = table.querySelector('tbody');
      var rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort(function (a, b) {
        var aText = (a.cells[col] ? a.cells[col].textContent : '').trim();
        var bText = (b.cells[col] ? b.cells[col].textContent : '').trim();
        var aNum = parseFloat(aText.replace(/[^0-9.-]/g, ''));
        var bNum = parseFloat(bText.replace(/[^0-9.-]/g, ''));
        var cmp = (!isNaN(aNum) && !isNaN(bNum))
          ? aNum - bNum
          : aText.localeCompare(bText, undefined, { sensitivity: 'base' });
        return ascending ? cmp : -cmp;
      });
      rows.forEach(function (r) { tbody.appendChild(r); });
    });
  });
}
initSortable();
