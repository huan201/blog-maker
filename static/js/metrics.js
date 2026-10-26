/* 阅读次数
 * ------------------------------------------------------------------
 * 设计目标：**任何情况下都不会丢数据、也不会让页面卡住**。
 *
 * 1. localStorage 永远是最可靠的底座 —— 它在访客自己的浏览器里，
 *    重新部署、清空 dist、换服务器都不会影响它。
 * 2. content/views.json 可以作为"基线"提交进仓库，
 *    于是换个浏览器、清了缓存，页面上显示的次数也不会归零。
 * 3. 想要跨设备共享的全局计数时，把 metrics.provider 换成
 *    abacus / goatcounter / custom 即可，失败会自动降级到本地。
 *
 * 最终显示 = max(本地计数, 基线, 远端计数)
 */
(function () {
  'use strict';

  var config = (window.__BLOG__ && window.__BLOG__.metrics) || {};
  var seed = (window.__BLOG__ && window.__BLOG__.viewsSeed) || {};
  var provider = config.provider || 'local';
  var namespace = config.namespace || 'blog';
  var ENDPOINT = config.endpoint || '';
  var siteCode = config.site_code || '';
  var enabled = config.enabled !== false;

  var STORE_KEY = 'blog-views';
  var memory = null;   // localStorage 不可用时的兜底

  /* ---------- 本地存储 ---------- */
  function readStore() {
    if (memory) return memory;
    try {
      var raw = localStorage.getItem(STORE_KEY);
      memory = raw ? JSON.parse(raw) : {};
    } catch (e) {
      memory = {};
    }
    return memory;
  }

  function writeStore(data) {
    memory = data;
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(data));
    } catch (e) { /* 无痕模式写入失败，内存里还在 */ }
  }

  function localGet(slug) {
    var data = readStore();
    return parseInt(data[slug], 10) || 0;
  }

  function localBump(slug) {
    var data = readStore();
    data[slug] = localGet(slug) + 1;
    writeStore(data);
    return data[slug];
  }

  /* ---------- 远端计数 ---------- */
  function safeKey(value) {
    return String(value).replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 120);
  }

  function fetchJson(url) {
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = null;
    var options = { method: 'GET', headers: { Accept: 'application/json' } };
    if (controller) {
      options.signal = controller.signal;
      // 3 秒拿不到就放弃，绝不能拖慢页面
      timer = window.setTimeout(function () { controller.abort(); }, 3000);
    }
    return fetch(url, options)
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        if (timer) window.clearTimeout(timer);
        return data;
      })
      .catch(function (err) {
        if (timer) window.clearTimeout(timer);
        throw err;
      });
  }

  function extractCount(data) {
    if (data == null) return null;
    if (typeof data === 'number') return data;
    var keys = ['value', 'count', 'views', 'hits'];
    for (var i = 0; i < keys.length; i += 1) {
      if (data[keys[i]] != null) {
        var parsed = parseInt(data[keys[i]], 10);
        if (!isNaN(parsed)) return parsed;
      }
    }
    return null;
  }

  function remoteRequest(slug, track) {
    if (provider === 'abacus') {
      var action = track ? 'hit' : 'get';
      return 'https://abacus.jasoncameron.dev/' + action + '/' + encodeURIComponent(safeKey(namespace)) +
             '/' + encodeURIComponent(safeKey(slug));
    }
    if (provider === 'goatcounter' && siteCode) {
      // GoatCounter 的 /counter/ 接口本身就是"访问一次 +1"
      return 'https://' + siteCode + '.goatcounter.com/counter/' +
             encodeURIComponent(slug) + '.json';
    }
    if (provider === 'custom' && ENDPOINT) {
      return ENDPOINT
        .replace('{slug}', encodeURIComponent(safeKey(slug)))
        .replace('{namespace}', encodeURIComponent(safeKey(namespace)))
        .replace('{action}', track ? 'hit' : 'get');
    }
    return null;
  }

  function remoteCount(slug, track) {
    var url = remoteRequest(slug, track);
    if (!url) return Promise.resolve(null);
    return fetchJson(url).then(extractCount).catch(function () { return null; });
  }

  /* ---------- 渲染 ---------- */
  function format(count) {
    if (count == null || count <= 0) return '暂无阅读';
    if (count >= 10000) return '阅读 ' + (count / 10000).toFixed(1) + ' 万次';
    return '阅读 ' + count + ' 次';
  }

  function pickMax(values) {
    var best = 0;
    for (var i = 0; i < values.length; i += 1) {
      var value = parseInt(values[i], 10);
      if (!isNaN(value) && value > best) best = value;
    }
    return best;
  }

  function paint(slug, count) {
    var nodes = document.querySelectorAll('[data-view-key="' + slug.replace(/"/g, '\\"') + '"]');
    for (var i = 0; i < nodes.length; i += 1) {
      nodes[i].textContent = format(count);
      nodes[i].title = '累计阅读 ' + count + ' 次（本地记录 + 基线，重装/重部署都不会丢）';
    }
  }

  function refresh(slug, track) {
    var base = pickMax([localGet(slug), seed[slug] || 0]);
    if (base > 0) paint(slug, base);

    if (provider === 'local') return Promise.resolve();

    return remoteCount(slug, track).then(function (remote) {
      if (remote != null) {
        paint(slug, pickMax([base, remote]));
      }
    });
  }

  function init() {
    if (!enabled) {
      var all = document.querySelectorAll('[data-views]');
      for (var i = 0; i < all.length; i += 1) all[i].textContent = '';
      return;
    }

    var trackers = document.querySelectorAll('[data-views][data-view-track="1"]');
    var seen = {};

    // 1) 需要 +1 的文章页
    for (var i = 0; i < trackers.length; i += 1) {
      var slug = trackers[i].getAttribute('data-view-key');
      if (!slug || seen[slug]) continue;
      seen[slug] = true;
      var bumped = localBump(slug);
      paint(slug, pickMax([bumped, seed[slug] || 0]));
      refresh(slug, true);
    }

    // 2) 只展示、不计数的（首页卡片等）
    var viewers = document.querySelectorAll('[data-views]:not([data-view-track])');
    for (var j = 0; j < viewers.length; j += 1) {
      var key = viewers[j].getAttribute('data-view-key');
      if (!key || seen[key]) continue;
      seen[key] = true;
      refresh(key, false);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
