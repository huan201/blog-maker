# Blog — 极简静态博客生成器

用 **纯 Python 标准库 + mistune** 手写的静态博客生成器。
零前端框架，零后端服务，构建产物直接丢到 GitHub Pages 就能跑。

**在线地址：<https://huan201.github.io/>**

> v2 是一次比较彻底的重构：Apple 风格界面 + 深色模式、评论系统、
> 阅读次数在重新部署后不丢、内容与生成器解耦，并修掉了一批"操作模式"上的坑（见文末清单）。
>
> **第一次部署请直接看 [docs/deploy-guide.md](docs/deploy-guide.md)**——里面是带每一步点击路径的详细教程。

---

## 目录

- [快速开始](#快速开始)
- [仓库怎么放：三种结构](#仓库怎么放三种结构)
- [目录结构](#目录结构)
- [写文章](#写文章)
- [命令一览](#命令一览)
- [配置说明](#配置说明)
- [评论系统](#评论系统)
- [阅读次数](#阅读次数)
- [部署到 GitHub Pages](#部署到-github-pages)
- [v2 重构做了什么](#v2-重构做了什么)
- [技术栈](#技术栈)
- [常见问题](#常见问题)

---

## 快速开始

需要 Python 3.10 或更高版本。

```bash
# 1. 建虚拟环境并装唯一的第三方依赖
python -m venv venv
venv/Scripts/python.exe -m pip install mistune      # Windows
# source venv/bin/activate && pip install mistune   # macOS / Linux

# 2. 构建站点到 dist/
python -m blog build

# 3. 本地预览（热重建 + 浏览器编辑器）
python -m blog serve
#  网站：  http://127.0.0.1:8000
#  编辑器：http://127.0.0.1:8000/editor
```

---

## 仓库怎么放：三种结构

GitHub Pages 的构建跑在 GitHub 的服务器上，只能读到**仓库里**的文件。
所以"文章 md 原文不进仓库"和"CI 全自动构建"天生有冲突，得选一个平衡点：

| | 结构 | md 原文是否公开 | 自动化 | 说明 |
|---|---|---|---|---|
| **A** | 单仓库：生成器 + 你的文章 | 公开 | 全自动 | 最快上线，适合不在乎源码公开的人 |
| **B** | `blog-maker`（生成器模板）+ `用户名.github.io`（你的博客） | 公开，但只在你自己的博客仓库 | 全自动 | 生成器仓库保持干净，能给别人当模板；站点正好在根域名 |
| **C** | 博客仓库公开 + **文章放私有仓库**，Actions 用 token 拉取 | **不公开** | 全自动 | 完全不接受 md 原文进公开仓库时用 |

如果只是怕**没写完的稿子**被提交，什么都不用改，用私有草稿约定就行：

- 文件名以 `_` 开头的 `.txt` 会被构建器和编辑器完全跳过
- frontmatter 写 `draft: true` 的文章默认不构建（加 `--drafts` 才会）
- 建议再把 `content/_drafts/` 写进 `.gitignore`

```gitignore
content/_drafts/
content/*.draft.txt
```

**文章目录也可以放在仓库外**（本地开发很顺手）：

```bash
python -m blog serve --content "D:\我的文章"
python -m blog build --content "D:\我的文章"
```

或者写进配置：`"build": { "content_dir": "D:/我的文章" }`。

三种结构的完整操作步骤（含私有仓库 + token 的配置）见
[docs/deploy-guide.md](docs/deploy-guide.md) 第 1～3 节。

---

## 目录结构

```
blog-maker/
├── blog/                      # Python 包（生成器本体）
│   ├── __main__.py            #   CLI：build / serve / new / check / stats / clean
│   ├── config.py              #   配置加载 + 校验
│   ├── content.py             #   frontmatter 解析、文章模型
│   ├── markdown_renderer.py   #   Markdown / 公式 / 代码块渲染
│   ├── templating.py          #   单遍扫描的极简模板引擎
│   ├── builder.py             #   站点构建、清单式清理
│   ├── server.py              #   本地预览服务器 + 编辑器 API
│   └── utils.py               #   slug / 日期 / 文本 / 路径安全
├── content/                   # 文章源文件（.txt + frontmatter）
│   ├── mlp.txt
│   ├── friends.txt            # 友链（特殊文件，不当作文章）
│   └── views.json             # 可选：阅读次数基线
├── templates/                 # HTML 模板
│   ├── base.html              #   公共骨架
│   ├── index.html  post.html  #   首页 / 文章页
│   ├── tags.html   tag.html   #   标签总览 / 单个标签
│   ├── search.html 404.html   #   搜索页 / 404
│   ├── friends.html           #   友链页
│   └── editor.html            #   本地编辑器（只在 serve 时提供）
├── static/                    # 静态资源（整目录拷进 dist/，且会被提交）
│   ├── css/style.css          #   主题样式（含深色模式）
│   ├── js/                    #   app / metrics / comments / search
│   ├── images/                #   文章配图
│   ├── attachments/           #   文章附件
│   ├── favicon.svg
│   └── marked.min.js          #   编辑器预览用的 Markdown 解析器
├── docs/deploy-guide.md       # 部署详细教程
├── .github/workflows/deploy.yml   # 推送到 main 自动部署 Pages
├── blog.config.json           # 站点配置（标题、评论、计数……）
└── dist/                      # 构建输出（.gitignore，由 Actions 在部署时生成）
```

---

## 写文章

在 `content/` 下新建 `.txt` 文件（或用 `python -m blog new "标题"`、`/editor` 编辑器）。

**文件名就是 URL**：`content/mlp.txt` → `posts/mlp.html`。
这一点很重要——评论和阅读次数都按 URL 认文章，文件名不变它们就永远不会跟丢。

```markdown
---
title: 文章标题
date: 2026-07-27
tags: python, 教程
summary: 可选，不写就自动截取正文开头
draft: false
pinned: false
---

## 小标题

正文支持 **Markdown**、表格、任务列表、删除线和脚注。

| 列一 | 列二 |
| --- | --- |
| 内容 | 内容 |

- [x] 已完成
- [ ] 待办

> 引用块

````python
print("代码块会自动带语言标签和复制按钮")
````

行内公式 E = mc^2，块级公式：

$$
\frac{\partial L}{\partial W} = X^{T} \cdot \delta
$$

也可以用 LaTeX 原生定界符：\(a^2 + b^2\)

图片：![说明](static/images/photo.png)
附件：[下载文件](static/attachments/file.zip)
```

注意事项：

- 图片、附件放到 `static/` 下，正文里写 **static/ 相对路径**，
  构建时会自动改写成 `../static/...`，不用自己数层级。
- 代码块里的内容不会被当成公式或 Markdown 处理。
- 支持原生 HTML（配置项 `markdown.allow_html`，默认开）。
- 以 `_` 开头的文件是私有草稿，不参与构建。

---

## 命令一览

```bash
python -m blog build                    # 构建到 dist/
python -m blog build --clean            # 先清空输出目录再构建
python -m blog build --drafts           # 连 draft: true 的文章一起构建
python -m blog build --content ../posts # 用仓库外的文章目录
python -m blog build -o public          # 构建到别的目录

python -m blog serve                    # 本地预览 + 文件变化自动重建
python -m blog serve -p 9000            # 换端口
python -m blog serve --host 0.0.0.0     # 让手机也能访问（默认只监听本机）
python -m blog serve --no-watch         # 关掉自动重建

python -m blog new "我的新文章"          # 新建文章，自动带 frontmatter
python -m blog check                    # 体检：配置 / 模板 / 文章 / 资源引用 / 试构建
python -m blog stats                    # 统计：文章数、字数、标签分布
python -m blog clean                    # 清空输出目录（有安全保护）
```

所有命令都支持 `--root <目录>` 指定项目根目录，因此在任何路径下都能执行：

```bash
python -m blog --root ~/code/blog-maker build
```

---

## 配置说明

所有配置集中在根目录的 **`blog.config.json`**（JSON 不支持注释，改动时注意）。

```json
{
  "site": {
    "title": "我的博客",
    "subtitle": "记录学习与思考",
    "description": "站点描述，用于首页和搜索引擎",
    "author": "huan201",
    "url": "https://huan201.github.io/",
    "base_path": "/",
    "github": "https://github.com/huan201/blog-maker"
  },
  "build": {
    "output_dir": "dist",
    "content_dir": "content",
    "include_drafts": false
  },
  "markdown": { "allow_html": true, "math": true, "tables": true },
  "comments": { "provider": "utterances", "repo": "huan201/blog-maker" },
  "metrics":  { "provider": "local", "namespace": "huan201-blog" },
  "theme":    { "accent": "#0071e3", "appearance": "auto" }
}
```

两个最容易填错的字段：

- `site.url`：站点完整地址，RSS / sitemap / 分享卡片用它拼绝对链接。
- `site.base_path`：部署在根域名填 `"/"`，部署在 `/仓库名/` 下填 `"/仓库名/"`。
- `build.content_dir`：文章目录，可以写相对路径，也可以写绝对路径把文章放到仓库外。

改完跑一下 `python -m blog check`，配置写错会直接告诉你哪一项不对。

---

## 评论系统

评论由 **GitHub 托管**，静态站点里一行评论数据都不存。
好处是：清空 `dist/`、重新部署、换电脑都不会丢评论。

| provider | 评论存在哪 | 额外要求 |
| --- | --- | --- |
| `utterances`（默认） | 仓库的 **Issues** | 安装 utterances App，只需填仓库名 |
| `giscus` | 仓库的 **Discussions** | 安装 giscus App + 开启 Discussions + 填 `repo_id` / `category_id` |

三步搞定（详细版见 [部署教程第 5 节](docs/deploy-guide.md)）：

1. 仓库保持 **Public**。
2. 打开 <https://github.com/apps/utterances> → **Install** → 选中你的仓库 → **Install & Authorize**。
3. 确认 @@BT@@blog.config.json@@BT@@ 里 @@BT@@comments.repo@@BT@@ 是 @@BT@@用户名/仓库名@@BT@@，重新构建即可。

评论按页面路径认文章（`mapping: pathname`），而文章输出路径就是源文件名，
所以**只要不改 `content/` 里的文件名**，评论就永远跟着同一篇文章走。

---

## 阅读次数

文章页和首页卡片都会显示阅读次数。实现分三层，**任何一层失效都不会让数字归零**：

1. **本地计数（默认）** — 存在访客浏览器的 `localStorage` 里。
   它不在服务器上，所以重新构建、重新部署、清空 `dist/` 全都影响不到它。
2. **基线文件（可选）** — `content/views.json`，形如 `{ "mlp": 128, "week4": 32 }`。
   页面显示 `max(本地计数, 基线)`。哪怕换了台电脑、清了缓存，
   只要基线还在仓库里，数字就不会掉下去。
3. **远端全局计数（可选）** — 想跨设备共享同一个数字，把 `metrics.provider` 换成：

   | provider | 说明 | 需要配置 |
   | --- | --- | --- |
   | `local` | 仅本地（默认，零依赖） | — |
   | `abacus` | 免费公开计数服务 | `namespace` |
   | `goatcounter` | GoatCounter 统计 | `site_code` |
   | `custom` | 你自己的接口 | `endpoint` |

   远端请求 3 秒超时，失败就静默回退到本地数字，**不会让页面卡住**。

`custom` 的接口约定：

```
GET {endpoint}      endpoint 里可用 {slug} / {namespace} / {action} 占位
                    action = hit（+1）或 get（只读）
返回                { "count": 123 } 或 { "value": 123 } 或直接返回数字
```

---

## 部署到 GitHub Pages

仓库里已经带了 `.github/workflows/deploy.yml`：推送到 `main` 就自动构建并部署。

**三步走（带每一步点击位置的详细版见 [docs/deploy-guide.md](docs/deploy-guide.md)）**

1. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
   （**不要**选 "Deploy from a branch"）。
2. 装一次 utterances App（<https://github.com/apps/utterances>），勾选你的仓库，评论就能用。
3. 把 `site.url` / `site.base_path` 改成本站真实地址：

   | 仓库名 | 站点地址 | `site.url` | `site.base_path` |
   | --- | --- | --- | --- |
   | `用户名.github.io` | `https://用户名.github.io/` | 同左 | `"/"` |
   | 其它名字（如 `blog-maker`） | `https://用户名.github.io/blog-maker/` | 同左 | `"/blog-maker/"` |

   站内链接全部是相对路径，所以 `base_path` 填错也照样能浏览，
   只影响 404 页按钮、robots.txt 和 RSS/sitemap 里的绝对链接。

**关于 `dist/`**

`dist/` 在 `.gitignore` 里，**不进仓库**，由 GitHub Actions 每次部署时现构建。
构建会自动写一个 `.nojekyll`，防止 Jekyll 忽略下划线开头的文件。

---

## v2 重构做了什么

### 界面

- 重写整套 CSS：Apple 设计语言（系统字体、紧字距、大留白、毛玻璃导航、圆角卡片、克制阴影）
- **完整深色模式**：跟随系统，也能手动切换，选择记在 `localStorage`
- 文章页新增：阅读进度条、右侧目录（自动高亮）、上下篇导航、标题锚点
- 代码块带语言标签和「复制」按钮；表格自动横向滚动；图片懒加载
- 搜索页：全文检索（标题 / 正文 / 标签加权排序）、结果高亮、键盘上下选择、`/` 快速聚焦
- 无障碍：跳到主内容链接、`aria` 标签、可见焦点环、`prefers-reduced-motion` 支持

### 新增能力

- **评论系统**（utterances / giscus，数据存 GitHub，永不丢失）
- **阅读次数**（三层降级设计，见上文）
- 自动生成 `.nojekyll` / `feed.xml` / `sitemap.xml` / `robots.txt` / `404.html`
- 新增 CLI：`new` / `check` / `stats`，以及 `--content` 外置文章目录
- 全新的 `/editor`：新建、删除、上传、快捷键保存、离线草稿、不再整页刷新
- 私有草稿约定：`_` 开头文件跳过 + `draft: true`

### 修掉的"操作模式不合理"

| # | 原来的问题 | 现在 |
| --- | --- | --- |
| 1 | 生成器用相对路径读 `content/`、`templates/`，**必须在项目根目录执行**，换个目录就崩 | 路径全部由配置解析，任意目录可执行，还能 `--root` 指定 |
| 2 | 模板引擎对每个变量各做一次全局替换，**正文里出现占位符字样会被二次替换** | 改成单遍扫描，替换进去的正文不会再被解析 |
| 3 | 公式预处理全局替换转义符、全局转义下划线，**会破坏代码块里的内容** | 改用 mistune 官方 math 插件；定界符只在非代码区域转换 |
| 4 | mistune 只用了基础语法，**表格 / 任务列表 / 删除线 / 脚注全部不可用** | 显式开启常用插件 |
| 5 | `split("---", 2)` 解析 frontmatter，**正文里出现 `---` 就错位** | 严格只认文件开头的分隔符，兼容 YAML 列表写法 |
| 6 | 日期不校验，`2026-13-45` 也能参与排序 | 解析失败降级为"无日期"并警告 |
| 7 | 标签名直接当文件名，**带斜杠、冒号、空格就写出非法路径** | 统一 `slugify` + URL 编码 + 重名去重 |
| 8 | 构建只增不减，**删掉的文章在 `dist/` 里还留着幽灵页面** | `.build-manifest.json` 记录产物，只清理自己生成的文件 |
| 9 | 上传的图片/附件写进 `dist/static/`，而 `dist/` 被 gitignore，**重建或换机就永久丢图** | 统一写进 `static/`（进仓库）；`--clean` 也保护上传目录 |
| 10 | 没有 `.nojekyll`，GitHub Pages 的 Jekyll 会忽略下划线开头的文件 | 构建时自动生成 |
| 11 | 没有部署流程，`dist/` 又在 gitignore 里，**根本没法自动上线** | 提供 GitHub Actions 工作流，推送即部署 |
| 12 | `python -m blog clean -o .` 会把**整个项目目录删掉** | 拒绝根目录/上级目录/家目录，无构建清单时要求 `--yes` |
| 13 | 预览服务器绑定 `0.0.0.0`，同网段任何人都能打开编辑器改文章 | 默认只监听 `127.0.0.1`，要开放得显式 `--host` |
| 14 | `/api/posts/../../任意文件` 可读可写（**路径穿越**） | 文件名白名单 + 扩展名白名单 + `safe_join` 越界检查 |
| 15 | 单线程 `HTTPServer`，构建时页面直接卡住 | `ThreadingHTTPServer` |
| 16 | 路由用 `self.path` 精确匹配，`/editor?x=1` 直接 404 | 先用 `urlsplit` 剥掉查询串再路由 |
| 17 | 文件监听 2 秒轮询且无防抖，保存一次触发多轮全量重建 | 1 秒轮询 + 防抖 + 上传目录排除 |
| 18 | `_rebuild_index()` 名字叫"只重建首页"，实际做全量构建 | 删掉半吊子增量逻辑，统一一次全量构建 |
| 19 | `build_single` 和 `build_all` 两套几乎重复的渲染代码 | 合并为一个 `Builder` |
| 20 | 首页 HTML 直接拼在 Python 字符串里，改样式要动代码 | 首页也走模板 |
| 21 | 编辑器预览用 `innerHTML` 直接注入，**Markdown 里的脚本标签会执行** | 预览前做标签/属性清洗 |
| 22 | 编辑器保存后整页 `reload()`，滚动位置和状态全丢 | 局部刷新列表，不重载页面 |
| 23 | 编辑器无法新建/删除文章，上传没有大小与类型限制 | 支持新建、删除、32MB 上限、扩展名白名单 |
| 24 | 搜索索引不含正文，只能搜标题和标签 | 索引含正文纯文本，按标题/标签/正文加权 |
| 25 | `log_message(self, format, ...)` 遮蔽内建 `format` | 改名，并只记录 API 与错误 |
| 26 | 没有 404 页、favicon、RSS、sitemap、Open Graph | 全部补齐 |
| 27 | `output_dir.mkdir(exist_ok=True)` 少了 `parents=True`，多级目录会失败 | 修复 |
| 28 | Windows 控制台中文日志乱码 | 启动时把 stdout/stderr 重设为 UTF-8 |
| 29 | 文章和个人笔记混在同一个仓库，想公开生成器就得连文章一起公开 | `--content` 外置文章目录 + 私有草稿约定 + 双仓库方案 |

---

## 技术栈

- Python 3.10+（开发用 3.12）
- mistune — 唯一的第三方依赖
- 标准库：`pathlib`、`argparse`、`http.server`、`json`、`shutil`、`re`、`dataclasses`
- 前端：纯 HTML + CSS + 原生 JS，**零框架、零构建步骤**
- 可选 CDN：MathJax（公式）、highlight.js（代码高亮），加载失败不影响阅读
- 评论：utterances / giscus（数据存 GitHub Issues / Discussions）

---

## 常见问题

**Q：构建报 "No module named 'mistune'"？**
用虚拟环境里的 Python：`venv/Scripts/python.exe -m blog build`，或者先 `pip install mistune`。

**Q：改了文章，网站没变？**
`serve` 默认会自动重建；手动 `build` 的话注意浏览器缓存，
或者 `python -m blog build --clean` 清一遍。

**Q：部署后样式丢了 / 图片 404？**
先确认 `static/` 里的路径大小写没问题（Linux 区分大小写，Windows 不区分），
然后 `python -m blog check` 会把缺失的资源文件名直接列出来。

**Q：评论框显示"评论系统还没配置"？**
说明 `comments.repo` 为空，或者没安装 utterances / giscus 的 GitHub App。
见 [部署教程第 5 节](docs/deploy-guide.md)。

**Q：阅读次数怎么才能是"全网真实数据"？**
默认的本地计数只在各自浏览器里累计。想要全局数字，把 `metrics.provider`
换成 `abacus` 或 `goatcounter`。

**Q：为什么文章输出路径是文件名而不是标题？**
为了 URL 稳定。评论和阅读次数都按 URL 认文章，标题可以随时改，文件名别乱动。

**Q：不想让自己的文章出现在 blog-maker 这个仓库里？**
见上文"仓库怎么放"，或 [部署教程第 3 节](docs/deploy-guide.md)。
