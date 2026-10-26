# 部署与上线教程

从零把博客发布到 GitHub Pages，一步一步来。

> 本教程对应 v2。所有命令都在**项目根目录**执行。
> 如果还没装依赖：`python -m venv venv` 然后 `venv\Scripts\python.exe -m pip install mistune`。

---

## 目录

1. [先决定：仓库怎么分](#1-先决定仓库怎么分)
2. [方案 A：单仓库（最快上线）](#2-方案-a单仓库最快上线)
3. [让文章原文不进公开仓库](#3-让文章原文不进公开仓库)
4. [Pages 设置：Source 选 GitHub Actions](#4-pages-设置source-选-github-actions)
5. [安装 utterances 让评论可用](#5-安装-utterances-让评论可用)
6. [确认站点地址与 base_path](#6-确认站点地址与-base_path)
7. [上线后自检清单](#7-上线后自检清单)
8. [排错表](#8-排错表)

---

## 1. 先决定：仓库怎么分

GitHub Pages 的构建跑在 GitHub 的服务器上，它**只能读到仓库里的文件**。
所以"文章原文不进仓库"和"CI 自动构建"天生有点冲突，得选一个平衡点。

| | 结构 | 文章 md 源文件是否公开 | 自动化 | 适合谁 |
|---|---|---|---|---|
| **A** | 一个仓库：生成器 + 你的文章 | 公开（仓库是公开的话） | 全自动 | 不在乎源码被看到，想最快上线 |
| **B** | 生成器仓库 + 博客仓库分开 | 仍然公开，但只在你的博客仓库里 | 全自动 | 想让 `blog-maker` 保持干净、能给别人当模板 |
| **C** | 博客仓库公开 + **文章放私有仓库**，Actions 用 token 拉取 | **不公开** | 全自动 | 完全不想让 md 原文出现在公开仓库 |

> **一个容易被忽略的事实**：网站上的文章本来就是公开可读的，所以"文章内容保密"通常不成立。
> 真正值得处理的是 **md 源文件**（可能混着草稿、内部笔记）和**仓库整洁度**。
> 如果你只是怕没写完的稿子被提交，用第 3.4 节的"私有草稿"约定就够了，一行结构都不用改。

**推荐路线**：先按 **方案 A** 跑通，确认评论和样式都正常；
等确实觉得 `blog-maker` 不该混着自己的文章，再升级到 B 或 C。

---

## 2. 方案 A：单仓库（最快上线）

### 2.1 本地先跑一遍

```bash
python -m blog check
python -m blog build --clean
python -m blog serve
```

浏览器打开 http://127.0.0.1:8000 ，确认首页、文章页、搜索页、评论区都正常。
`check` 应当输出"没有发现问题。"

### 2.2 改成本站配置

编辑 `blog.config.json`：

```json
{
  "site": {
    "title": "我的博客",
    "description": "站点描述",
    "author": "huan201",
    "url": "https://huan201.github.io/",
    "base_path": "/",
    "github": "https://github.com/huan201/blog-maker"
  },
  "comments": { "provider": "utterances", "repo": "huan201/blog-maker" }
}
```

两个关键字段：

- `site.url`：站点**完整地址**，RSS / sitemap / 分享卡片用它拼绝对链接。
- `site.base_path`：站点在域名下的**路径前缀**。根路径填 `"/"`，
  部署在 `/仓库名/` 下就填 `"/仓库名/"`。判定方法见第 6 节。

### 2.3 提交并推送

```bash
git status --short
git add .
git commit -m "v2：新界面 + 评论 + 阅读计数"
git push origin main
```

推送前用 `git status --short` 扫一眼，正常应该只有
`content/`、`templates/`、`static/`、`blog/`、`blog.config.json`、`.github/`；
**不应该**出现 `dist/`、`venv/`、`__pycache__/`。

---

## 3. 让文章原文不进公开仓库

### 3.1 方案 B：拆成两个仓库

**仓库 1：`blog-maker`（生成器模板）**
只有代码、模板、样式和一篇示例文章，可以给别人当模板。

**仓库 2：`huan201.github.io`（你的博客）**
放 `content/`、`blog.config.json`、`templates/`、`static/` 和一份生成器副本。
**Pages 从这个仓库部署**——因为仓库名是 `用户名.github.io`，站点地址正好是
`https://huan201.github.io/`（也就是你说的根路径）。

```powershell
# 1) 先在 GitHub 网页新建空仓库 huan201.github.io（不要勾选任何初始化文件）

# 2) 本地复制一份（排除 .git / venv / dist / __pycache__）
robocopy . ..\huan201.github.io /E /XD .git venv dist __pycache__ .github

# 3) 建立独立仓库并推送
cd ..\huan201.github.io
git init
git add .
git commit -m "初始化博客"
git remote add origin https://github.com/huan201/huan201.github.io.git
git push -u origin main
```

然后把 `blog.config.json` 里的 `site.url`、`site.github`、
`comments.repo` 都改成新仓库。

> 生成器以后更新了怎么办？把 `blog/`、`templates/`、`static/css`、
> `static/js` 从 `blog-maker` 复制过来覆盖，文章和配置不动就行。

### 3.2 方案 B+：文章放在仓库外

`build` / `serve` 支持用 `--content` 指定任意文章目录：

```bash
python -m blog build --content "D:\我的文章"
python -m blog serve --content "D:\我的文章"
```

也可以写进配置（相对路径按项目根目录解析，也可以直接写绝对路径）：

```json
"build": { "content_dir": "D:/我的文章" }
```

注意：这样**本地**构建没问题，但 GitHub Actions 访问不到你电脑上的目录。
要走 CI 自动部署，得配合下面的私有内容仓库。

### 3.3 方案 C：文章放私有仓库，Actions 用 token 拉取

**第 1 步 · 建私有内容仓库**

新建 `huan201/blog-content`，**设为 Private**，把 `content/` 里的文章推上去。

**第 2 步 · 造一个只读 token**

GitHub → 头像 → **Settings** → 左栏最下 **Developer settings** →
**Personal access tokens** → **Fine-grained tokens** → **Generate new token**：

- Token name：随便，例如 `blog-deploy`
- Expiration：按需（建议 90 天，到期换一个）
- Repository access：选 **Only select repositories** → 勾 `blog-content`
- Permissions → Repository permissions → **Contents** → 设为 **Read-only**

生成后复制那串 token（只显示一次）。

**第 3 步 · 把 token 存进博客仓库的 Secrets**

博客仓库 → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**：

- Name：`CONTENT_TOKEN`
- Secret：粘贴刚才的 token

**第 4 步 · 改工作流**

把 `.github/workflows/deploy.yml` 里"构建站点"那一步替换成：

```yaml
      - name: 检出私有文章仓库
        uses: actions/checkout@v4
        with:
          repository: huan201/blog-content
          token: $$ secrets.CONTENT_TOKEN $$
          path: .content-private

      - name: 构建站点
        run: python -m blog build --clean --quiet --content .content-private
```

**第 5 步 · 本地也指向私有仓库的克隆**

```bash
git clone https://github.com/huan201/blog-content.git D:\blog-content
python -m blog serve --content D:\blog-content
```

### 3.4 最低成本：私有草稿约定

如果你只是怕**没写完的稿子**被提交，什么都不用改结构：

- 文件名以 `_` 开头的 `.txt` 会被构建器和编辑器**完全跳过**，
  例如 `content/_草稿-神经网络重写.txt`
- frontmatter 里写 `draft: true` 的文章，默认不出现在站点上
  （只有加 `--drafts` 才会构建）
- 再建一个 `content/_drafts/` 目录并写进 `.gitignore`：

```gitignore
content/_drafts/
content/*.draft.txt
```

---

## 4. Pages 设置：Source 选 GitHub Actions

**这一步只做一次，但必须做对**，否则推了代码也不会自动上线。

1. 打开浏览器，进入**要部署的那个仓库**。
   （方案 A 是 `blog-maker`；方案 B/C 是 `huan201.github.io`。）
2. 点仓库顶部导航栏最右边的 **Settings**（齿轮图标）。
   地址形式：`https://github.com/huan201/blog-maker/settings`
3. 左侧边栏往下滚，点 **Pages**。
   地址形式：`https://github.com/huan201/blog-maker/settings/pages`
4. 在 **Build and deployment** 区块找到 **Source** 下拉框。
5. 把 Source 从 `Deploy from a branch` 改成 **`GitHub Actions`**。
   **不要**选 `Deploy from a branch`，也**不要**建 `gh-pages` 分支——
   本项目是让 Actions 直接上传构建产物。
6. 选完一般会自动保存（老界面可能需要点一下 **Save**）。
   页面会显示一行 `Your site is ready to be published at ...`
7. 到仓库顶部 **Actions** 标签页 → 左侧点 **构建并部署到 GitHub Pages** →
   右侧 **Run workflow** → 分支选 `main` → 绿色 **Run workflow** 按钮。
8. 等任务里 **build** 和 **deploy** 两个方块都变成 ✅（第一次约 1～3 分钟）。
9. 回到 **Settings → Pages**，顶部出现
   **`Your site is live at https://...`**，点 **Visit site** 即可。

> 之后每次 `git push` 到 `main` 都会自动重新构建部署。
> 部署过程中站点会短暂 404，属正常现象。

**如果第 7 步找不到这个工作流**，说明工作流文件没提交上去：

```bash
git add .github/workflows/deploy.yml
git commit -m "添加部署工作流"
git push
```

（`.gitignore` 里不能有忽略 `.github` 的规则。）

---

## 5. 安装 utterances 让评论可用

本站默认用 [utterances](https://utteranc.es)，评论存进仓库的 **Issues**。
好处是：重建、重新部署、换电脑都不会丢评论，因为评论根本不在静态站点里。

### 5.1 前提

- 托管评论的仓库必须是 **Public**。
- `blog.config.json` 里 `comments.repo` 要写成 `用户名/仓库名`。

### 5.2 安装 App（只需一次）

1. 打开 https://github.com/apps/utterances
2. 点绿色的 **Install** 按钮。
3. 提示选择账号时，选你的个人账号 `huan201`。
4. **Repository access** 选 **Only select repositories**。
5. 下拉列表里选 **`huan201/blog-maker`**（方案 B/C 就选你的博客仓库）。
6. 点 **Install & Authorize**；如果弹出授权页，输入 GitHub 密码确认。
7. 安装完毕会跳回 utterances 首页，说明装好了。

### 5.3 回网站试一下

1. 打开任意文章页，滚到最底部，会看到评论框
   （第一次显示 `Sign in with GitHub to comment`）。
2. 点它 → **Authorize utterances** → 允许。
3. 写一句测试评论，点 **Comment**。
4. 去仓库 **Issues** 标签页，会看到一个以文章路径命名的 Issue
   （例如标题是 `/posts/mlp.html`），评论就在里面。
   你也可以直接在 Issue 里回复，网站上会同步显示。

### 5.4 想换成 giscus？

1. 仓库 → **Settings** → **General** → 往下拉 **Features** → 勾选 **Discussions**。
2. 打开 https://giscus.app ，填入仓库名，按页面提示拿到 `repo_id` 和 `category_id`。
3. 改 `blog.config.json`：

```json
"comments": {
  "provider": "giscus",
  "repo": "huan201/blog-maker",
  "repo_id": "R_kgDOxxxxxxx",
  "category": "Announcements",
  "category_id": "DIC_kwDOxxxxxxxx",
  "mapping": "pathname"
}
```

再去 https://github.com/apps/giscus 装一次 App，步骤和 utterances 一样。

> 如果 `provider` 写了 giscus 但 ID 漏填，构建时会自动降级成 utterances 并给出警告，
> 页面不会变成空白。

### 5.5 评论是怎么"跟住"文章的

评论按 **页面路径** 认文章（`mapping: pathname`）。
本项目的输出路径直接沿用 `content/` 里的文件名，所以只要**不重命名文章文件**，
评论就永远挂在同一篇文章上。改标题随便改，改文件名评论会"另起一页"。

---

## 6. 确认站点地址与 base_path

### 6.1 先判断地址属于哪种

| 仓库名 | 站点地址 |
|---|---|
| `<用户名>.github.io` | `https://<用户名>.github.io/` ← 根路径 |
| 其它名字，例如 `blog-maker` | `https://<用户名>.github.io/blog-maker/` ← 子路径 |

**核实方法**：Settings → Pages → 顶部 **Your site is live at ...** 那一行，
那是真实地址，照抄即可。

> 你提到站点是 `https://huan201.github.io/`（根路径），
> 那对应的仓库名必须是 `huan201.github.io`。
> 如果仓库仍叫 `blog-maker`，真实地址就是 `https://huan201.github.io/blog-maker/` 。
> 二者选其一，别混用。

### 6.2 按地址改配置

**根路径（`https://huan201.github.io/`）**

```json
"site": {
  "url": "https://huan201.github.io/",
  "base_path": "/"
}
```

**子路径（`https://huan201.github.io/blog-maker/`）**

```json
"site": {
  "url": "https://huan201.github.io/blog-maker/",
  "base_path": "/blog-maker/"
}
```

### 6.3 改错了会怎样

- **站内所有链接都是相对路径**，所以即使 `base_path` 写错，首页、文章、标签、搜索
  都能正常点击，样式和脚本也正常。
- 真正会错的只有三处：**404 页的返回按钮**、**robots.txt 里的 Sitemap 地址**、
  以及 **RSS / sitemap / 分享卡片里的绝对链接**。
- 结论：不确定就先别改，站点照样能用；想做到完美再按 6.2 填。

改完重新构建并推送：

```bash
python -m blog build --clean
git add blog.config.json
git commit -m "修正站点地址"
git push
```

---

## 7. 上线后自检清单

打开线上地址，逐条对一遍：

- [ ] 首页能看到文章卡片：标题、日期、字数、"阅读 N 次"
- [ ] 导航 **标签** → 标签卡片能点进去，里面是该标签的文章
- [ ] 导航 **搜索** → 输入"神经"立刻出结果并高亮
- [ ] 点开一篇文章：**右侧目录**出现且滚动时高亮、**代码块有复制按钮**、**公式正常渲染**
- [ ] 页面最底部有评论框（第一次需登录 GitHub 授权）
- [ ] 右上角 🌙 / ☀️ 能切深浅色，刷新后记得你的选择
- [ ] 手机打开布局不溢出
- [ ] 访问一个不存在的路径（例如 `/abc`），看到 404 页而不是 GitHub 默认页
- [ ] `/feed.xml` 和 `/sitemap.xml` 能打开

---

## 8. 排错表

| 现象 | 原因 | 解决 |
|---|---|---|
| Actions 跑完了但站点 404 | Pages 的 Source 没设成 GitHub Actions | 重做第 4 节 |
| Actions 页面看不到工作流 | 工作流文件没提交 | `git add .github && git commit && git push` |
| 构建 job 报 `No module named 'mistune'` | 依赖没装 | 检查工作流里的 `pip install mistune` 是否被删 |
| 页面样式全丢 | `static/` 没提交，或路径大小写不一致 | `git status` 检查；Linux 区分大小写 |
| 图片 404 | 图片只在 `dist/`，没放进 `static/` | 把图移到 `static/images/`；`python -m blog check` 会列出缺失的文件名 |
| 评论框显示"评论系统还没配置" | `comments.repo` 为空 | 填 `用户名/仓库名` |
| 评论框一直转圈 | 没装 utterances App，或仓库是私有的 | 重做第 5 节；仓库改 Public |
| 评论跑到别的文章下面 | 改了文章文件名 | 文件名即 URL，改回来即可 |
| 阅读次数一直是"暂无阅读" | 首次访问，或用了无痕模式 | 正常，本地计数要写一次 |
| 想要跨设备统一的阅读数 | 默认 `local` 只在本机累加 | 改用 `abacus` / `goatcounter`，见 README |
| `check` 报"模板缺少占位符" | 模板里写了没人传的值 | 按提示修正模板或构建器 |
| Windows 控制台中文乱码 | 代码页不是 UTF-8 | 程序已自动切 UTF-8；仍乱码可 `chcp 65001` |

---

## 附：一次完整的发布流程备忘

```bash
# 1. 写文章
python -m blog new "我的新文章"

# 2. 本地看效果（改文件会自动重建）
python -m blog serve        # http://127.0.0.1:8000

# 3. 自检
python -m blog check

# 4. 提交推送
git add content/ static/ templates/ blog/ blog.config.json
git commit -m "新增文章"
git push                    # 剩下的交给 GitHub Actions

# 5. 1~3 分钟后刷新线上地址
```
