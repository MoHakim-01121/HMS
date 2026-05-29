function copyText(text) {
  function showCopyToast() {
    var container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    var t = document.createElement('div');
    t.className = 'toast toast-success';
    t.textContent = 'Disalin: ' + text;
    container.appendChild(t);
    setTimeout(function() {
      t.style.opacity = '0';
      t.style.transform = 'translateX(20px)';
      setTimeout(function() { t.remove(); }, 300);
    }, 2000);
  }

  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(showCopyToast);
  } else {
    var el = document.createElement('textarea');
    el.value = text;
    el.style.cssText = 'position:fixed;opacity:0;pointer-events:none;';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showCopyToast();
  }
}
