# Extract Behance Moodboard

[![Latest release](https://img.shields.io/github/v/release/ilariaislwj-lang/extract-behance-moodboard?display_name=tag)](https://github.com/ilariaislwj-lang/extract-behance-moodboard/releases/latest)
[![Repository](https://img.shields.io/badge/GitHub-public-181717?logo=github)](https://github.com/ilariaislwj-lang/extract-behance-moodboard)

一个用于 Codex 的 Skill：只提取 **Behance 情绪板中实际收藏的项目**，逐个下载项目正文里的高清图片，并按项目名称建立独立文件夹。

它重点解决 Behance 页面中最容易出错的问题：情绪板下方会继续加载推荐项目，不能把页面里所有 `/gallery/` 链接都当成收藏内容。

## 功能

- 从 Behance 情绪板生成权威项目清单
- 仅处理收藏网格中的项目，排除推荐内容
- 提取项目正文中的 `project_modules` 图片
- 自动尝试 `max_3840_webp` 高清版本
- 排除项目封面、头像、图标和作者其他作品
- 按项目名称建立文件夹
- 按网页顺序将图片命名为 `001`、`002`、`003`……
- 支持 WebP、JPEG、PNG 和 GIF
- 支持断点续传、失败重试和特殊延迟加载项目补抓
- 输出 JSON 汇总并校验图片完整性

## 安装

### 让 Codex 安装

在 Codex 中调用内置的 Skill 安装器：

```text
使用 $skill-installer 安装这个 Skill：
https://github.com/ilariaislwj-lang/extract-behance-moodboard
```

### Windows PowerShell

```powershell
$skillHome = if ($env:CODEX_HOME) {
    Join-Path $env:CODEX_HOME "skills"
} else {
    Join-Path $HOME ".codex\skills"
}

New-Item -ItemType Directory -Force -Path $skillHome | Out-Null
git clone https://github.com/ilariaislwj-lang/extract-behance-moodboard.git `
    (Join-Path $skillHome "extract-behance-moodboard")
```

### macOS / Linux

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/ilariaislwj-lang/extract-behance-moodboard.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/extract-behance-moodboard"
```

安装后重新打开一个 Codex 任务，使 Skill 出现在可用 Skill 列表中。

### 下载发布包

也可以从 [GitHub Releases](https://github.com/ilariaislwj-lang/extract-behance-moodboard/releases) 下载已经校验过的 ZIP 包。解压后，将 `extract-behance-moodboard` 文件夹放进 Codex 的 `skills` 目录，再新建一个任务使用。

## 在 Codex 中使用

直接在请求中调用 Skill：

```text
使用 $extract-behance-moodboard 提取这个 Behance 情绪板，只处理已收藏项目：
https://www.behance.net/moodboard/123456/example
```

也可以使用当前 Chrome 页面：

```text
使用 $extract-behance-moodboard 读取当前 Chrome 中打开的 Behance 情绪板。
只导出我已经收藏的项目，每个项目单独建文件夹，文件夹使用项目名称。
```

指定输出位置：

```text
使用 $extract-behance-moodboard 提取这个情绪板，把结果保存到 D:\Behance\品牌灵感。
```

## 工作流程

Skill 会依次执行：

1. 在 Chrome 中识别情绪板标题、收藏项目网格和网格结束位置。
2. 在进入 `More Behance`、推荐项目或页脚前停止收集。
3. 按项目 ID 去重并保存项目清单。
4. 根据清单逐个下载项目正文图片。
5. 对普通解析无法读取的新项目或特殊项目，通过 Chrome 渲染后的 DOM 补抓图片地址。
6. 校验项目数量、空文件夹、临时文件和图片可解码性。

> 不要直接收集整个页面中的所有 `/gallery/` 链接。这样会把推荐项目错误地包含进来。

## 项目清单格式

Skill 在下载前生成 UTF-8 JSON 清单：

```json
{
  "moodboard": "品牌",
  "moodboard_url": "https://www.behance.net/moodboard/123456/example",
  "projects": [
    {
      "title": "Project name",
      "url": "https://www.behance.net/gallery/123456/Project-name"
    }
  ]
}
```

如果某个项目只能从 Chrome 渲染页面读取图片，可以加入 `image_urls`：

```json
{
  "title": "Special lazy-loaded project",
  "url": "https://www.behance.net/gallery/123456/Project-name",
  "image_urls": [
    "https://mir-s3-cdn-cf.behance.net/project_modules/1400_webp/example.png"
  ]
}
```

## 直接使用下载脚本

Skill 内置了一个清单驱动的下载脚本：

```powershell
python scripts/download_manifest.py `
  --manifest moodboard-projects.json `
  --output extracted-images `
  --workers 4
```

macOS / Linux：

```bash
python3 scripts/download_manifest.py \
  --manifest moodboard-projects.json \
  --output extracted-images \
  --workers 4
```

只检查项目能够发现多少张图片，不进行下载：

```bash
python3 scripts/download_manifest.py \
  --manifest moodboard-projects.json \
  --probe-only \
  --limit 3
```

### 参数

| 参数 | 说明 |
| --- | --- |
| `--manifest` | 必填，项目清单 JSON 路径 |
| `--output` | 输出文件夹；省略时根据清单名称自动生成 |
| `--workers` | 并行项目数，默认 `4`，允许 `1–12` |
| `--limit` | 只处理清单中的前 N 个项目，适合测试 |
| `--probe-only` | 只探测图片数量，不下载文件 |

## 输出结构

```text
情绪板名称_behance_images/
├── Project A/
│   ├── 001.webp
│   ├── 002.webp
│   └── 003.png
├── Project B/
│   ├── 001.jpg
│   └── 002.webp
└── _extract-summary.json
```

Windows 文件夹名称中不允许的字符会替换成可读的全角字符，例如：

- `/` → `／`
- `|` → `｜`
- `:` → `：`
- `?` → `？`
- `*` → `＊`

## 依赖

- Codex Skill 支持
- Chrome 浏览器控制能力，用于准确识别收藏网格和处理特殊项目
- Python 3.9 或更高版本
- 可访问 Behance 及其图片 CDN 的网络环境
- Pillow 为可选依赖；安装后可进行图片解码校验

## 注意事项

- 请只下载你有权访问和保存的内容。
- 项目的版权仍属于原作者。
- 不要使用本 Skill 绕过登录、访问限制、CAPTCHA、付费墙或地区限制。
- Skill 不会读取或保存浏览器 Cookie、密码或会话令牌。
- Behance 页面结构可能变化；当收藏数量与清单数量不一致时，应先停止并重新确认收藏网格边界。

## 隐私、安全与支持

- [隐私政策](docs/PRIVACY.md)
- [使用条款](docs/TERMS.md)
- [支持说明](docs/SUPPORT.md)
- [问题反馈](https://github.com/ilariaislwj-lang/extract-behance-moodboard/issues)

本项目可作为 Skills-only 插件提交到 OpenAI 的公共插件目录。公开上架仍需经过平台身份验证和审核；仓库中的发布包、测试用例及提交材料用于完成该流程。
