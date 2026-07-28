from pathlib import Path
import json  # 导出搜索索引
import shutil
import re
import mistune


def parse_meta(text):
    """解析 frontmatter，返回 (meta_dict, body_text)"""
    parts = text.split("---", 2)

    if len(parts) < 3:
        return {}, text.strip()

    meta_block = parts[1].strip()
    body = parts[2].strip()

    meta = {}
    for line in meta_block.split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()

    return meta, body


def render(template_path, **kwargs):
    """读取模板并用关键字参数替换所有 {{ key }} 占位符"""
    template = Path(template_path).read_text(encoding="utf-8")

    for key, value in kwargs.items():
        # re.sub 精确匹配 {{ key }}，不会误伤 {{ other_key }} 中的子串
        # 用 lambda 包裹 value，避免 value 中的反斜杠被 re 解释为转义序列
        pattern = r'\{\{\s*' + re.escape(key) + r'\s*\}\}'
        template = re.sub(pattern, lambda _: value, template)

    return template


def _render_body(body):
    """Markdown 渲染，包含 LaTeX 数学公式预处理"""
    # 步骤 1：LaTeX 定界符 → MathJax 标准格式（必须在 markdown 之前）
    #   \( ... \) → $ ... $（行内），\[ ... \] → $$ ... $$（块级）
    body = body.replace(r'\[', '$$').replace(r'\]', '$$')
    body = body.replace(r'\(', '$').replace(r'\)', '$')

    # 步骤 2：保护数学区域中的下划线，防止被 mistune 解析为斜体
    #   例如 $x_i$ 中的 _i 会被转为 <em>i</em>，破坏公式
    def _escape_underscores(m):
        return m.group(0).replace('_', r'\_')
    # 先处理 $$...$$（块级），用 DOTALL 支持跨行公式
    body = re.sub(r'\$\$(.+?)\$\$', _escape_underscores, body, flags=re.DOTALL)
    # 再处理 $...$（行内）
    body = re.sub(r'\$(.+?)\$', _escape_underscores, body)

    try:
        return mistune.html(body)
    except Exception as e:
        print(f"  [警告] Markdown 渲染失败: {e}，使用原文")
        return f"<pre>{body}</pre>"


def _count_words(text):
    """统计正文的非空白字符数，简单但够用的字数估算"""
    return len(text.replace("\n", "").replace(" ", ""))


def _fix_static_paths(html, prefix):
    """修正 HTML 中 static/ 资源的相对路径，用于子目录页面"""
    # src="static/..." → src="{prefix}static/..."
    html = html.replace('src="static/', f'src="{prefix}static/')
    html = html.replace("src='static/", f"src='{prefix}static/")
    # href="static/..." → href="{prefix}static/..."
    html = html.replace('href="static/', f'href="{prefix}static/')
    html = html.replace("href='static/", f"href='{prefix}static/")
    return html


