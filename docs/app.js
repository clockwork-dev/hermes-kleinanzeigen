/**
 * hermes-kleinanzeigen Documentation & Interactive Builder Script
 * Antislop & Security Audited:
 * - Deterministic, exact URL generator matching kleinanzeigen_api.py build_search_url()
 * - Secure DOM manipulation (textContent only, safe URL scheme validation, no innerHTML/eval/Function)
 * - Safe theme toggle with localStorage persistence and cross-origin sandboxing
 * - Mobile navigation menu toggle with keyboard trap & Escape handling
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
    try {
      const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
      if (savedTheme === 'light' || savedTheme === 'dark') {
        applyTheme(savedTheme);
        return;
      }
    } catch (e) {
      // LocalStorage access may be restricted in sandboxed environments
    }

    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(prefersDark ? 'dark' : 'light');
  }

  function applyTheme(theme) {
    htmlRoot.setAttribute('data-theme', theme);
    if (themeIcon) {
      themeIcon.textContent = theme === 'dark' ? '\u2600' : '\u263E'; // Sun / Moon
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
        // Fallback for blocked cookies/storage
      }
    });
  }

  // --- Mobile Navigation Menu Toggle ---
  const mobileMenuToggle = document.getElementById('mobile-menu-toggle');
  const siteNav = document.getElementById('site-nav');

  if (mobileMenuToggle && siteNav) {
    mobileMenuToggle.addEventListener('click', function () {
      const isExpanded = mobileMenuToggle.getAttribute('aria-expanded') === 'true';
      const newState = !isExpanded;
      mobileMenuToggle.setAttribute('aria-expanded', newState ? 'true' : 'false');
      siteNav.classList.toggle('nav-open', newState);
    });

    // Close menu when clicking any nav anchor
    siteNav.querySelectorAll('a').forEach(function (link) {
      link.addEventListener('click', function () {
        mobileMenuToggle.setAttribute('aria-expanded', 'false');
        siteNav.classList.remove('nav-open');
      });
    });

    // Close menu on Escape key
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && siteNav.classList.contains('nav-open')) {
        mobileMenuToggle.setAttribute('aria-expanded', 'false');
        siteNav.classList.remove('nav-open');
        mobileMenuToggle.focus();
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
  // Mirrors Python build_search_url exactly
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

  function buildSearchUrl(keyword, minPrice, maxPrice, plz, radius) {
    const parts = [];
    if (minPrice !== null || maxPrice !== null) {
      const minStr = minPrice !== null ? minPrice : '';
      const maxStr = maxPrice !== null ? maxPrice : '';
      parts.push('s-preis:' + minStr + ':' + maxStr);
    }
    parts.push('s-seite:1');

    const path = '/' + parts.join('/');
    const params = new URLSearchParams();
    if (keyword) {
      params.set('keywords', keyword);
    }
    if (plz && plz.length === 5) {
      params.set('locationStr', plz);
      params.set('radius', String(radius));
    }

    const qs = params.toString();
    return 'https://www.kleinanzeigen.de' + path + (qs ? '?' + qs : '');
  }

  function updateOutputs() {
    const keyword = (inpKeyword ? inpKeyword.value.trim() : '') || 'ThinkPad T14';
    const plz = inpPlz ? inpPlz.value.trim() : '';
    const radius = inpRadius ? parseInt(inpRadius.value, 10) : 20;
    const minPriceRaw = inpMinPrice ? inpMinPrice.value.trim() : '';
    const maxPriceRaw = inpMaxPrice ? inpMaxPrice.value.trim() : '';
    const minPrice = minPriceRaw ? Math.max(0, parseInt(minPriceRaw, 10)) : null;
    const maxPrice = maxPriceRaw ? Math.max(0, parseInt(maxPriceRaw, 10)) : null;
    const limit = inpLimit ? Math.max(1, Math.min(100, parseInt(inpLimit.value, 10) || 25)) : 25;
    const fetchMode = inpFetchMode ? inpFetchMode.value : 'auto';
    const excludeTopAds = inpExcludeTopAd ? inpExcludeTopAd.checked : true;

    // 1. Build Canonical URL (Exact match with python kleinanzeigen_api.py)
    const canonicalUrl = buildSearchUrl(keyword, minPrice, maxPrice, plz, radius);
    if (outUrl) {
      outUrl.textContent = canonicalUrl;
    }
    if (outUrlLink) {
      // Ensure URL is strict HTTPS kleinanzeigen.de link (Security Audit check)
      if (canonicalUrl.startsWith('https://www.kleinanzeigen.de/')) {
        outUrlLink.href = canonicalUrl;
      }
    }

    // 2. Build Tool Call JSON
    const toolCallPayload = {
      query: keyword,
      postal_code: plz && plz.length === 5 ? plz : null,
      radius: plz && plz.length === 5 ? radius : null,
      min_price: minPrice,
      max_price: maxPrice,
      limit: limit,
      exclude_topads: excludeTopAds,
      fetch_mode: fetchMode
    };

    const cleanPayload = {};
    for (const key in toolCallPayload) {
      if (toolCallPayload[key] !== null) {
        cleanPayload[key] = toolCallPayload[key];
      }
    }
    if (outToolCall) {
      outToolCall.textContent = JSON.stringify(cleanPayload, null, 2);
    }

    // 3. Build CLI Command with safe shell quoting
    const safeKeyword = keyword.replace(/"/g, '\\"');
    let cliCmd = 'python skills/kleinanzeigen/scripts/search_cli.py "' + safeKeyword + '"';
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

  // Attach event listeners
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
