/* 评论系统
 * ------------------------------------------------------------------
 * 用 utterances 或 giscus，两者都把评论存在 GitHub 上：
 *   · utterances -> 仓库的 Issues
 *   · giscus     -> 仓库的 Discussions
 *
 * 这意味着：清空 dist/、重新部署、换电脑都不会丢评论，
 * 因为评论压根不在静态站点里，而在 GitHub 仓库里。
 *
 * issue 映射用 pathname，所以只要文章的输出路径不变
 * （本项目的输出路径直接沿用源文件名，很稳定），评论就会一直跟着走。
 */
(function () {
  'use strict';

  var config = (window.__BLOG__ && window.__BLOG__.comments) || { provider: 'none' };
  var mount = document.getElementById('comments-mount');
  if (!mount) return;

  var provider = config.provider || 'none';
  var loaded = false;
  var observer = null;

  function currentTheme() {
    return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
  }

  function setupNotice() {
    var repo = config.repo || '你的用户名/仓库名';
    mount.innerHTML =
      '<div class="comments__setup">' +
      '<strong>评论系统还没配置。</strong>' +
      '<ol>' +
      '<li>仓库必须是公开的：<code>' + repo + '</code></li>' +
      '<li>安装 utterances 应用（如果改用 giscus，就装 giscus 应用并开启 Discussions）</li>' +
      '<li>把仓库名填进 <code>blog.config.json</code> 的 <code>comments.repo</code>，重新构建即可。</li>' +
      '</ol>' +
      '</div>';
  }

  function clearFrames() {
    var frames = mount.querySelectorAll('iframe, script');
    for (var i = 0; i < frames.length; i += 1) {
      frames[i].parentNode.removeChild(frames[i]);
    }
  }

  function loadUtterances() {
    clearFrames();
    var script = document.createElement('script');
    script.src = 'https://utteranc.es/client.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.setAttribute('repo', config.repo);
    script.setAttribute('issue-term', config.issue_term || config.mapping || 'pathname');
    script.setAttribute('label', config.label || 'comment');
    script.setAttribute('theme', currentTheme() === 'dark' ? 'github-dark' : 'github-light');
    mount.appendChild(script);
  }

  function loadGiscus() {
    clearFrames();
    var script = document.createElement('script');
    script.src = 'https://giscus.app/client.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.setAttribute('data-repo', config.repo);
    script.setAttribute('data-repo-id', config.repo_id);
    script.setAttribute('data-category', config.category || 'Announcements');
    script.setAttribute('data-category-id', config.category_id);
    script.setAttribute('data-mapping', config.mapping || 'pathname');
    script.setAttribute('data-strict', '0');
    script.setAttribute('data-reactions-enabled', config.reactions_enabled === false ? '0' : '1');
    script.setAttribute('data-emit-metadata', '0');
    script.setAttribute('data-input-position', config.input_position || 'top');
    script.setAttribute('data-theme', currentTheme() === 'dark' ? 'dark' : 'light');
    script.setAttribute('data-lang', 'zh-CN');
    script.setAttribute('data-loading', 'lazy');
    mount.appendChild(script);
  }

  function load() {
    if (loaded) return;
    loaded = true;
    if (provider === 'utterances') loadUtterances();
    else if (provider === 'giscus') loadGiscus();
  }

  if (provider === 'none') {
    mount.innerHTML = '<p class="comments__empty">评论功能已关闭。</p>';
    return;
  }

  if (provider === 'unconfigured') {
    setupNotice();
    return;
  }

  // 评论框一般都在页面底部，等滚动到附近再加载，省流量也更快
  var lazy = config.lazy !== false;
  if (lazy && 'IntersectionObserver' in window) {
    observer = new IntersectionObserver(function (entries) {
      if (entries.some(function (entry) { return entry.isIntersecting; })) {
        observer.disconnect();
        load();
      }
    }, { rootMargin: '600px 0px' });
    observer.observe(mount);
  } else {
    load();
  }

  // 跟随站点的深浅色切换
  window.addEventListener('blog:theme', function () {
    if (!loaded) return;
    if (provider === 'giscus') {
      var frame = document.querySelector('iframe.giscus-frame');
      if (frame && frame.contentWindow) {
        // giscus 支持 postMessage 换主题，比重建更平滑
        frame.contentWindow.postMessage(
          { giscus: { setConfig: { theme: currentTheme() } } },
          'https://giscus.app'
        );
        return;
      }
      loadGiscus();
    } else {
      loadUtterances();
    }
  });
})();
