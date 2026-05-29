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

// Live search: auto-submit filter form as user types
(function () {
  const form = document.querySelector('form.filter-bar');
  if (!form) return;
  const input = form.querySelector('input[name="q"]');
  if (!input) return;
  let timer;
  input.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(function () { form.submit(); }, 350);
  });
})();

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