def build_all(output_dir="dist"):
    """执行完整构建：扫描文章 -> 排序 -> 生成文章页 + 首页"""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # --- 第 1 步：扫描所有文章（带异常保护）---
    all_posts = []
    tag_map = {}  # {tag_name: [post_dict, ...]}

    for txt_file in Path("content").glob("*.txt"):
        if txt_file.name == "friends.txt":
            # 友链文件由专门的生成逻辑处理，不作为文章
            continue
        try:
            raw_text = txt_file.read_text(encoding="utf-8")
            meta, body = parse_meta(raw_text)
        except Exception as e:
            print(f"[警告] 跳过 '{txt_file.name}': {e}")
            continue

        date = meta.get("date", "")
        if not date:
            print(f"[警告] '{txt_file.name}' 缺少日期，使用默认值 1970-01-01")
            date = "1970-01-01"

        tags_raw = meta.get("tags", "")
        # 逗号分隔的标签列表，strip 去掉空格
        tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()]

        post = {
            "title": meta.get("title", "无标题"),
            "date": date,
            "tags": tags_raw,
            "tag_list": tag_list,       # 内部使用，不输出到 JSON
            "body": body,
            "html_file": "posts/" + txt_file.stem + ".html",
            "word_count": _count_words(body),
        }
        all_posts.append(post)

        # 收集标签 -> 文章映射
        for tag in tag_list:
            if tag not in tag_map:
                tag_map[tag] = []
            tag_map[tag].append(post)

    if not all_posts:
        print("未找到任何文章，构建终止。")
        return

    # --- 第 2 步：按日期降序排序 ---
    all_posts.sort(key=lambda p: p["date"], reverse=True)

    for post in all_posts:
        print(f"[{post['date']}] {post['title']} -> {post['html_file']}")

    # --- 第 3 步：逐篇生成文章页 ---
    posts_dir = output_dir / "posts"
    posts_dir.mkdir(exist_ok=True)

    for post in all_posts:
        body_html = render("templates/post.html",
                           title=post["title"],
                           date=post["date"],
                           tags=post["tags"],
                           word_count=str(post["word_count"]),
                           body=_render_body(post["body"]))

        html = render("templates/base.html",
                      title=post["title"],
                      content=body_html,
                      static_path="../static/",
                      root_path="../")

        # 修正文章内图片/附件等 static/ 资源的相对路径
        html = _fix_static_paths(html, "../")

        output_file = output_dir / post["html_file"]
        output_file.write_text(html, encoding="utf-8")
        print(f"已生成: {output_file}")

    print(f"共处理 {len(all_posts)} 篇文章")

    # --- 第 4 步：生成首页 ---
    links = "\n".join(
        f'    <li><a href="{p["html_file"]}">{p["title"]}</a> - {p["date"]} '
        f'({p["word_count"]}字)</li>'
        for p in all_posts
    )

    index_body = f"""<h1>我的博客</h1>
<p class="subtitle">{len(all_posts)} 篇文章</p>
<ul class="post-list">
{links}
</ul>"""

    index_html = render("templates/base.html",
                        title="我的博客",
                        content=index_body,
                        static_path="static/",
                        root_path="")

    index_file = output_dir / "index.html"
    index_file.write_text(index_html, encoding="utf-8")
    print(f"首页已生成: {index_file}")

    # --- 第 5 步：生成标签总览页 ---
    tags_dir = output_dir / "tags"
    tags_dir.mkdir(exist_ok=True)

    tag_links = "\n".join(
        f'    <a href="{tag}.html" class="tag">{tag}'
        f'<span class="count">({len(posts)})</span></a>'
        for tag, posts in sorted(tag_map.items())
    )

    tags_html = render("templates/tags.html", tag_list=tag_links)
    tags_full = render("templates/base.html",
                       title="标签",
                       content=tags_html,
                       static_path="../static/",
                       root_path="../")
    tags_full = _fix_static_paths(tags_full, "../")
    (tags_dir / "index.html").write_text(tags_full, encoding="utf-8")
    print(f"标签页已生成: tags/index.html ({len(tag_map)} 个标签)")

    # --- 第 6 步：生成每个标签的过滤页 ---
    # 这些页面在 tags/ 子目录下，文章链接需要 ../ 前缀
    for tag, posts in sorted(tag_map.items()):
        posts.sort(key=lambda p: p["date"], reverse=True)
        tag_links = "\n".join(
            f'    <li><a href="../{p["html_file"]}">{p["title"]}</a> - {p["date"]}</li>'
            for p in posts
        )
        tag_body = render("templates/tag.html",
                          tag=tag,
                          count=str(len(posts)),
                          links=tag_links)
        tag_full = render("templates/base.html",
                          title=f"标签: {tag}",
                          content=tag_body,
                          static_path="../static/",
                          root_path="../")
        tag_full = _fix_static_paths(tag_full, "../")
        (tags_dir / f"{tag}.html").write_text(tag_full, encoding="utf-8")

    print(f"标签过滤页已生成: {len(tag_map)} 个")

    # --- 第 7 步：导出搜索索引（posts.json）---
    # 去掉 body 和内部字段 tag_list，大幅减小 JSON 体积
    search_data = [
        {k: v for k, v in p.items() if k not in ("tag_list", "body")}
        for p in all_posts
    ]
    json_file = output_dir / "posts.json"
    json_file.write_text(
        json.dumps(search_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"搜索索引已生成: {json_file}")

    # --- 第 8 步：生成搜索页 ---
    search_body = render("templates/search.html")
    search_full = render("templates/base.html",
                         title="搜索",
                         content=search_body,
                         static_path="static/",
                         root_path="")
    (output_dir / "search.html").write_text(search_full, encoding="utf-8")
    print(f"搜索页已生成: search.html")

    # --- 第 9 步：生成友链页 ---
    friends_file = Path("content") / "friends.txt"
    if friends_file.is_file():
        raw = friends_file.read_text(encoding="utf-8")
        friends_meta, friends_body = parse_meta(raw)
        friends_html = render("templates/friends.html",
                              friend_links=_render_body(friends_body))
        friends_dir = output_dir / "friends"
        friends_dir.mkdir(exist_ok=True)
        friends_full = render("templates/base.html",
                              title="友链",
                              content=friends_html,
                              static_path="../static/",
                              root_path="../")
        friends_full = _fix_static_paths(friends_full, "../")
        (friends_dir / "index.html").write_text(friends_full, encoding="utf-8")
        print(f"友链页已生成: friends/index.html")

    # --- 第 10 步：拷贝静态资源 ---
    # copytree 整目录拷贝，dirs_exist_ok=True 允许目标已存在
    static_src = Path("static")
    if static_src.is_dir():
        static_dst = output_dir / "static"
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)
        print(f"静态资源已拷贝: {static_dst}")


def build_single(txt_file, output_dir="dist"):
    """只重建单篇文章，用于 serve 的增量构建"""
    output_dir = Path(output_dir)
    txt_file = Path(txt_file)

    try:
        raw_text = txt_file.read_text(encoding="utf-8")
        meta, body = parse_meta(raw_text)
    except Exception as e:
        print(f"[警告] 增量构建跳过 '{txt_file.name}': {e}")
        return

    date = meta.get("date", "")
    if not date:
        date = "1970-01-01"

    tags = meta.get("tags", "")
    html_name = "posts/" + txt_file.stem + ".html"
    body_html = render("templates/post.html",
                       title=meta.get("title", "无标题"),
                       date=date,
                       tags=tags,
                       word_count=str(_count_words(body)),
                       body=_render_body(body))

    html = render("templates/base.html",
                  title=meta.get("title", "无标题"),
                  content=body_html,
                  static_path="../static/",
                  root_path="../")

    # 修正文章内图片/附件等 static/ 资源的相对路径
    html = _fix_static_paths(html, "../")

    output_file = output_dir / html_name
    output_file.write_text(html, encoding="utf-8")
    print(f"[增量] 已更新: {output_file}")
