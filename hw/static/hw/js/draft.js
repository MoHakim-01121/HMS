function initDraft(draftKey, formId, expandRows) {
  let _saveTimer;

  function _saveDraft() {
    const data = {};
    document.getElementById(formId).querySelectorAll('[name]').forEach(el => {
      if (el.name === 'csrfmiddlewaretoken') return;
      const v = data[el.name];
      if (v !== undefined) {
        data[el.name] = Array.isArray(v) ? [...v, el.value] : [v, el.value];
      } else {
        data[el.name] = el.value;
      }
    });
    localStorage.setItem(draftKey, JSON.stringify(data));
  }

  window.restoreDraft = function() {
    const raw = localStorage.getItem(draftKey);
    if (!raw) return;
    const data = JSON.parse(raw);
    if (expandRows) expandRows(data);
    Object.entries(data).forEach(([name, vals]) => {
      const els = [...document.querySelectorAll(`[name="${name}"]`)];
      if (Array.isArray(vals)) { els.forEach((el, i) => { if (i < vals.length) el.value = vals[i]; }); }
      else if (els[0]) { els[0].value = vals; }
    });
    if (typeof recalculate === 'function') recalculate();
    document.getElementById('draft-banner').classList.remove('visible');
  };

  window.discardDraft = function() {
    localStorage.removeItem(draftKey);
    document.getElementById('draft-banner').classList.remove('visible');
  };

  document.addEventListener('DOMContentLoaded', function() {
    if (localStorage.getItem(draftKey)) {
      document.getElementById('draft-banner').classList.add('visible');
    }
    const form = document.getElementById(formId);
    form.addEventListener('input', function() { clearTimeout(_saveTimer); _saveTimer = setTimeout(_saveDraft, 600); });
    form.addEventListener('change', function() { clearTimeout(_saveTimer); _saveTimer = setTimeout(_saveDraft, 600); });
    form.addEventListener('submit', function() { localStorage.removeItem(draftKey); });
  });
}
