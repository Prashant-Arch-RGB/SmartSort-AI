/**
 * SmartSort AI — Main frontend JavaScript
 *
 * Covers:
 *   - Toast notifications
 *   - Folder picker modal
 *   - Max file size slider with Unlimited endpoint
 *   - Scan execution with progress
 *   - Global search
 *   - Checkbox helpers
 *   - Theme application
 */

/* ============================================================
   TOAST NOTIFICATIONS
   ============================================================ */

/**
 * Show a toast notification.
 * @param {string} message
 * @param {'success'|'error'|'warning'|'info'} type
 * @param {number} duration  ms before auto-dismiss (default 3500)
 */
function showToast(message, type, duration) {
  type = type || 'info';
  duration = duration || 3500;

  var container = document.getElementById('toastContainer');
  if (!container) return;

  var toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.textContent = message;

  container.appendChild(toast);

  setTimeout(function () {
    toast.style.transition = 'opacity 0.3s';
    toast.style.opacity = '0';
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 320);
  }, duration);
}

/* ============================================================
   FOLDER PICKER MODAL
   ============================================================ */

var _folderModalCallback = null;

/**
 * Open the folder-path modal.
 * @param {function(string):void} callback  Called with the path when confirmed.
 */
function openFolderModal(callback) {
  _folderModalCallback = callback;
  var modal = document.getElementById('folderModal');
  var input = document.getElementById('modalFolderInput');
  if (modal) modal.style.display = 'flex';
  if (input) { input.value = ''; setTimeout(function () { input.focus(); }, 100); }
}

function closeFolderModal() {
  var modal = document.getElementById('folderModal');
  if (modal) modal.style.display = 'none';
  _folderModalCallback = null;
}

function confirmFolderModal() {
  var input = document.getElementById('modalFolderInput');
  var path = input ? input.value.trim() : '';
  if (!path) { showToast('Please enter a folder path.', 'warning'); return; }
  if (_folderModalCallback) _folderModalCallback(path);
  closeFolderModal();
}

// Close modal when clicking the overlay background
document.addEventListener('DOMContentLoaded', function () {
  var modal = document.getElementById('folderModal');
  if (modal) {
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeFolderModal();
    });
  }

  // Allow Enter key in modal input
  var modalInput = document.getElementById('modalFolderInput');
  if (modalInput) {
    modalInput.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') confirmFolderModal();
      if (e.key === 'Escape') closeFolderModal();
    });
  }
});

/* ============================================================
   SCAN EXECUTION
   ============================================================ */

function startScan() {
  var folderPath = (document.getElementById('folderPath') || {}).value || '';
  folderPath = folderPath.trim();

  if (!folderPath) {
    showToast('Please enter or select a folder path.', 'warning');
    return;
  }

  var recursive = document.getElementById('recursiveToggle');
  var isRecursive = recursive ? recursive.getAttribute('data-checked') === 'true' : true;

  var maxSizeHidden = document.getElementById('maxSizeValue');
  var maxSize = maxSizeHidden ? maxSizeHidden.value : '500';
  // Convert to null for API if unlimited
  var maxSizePayload = (maxSize === 'unlimited') ? null : parseFloat(maxSize);

  var excludeExt  = (document.getElementById('excludeExtensions') || {}).value || '';
  var excludeSubs = (document.getElementById('excludeSubfolders') || {}).value || '';

  // Show progress UI
  var scanBtn      = document.getElementById('scanBtn');
  var progressEl   = document.getElementById('scanProgress');
  var resultEl     = document.getElementById('scanResult');
  var progressFill = document.getElementById('progressBarFill');
  var progressLbl  = document.getElementById('progressLabel');
  var progressSub  = document.getElementById('progressSub');

  if (scanBtn)    scanBtn.disabled = true;
  if (progressEl) progressEl.style.display = 'block';
  if (resultEl)   resultEl.style.display = 'none';

  // Animate progress bar (indeterminate)
  var progressValue = 0;
  var progressInterval = setInterval(function () {
    progressValue = Math.min(progressValue + Math.random() * 3, 88);
    if (progressFill) progressFill.style.width = progressValue + '%';
    if (progressLbl)  progressLbl.textContent = 'Scanning folder... (' + Math.round(progressValue) + '%)';
  }, 200);

  fetch('/api/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder: folderPath,
      recursive: isRecursive,
      excluded_extensions: excludeExt,
      excluded_subfolders: excludeSubs,
      max_size: maxSizePayload,
    })
  })
  .then(function (res) { return res.json(); })
  .then(function (data) {
    clearInterval(progressInterval);
    if (progressFill) progressFill.style.width = '100%';
    if (progressLbl)  progressLbl.textContent = 'Scan complete!';

    if (scanBtn) scanBtn.disabled = false;

    if (data.error) {
      if (progressSub) progressSub.textContent = data.error;
      if (resultEl) {
        resultEl.style.display = 'block';
        var banner = document.getElementById('resultBanner');
        if (banner) {
          banner.className = 'error-banner';
          banner.textContent = data.error;
        }
        var goBtn = document.getElementById('goToPreview');
        if (goBtn) goBtn.style.display = 'none';
      }
      return;
    }

    // Success
    var banner = document.getElementById('resultBanner');
    if (banner) {
      banner.className = 'result-banner';
      banner.innerHTML =
        '✓ Scan complete: <strong>' + data.total + '</strong> files found in <strong>' +
        data.folder + '</strong>. ' +
        (data.needs_review > 0 ? data.needs_review + ' need review.' : '');
    }

    if (progressSub) progressSub.textContent =
      'Categories: ' + Object.entries(data.category_counts || {})
        .map(function (kv) { return kv[0] + ' (' + kv[1] + ')'; }).join(', ');

    if (resultEl) resultEl.style.display = 'block';
    var goBtn = document.getElementById('goToPreview');
    if (goBtn) goBtn.style.display = 'flex';
  })
  .catch(function (err) {
    clearInterval(progressInterval);
    if (scanBtn)    scanBtn.disabled = false;
    if (progressEl) progressEl.style.display = 'none';
    showToast('Scan failed: ' + err, 'error');
  });
}

