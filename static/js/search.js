/* 站内搜索：客户端全文检索
 * 索引是构建时生成的 posts.json（标题 + 摘要 + 正文纯文本 + 标签）。
 */
(function () {
  'use strict';

  var input = document.getElementById('search-input');
  var results = document.getElementById('search-results');
  var status = document.getElementById('search-status');
  if (!input || !results) return;

  var indexUrl = input.getAttribute('data-index') || 'posts.json';
  var posts = null;
  var loading = null;
  var timer = null;
  var activeIndex = -1;

  var SPECIAL = '.*+?^' + String.fromCharCode(36) + '{}()|[]' + String.fromCharCode(92);

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeRegExp(text) {
    var out = '';
    for (var i = 0; i < text.length; i += 1) {
      var ch = text.charAt(i);
      out += SPECIAL.indexOf(ch) >= 0 ? String.fromCharCode(92) + ch : ch;
    }
    return out;
  }

  function ensureIndex() {
    if (loading) return loading;
    loading = fetch(indexUrl)
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        posts = Array.isArray(data) ? data : [];
        return posts;
      })
      .catch(function () {
        posts = [];
        if (status) status.textContent = '搜索索引加载失败，请刷新重试。';
        return posts;
      });
    return loading;
  }

  function highlight(text, query) {
    if (!query) return escapeHtml(text);
    var pattern = new RegExp('(' + escapeRegExp(query) + ')', 'gi');
    return escapeHtml(text).replace(pattern, '<mark>' + String.fromCharCode(36) + '1</mark>');
  }

  function snippet(text, query) {
    if (!text) return '';
    var lower = text.toLowerCase();
    var at = lower.indexOf(query.toLowerCase());
    if (at < 0) return text.slice(0, 90);
    var from = Math.max(0, at - 36);
    var to = Math.min(text.length, at + query.length + 60);
    return (from > 0 ? '…' : '') + text.slice(from, to) + (to < text.length ? '…' : '');
  }

  function score(post, query) {
    var q = query.toLowerCase();
    var total = 0;

    var title = (post.title || '').toLowerCase();
    if (title === q) total += 200;
    else if (title.indexOf(q) === 0) total += 140;
    else if (title.indexOf(q) >= 0) total += 100;

    var tags = (post.tags || []).join(' ').toLowerCase();
    if (tags.indexOf(q) >= 0) total += 45;

    var body = (post.text || '').toLowerCase();
    var hits = body.split(q).length - 1;
    total += Math.min(hits, 8) * 6;

    var summary = (post.summary || '').toLowerCase();
    if (summary.indexOf(q) >= 0) total += 20;

    return total;
  }

  function render(query) {
    if (!posts) return;
    results.innerHTML = '';
    activeIndex = -1;

    if (!query) {
      if (status) status.textContent = '共 ' + posts.length + ' 篇文章';
      return;
    }

    var matched = posts
      .map(function (post) { return { post: post, score: score(post, query) }; })
      .filter(function (item) { return item.score > 0; })
      .sort(function (a, b) {
        if (b.score !== a.score) return b.score - a.score;
        return (b.post.date || '').localeCompare(a.post.date || '');
      })
      .slice(0, 40);

    if (status) {
      status.textContent = matched.length
        ? '找到 ' + matched.length + ' 篇相关文章'
        : '没有匹配「' + query + '」的文章';
    }

    var fragment = document.createDocumentFragment();
    matched.forEach(function (item) {
      var post = item.post;
      var link = document.createElement('a');
      link.className = 'result';
      link.href = post.url;

      var tagPart = (post.tags && post.tags.length)
        ? '<span>·</span><span>' + escapeHtml(post.tags.join('、')) + '</span>'
        : '';

      link.innerHTML =
        '<h2 class="result__title">' + highlight(post.title, query) + '</h2>' +
        '<div class="result__meta">' +
        '<span>' + escapeHtml(post.date_text || post.date || '日期未填') + '</span>' +
        '<span>·</span><span>' + (post.words || 0) + ' 字</span>' + tagPart +
        '</div>' +
        (post.summary
          ? '<p class="result__snippet">' + highlight(snippet(post.summary, query), query) + '</p>'
          : '');
      fragment.appendChild(link);
    });
    results.appendChild(fragment);
  }

  function syncUrl(query) {
    var url = new URL(window.location.href);
    if (query) url.searchParams.set('q', query);
    else url.searchParams.delete('q');
    window.history.replaceState({}, '', url);
  }

  function schedule() {
    var query = input.value.trim();
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      ensureIndex().then(function () { render(query); });
      syncUrl(query);
    }, 120);
  }

  input.addEventListener('input', schedule);

  input.addEventListener('keydown', function (event) {
    var items = results.querySelectorAll('.result');
    if (event.key === 'Escape') {
      input.value = '';
      schedule();
      return;
    }
    if (!items.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      activeIndex += event.key === 'ArrowDown' ? 1 : -1;
      if (activeIndex < 0) activeIndex = items.length - 1;
      if (activeIndex >= items.length) activeIndex = 0;
      for (var i = 0; i < items.length; i += 1) {
        items[i].classList.toggle('is-active', i === activeIndex);
      }
      items[activeIndex].scrollIntoView({ block: 'nearest' });
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      items[activeIndex].click();
    }
  });

  // 支持从别的页面带 ?q= 过来
  var initial = new URL(window.location.href).searchParams.get('q');
  ensureIndex().then(function () {
    if (initial) {
      input.value = initial;
      render(initial.trim());
    } else {
      render('');
      input.focus();
    }
  });
})();
