/* 站点通用交互：外观切换、阅读进度、目录高亮、代码复制、回到顶部 */
(function () {
  'use strict';

  var root = document.documentElement;
  var STORE_KEY = 'blog-appearance';
  var prefersDark = window.matchMedia('(prefers-color-scheme: dark)');

  /* ---------- 外观 ---------- */
  function readPreference() {
    try {
      return localStorage.getItem(STORE_KEY) || (window.__BLOG__ && window.__BLOG__.appearance) || 'auto';
    } catch (e) {
      return 'auto';
    }
  }

  function resolve(preference) {
    if (preference === 'auto') {
      return prefersDark.matches ? 'dark' : 'light';
    }
    return preference === 'dark' ? 'dark' : 'light';
  }

  function apply(preference) {
    var theme = resolve(preference);
    root.dataset.theme = theme;
    root.dataset.appearance = preference;
    var metas = document.querySelectorAll('meta[name="theme-color"]');
    for (var i = 0; i < metas.length; i += 1) {
      metas[i].setAttribute('content', theme === 'dark' ? '#000000' : '#fbfbfd');
    }
    // 通知其它脚本（例如注释框）跟随主题
    window.dispatchEvent(new CustomEvent('blog:theme', { detail: { theme: theme } }));
  }

  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(STORE_KEY, next);
      } catch (e) { /* 隐私模式下写不进去，忽略 */ }
      apply(next);
    });
  }

  prefersDark.addEventListener('change', function () {
    if (readPreference() === 'auto') {
      apply('auto');
    }
  });

  /* ---------- 阅读进度 ---------- */
  var bar = document.getElementById('reading-progress');
  var toTop = document.getElementById('to-top');

  function onScroll() {
    var scrollTop = window.scrollY || document.documentElement.scrollTop;
    var height = document.documentElement.scrollHeight - window.innerHeight;
    if (bar) {
      bar.style.width = (height > 0 ? Math.min(100, (scrollTop / height) * 100) : 0) + '%';
    }
    if (toTop) {
      toTop.classList.toggle('is-visible', scrollTop > 640);
    }
  }

  var ticking = false;
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      onScroll();
      ticking = false;
    });
  }, { passive: true });
  onScroll();

  if (toTop) {
    toTop.addEventListener('click', function () {
      var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
    });
  }

  /* ---------- 代码块复制 ---------- */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.top = '-1000px';
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand('copy');
        resolve();
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(area);
      }
    });
  }

  document.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('.code-block__copy') : null;
    if (!button) return;
    var block = button.closest('.code-block');
    var code = block ? block.querySelector('code') : null;
    if (!code) return;
    copyText(code.innerText).then(function () {
      var old = button.textContent;
      button.textContent = '已复制';
      button.classList.add('is-done');
      window.setTimeout(function () {
        button.textContent = old;
        button.classList.remove('is-done');
      }, 1400);
    }).catch(function () {
      button.textContent = '复制失败';
    });
  });

  /* ---------- 目录滚动高亮 ---------- */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc__item a'));
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var map = {};
    tocLinks.forEach(function (link) {
      var id = decodeURIComponent(link.getAttribute('href').slice(1));
      map[id] = link;
    });

    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        visible[entry.target.id] = entry.isIntersecting;
      });
      var active = null;
      for (var i = 0; i < tocLinks.length; i += 1) {
        var id = decodeURIComponent(tocLinks[i].getAttribute('href').slice(1));
        if (visible[id]) {
          active = tocLinks[i];
          break;
        }
      }
      if (active) {
        tocLinks.forEach(function (link) { link.classList.remove('is-active'); });
        active.classList.add('is-active');
      }
    }, { rootMargin: '-80px 0px -70% 0px', threshold: 0 });

    Object.keys(map).forEach(function (id) {
      var heading = document.getElementById(id);
      if (heading) observer.observe(heading);
    });
  }

  /* ---------- 键盘快捷键 ---------- */
  document.addEventListener('keydown', function (event) {
    var tag = (event.target.tagName || '').toLowerCase();
    var typing = tag === 'input' || tag === 'textarea' || event.target.isContentEditable;

    if (event.key === '/' && !typing) {
      var searchInput = document.getElementById('search-input');
      if (searchInput) {
        event.preventDefault();
        searchInput.focus();
      }
      return;
    }

    if ((event.key === 'k' || event.key === 'K') && (event.metaKey || event.ctrlKey)) {
      var input = document.getElementById('search-input');
      if (input) {
        event.preventDefault();
        input.focus();
      } else {
        event.preventDefault();
        window.location.href = ((window.__BLOG__ && window.__BLOG__.base) || '') + 'search.html';
      }
    }
  });
})();