/* ============================================================
   CHECKBOX TOGGLE (custom checkbox UI)
   ============================================================ */

function toggleCheckbox(el) {
  var current = el.getAttribute('data-checked') === 'true';
  el.setAttribute('data-checked', current ? 'false' : 'true');
}

/* ============================================================
   GLOBAL SEARCH
   ============================================================ */

(function () {
  var input = document.getElementById('globalSearch');
  var dropdown = document.getElementById('searchResults');
  if (!input || !dropdown) return;

  var debounceTimer;

  input.addEventListener('input', function () {
    clearTimeout(debounceTimer);
    var q = input.value.trim();
    if (!q) { dropdown.style.display = 'none'; return; }

    debounceTimer = setTimeout(function () {
      fetch('/api/search?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var results = data.results || [];
          if (!results.length) { dropdown.style.display = 'none'; return; }

          dropdown.innerHTML = results.map(function (r) {
            return '<div class="search-result-item" onclick="window.location.href=\'/preview\'">' +
              '<span class="category-badge cat-' + (r.category || 'other').toLowerCase().replace(/ /g, '_') + '">' + (r.category || '?') + '</span>' +
              '<span>' + r.filename + '</span>' +
              '<span style="color:var(--text-muted);font-size:12px;margin-left:auto">' + r.size + '</span>' +
              '</div>';
          }).join('');
          dropdown.style.display = 'block';
        })
        .catch(function () { dropdown.style.display = 'none'; });
    }, 250);
  });

  input.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { dropdown.style.display = 'none'; input.blur(); }
  });

  document.addEventListener('click', function (e) {
    if (!e.target.closest('.topbar-search')) dropdown.style.display = 'none';
  });
})();

/* ============================================================
   THEME APPLICATION
   ============================================================ */

(function () {
  var html = document.documentElement;
  var theme = html.getAttribute('data-theme') || 'dark';
  // In the future, handle 'system' by checking prefers-color-scheme
  if (theme === 'system') {
    var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    html.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  }
})();

/* ============================================================
   NATIVE FOLDER BROWSER
   ============================================================ */

/**
 * Open a native OS folder-picker via the server-side /api/browse_folder
 * endpoint and call `callback(path)` with the selected path.
 *
 * @param {function(string):void} callback
 */
function browseFolder(callback) {
  fetch('/api/browse_folder', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        showToast('Folder dialog error: ' + data.error, 'error');
        return;
      }
      if (data.path) callback(data.path);
    })
    .catch(function (err) {
      showToast('Could not open folder dialog: ' + err, 'error');
    });
}
