# Blog — 极简静态博客生成器

一个用纯 Python 标准库（+ `mistune`）从零搭建的静态博客生成器，适合学习 Python 基础的项目（本人使用ai编程编写）。

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\python.exe -m pip install mistune

# 2. 构建博客
venv\Scripts\python.exe -m blog build

# 3. 本地预览
venv\Scripts\python.exe -m blog serve
# 浏览器打开 http://127.0.0.1:8000
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `python -m blog build` | 构建博客到 `dist/` |
| `python -m blog build -o public` | 构建到自定义目录 |
| `python -m blog serve` | 启动预览服务器 + 文件监听自动重建 |
| `python -m blog serve -o public` | 预览自定义目录 |
| `python -m blog clean` | 清空输出目录 |

## 项目结构

```
blog/
├── blog/                  # Python 包
│   ├── __init__.py
│   ├── __main__.py        # CLI 入口 (argparse)
│   ├── builder.py         # 构建逻辑
│   └── server.py          # 预览服务器
├── content/               # 源文章 (.txt)
├── templates/             # HTML 模板
│   ├── base.html          # 公共骨架
│   ├── post.html          # 文章页
│   ├── tags.html          # 标签总览
│   ├── tag.html           # 标签过滤页
│   └── search.html        # 搜索页
├── static/                # 静态资源 (CSS)
├── dist/                  # 构建输出
├── build.py               # 向后兼容入口
├── serve.py               # 向后兼容入口
└── README.md
```

## 写文章

在 `content/` 目录下创建 `.txt` 文件，使用 frontmatter 格式：

```markdown
---
title: 文章标题
date: 2026-07-27
tags: python, 教程
---
## 正文标题

正文支持 **Markdown** 语法。

- 列表项
- 代码 `inline code`

> 引用块
```

## 功能特性

- Markdown 渲染（基于 `mistune`）
- frontmatter 元数据解析（标题、日期、标签）
- 文章按日期降序排列
- 标签总览 + 标签过滤页
- 全文模糊搜索（客户端 JS）
- 字数统计
- 自定义模板引擎（`{{ }}` 占位符）
- 本地预览服务器 + 文件监听自动重建
- 优雅降级（缺失日期、解析失败不中断构建）

## 学习路径

本项目按以下步骤逐步构建，适合 Python 初学者：

| 步骤 | 学到的知识点 |
|------|-------------|
| 硬编码 HTML 生成 | 文件 I/O、字符串格式化 |
| frontmatter 解析 | `split()`、`dict`、逐行解析 |
| 多文章 + 排序 | `glob`、`lambda`、列表数据结构 |
| 模板引擎 | 占位符替换、关注点分离 |
| Markdown 渲染 | 第三方库引入、MD→HTML |
| 预览服务器 | `http.server`、文件监听 |
| CLI 工程化 | `argparse`、`try-except` |

## 技术栈

- Python 3.10+
- `mistune`（Markdown 渲染）
- 标准库：`pathlib`、`argparse`、`http.server`、`json`、`shutil`
- 零前端框架，纯 HTML + CSS + 少量 JS
