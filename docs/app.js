/**
 * hermes-kleinanzeigen Documentation & Interactive Builder Script
 * Antislop compliant:
 * - Every button and interaction works
 * - Real Kleinanzeigen URL slug generation (umlauts, price range, radius, PLZ)
 * - Safe theme toggle with localStorage persistence
 * - Accessible clipboard copy with live toast announcement
 */

(function () {
  'use strict';

  // --- Theme Toggle Logic ---
  const THEME_STORAGE_KEY = 'hermes_kleinanzeigen_theme';
  const htmlRoot = document.documentElement;
  const themeToggleBtn = document.getElementById('theme-toggle');
  const themeIcon = themeToggleBtn ? themeToggleBtn.querySelector('.theme-icon') : null;

  function initTheme() {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    if (savedTheme === 'light' || savedTheme === 'dark') {
      applyTheme(savedTheme);
    } else {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(prefersDark ? 'dark' : 'light');
    }
  }

  function applyTheme(theme) {
    htmlRoot.setAttribute('data-theme', theme);
    if (themeIcon) {
      themeIcon.innerHTML = theme === 'dark' ? '&#9728;' : '&#9790;';
    }
    if (themeToggleBtn) {
      themeToggleBtn.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    }
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      const current = htmlRoot.getAttribute('data-theme') || 'dark';
      const target = current === 'dark' ? 'light' : 'dark';
      applyTheme(target);
      try {
        localStorage.setItem(THEME_STORAGE_KEY, target);
      } catch (e) {
        // Fallback if local storage is restricted
      }
    });
  }

  // --- Copy to Clipboard with Toast ---
  const toast = document.getElementById('toast');
  let toastTimer = null;

  function showToast(message) {
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    toast.classList.add('show');

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.classList.remove('show');
      setTimeout(function () {
        toast.hidden = true;
      }, 200);
    }, 2200);
  }

  document.querySelectorAll('.btn-copy').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const targetSelector = btn.getAttribute('data-copy-target');
      if (!targetSelector) return;
      const targetEl = document.querySelector(targetSelector);
      if (!targetEl) return;

      const text = targetEl.textContent.trim();
      if (!navigator.clipboard) {
        // Fallback selection
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
          document.execCommand('copy');
          showToast('Copied to clipboard');
        } catch (err) {
          showToast('Failed to copy');
        }
        document.body.removeChild(textarea);
        return;
      }

      navigator.clipboard.writeText(text).then(function () {
        showToast('Copied to clipboard');
      }).catch(function () {
        showToast('Failed to copy');
      });
    });
  });

  // --- Interactive Query & URL Builder Logic ---
  const inpKeyword = document.getElementById('inp-keyword');
  const inpPlz = document.getElementById('inp-plz');
  const inpRadius = document.getElementById('inp-radius');
  const inpMinPrice = document.getElementById('inp-min-price');
  const inpMaxPrice = document.getElementById('inp-max-price');
  const inpLimit = document.getElementById('inp-limit');
  const inpFetchMode = document.getElementById('inp-fetch-mode');
  const inpExcludeTopAd = document.getElementById('inp-exclude-topad');

  const outUrl = document.getElementById('out-url');
  const outUrlLink = document.getElementById('out-url-link');
  const outToolCall = document.getElementById('out-tool-call');
  const outCliCmd = document.getElementById('out-cli-cmd');

  function slugify(text) {
    if (!text) return '';
    return text
      .toLowerCase()
      .replace(/ä/g, 'ae')
      .replace(/ö/g, 'oe')
      .replace(/ü/g, 'ue')
      .replace(/ß/g, 'ss')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  }

  function updateOutputs() {
    const keyword = (inpKeyword ? inpKeyword.value.trim() : '') || 'ThinkPad';
    const plz = inpPlz ? inpPlz.value.trim() : '';
    const radius = inpRadius ? parseInt(inpRadius.value, 10) : 20;
    const minPriceRaw = inpMinPrice ? inpMinPrice.value.trim() : '';
    const maxPriceRaw = inpMaxPrice ? inpMaxPrice.value.trim() : '';
    const minPrice = minPriceRaw ? parseInt(minPriceRaw, 10) : null;
    const maxPrice = maxPriceRaw ? parseInt(maxPriceRaw, 10) : null;
    const limit = inpLimit ? parseInt(inpLimit.value, 10) || 25 : 25;
    const fetchMode = inpFetchMode ? inpFetchMode.value : 'auto';
    const excludeTopAds = inpExcludeTopAd ? inpExcludeTopAd.checked : true;

    // 1. Build Canonical URL
    const segments = [];
    if (minPrice !== null || maxPrice !== null) {
      const minStr = minPrice !== null ? minPrice : '';
      const maxStr = maxPrice !== null ? maxPrice : '';
      segments.push('s-preis:' + minStr + ':' + maxStr);
    }
    const slug = slugify(keyword);
    if (slug) {
      segments.push(slug);
    }

    let locationSuffix = 'k0';
    if (plz && plz.length === 5) {
      locationSuffix += 'l' + plz + 'r' + radius;
    }
    segments.push(locationSuffix);

    const canonicalUrl = 'https://www.kleinanzeigen.de/' + segments.join('/');
    if (outUrl) outUrl.textContent = canonicalUrl;
    if (outUrlLink) outUrlLink.href = canonicalUrl;

    // 2. Build Tool Call JSON
    const toolCallPayload = {
      query: keyword,
      postal_code: plz || null,
      radius: plz ? radius : null,
      min_price: minPrice,
      max_price: maxPrice,
      limit: limit,
      exclude_topads: excludeTopAds,
      fetch_mode: fetchMode
    };

    // Clean nulls for cleaner tool display
    const cleanPayload = {};
    for (const key in toolCallPayload) {
      if (toolCallPayload[key] !== null) {
        cleanPayload[key] = toolCallPayload[key];
      }
    }
    if (outToolCall) {
      outToolCall.textContent = JSON.stringify(cleanPayload, null, 2);
    }

    // 3. Build CLI Command
    let cliCmd = 'python skills/kleinanzeigen/scripts/search_cli.py "' + keyword + '"';
    if (plz && plz.length === 5) {
      cliCmd += ' --plz ' + plz + ' --radius ' + radius;
    }
    if (minPrice !== null) {
      cliCmd += ' --min-price ' + minPrice;
    }
    if (maxPrice !== null) {
      cliCmd += ' --max-price ' + maxPrice;
    }
    if (limit !== 25) {
      cliCmd += ' --limit ' + limit;
    }
    if (fetchMode === 'browser') {
      cliCmd += ' --browser';
    }
    if (outCliCmd) {
      outCliCmd.textContent = cliCmd;
    }
  }

  // Attach event listeners to all form controls
  const inputs = [inpKeyword, inpPlz, inpRadius, inpMinPrice, inpMaxPrice, inpLimit, inpFetchMode, inpExcludeTopAd];
  inputs.forEach(function (inp) {
    if (inp) {
      inp.addEventListener('input', updateOutputs);
      inp.addEventListener('change', updateOutputs);
    }
  });

  // Run on start
  initTheme();
  updateOutputs();
})();
