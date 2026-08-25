# First-Run Checklist

Updated: 2026-08-24
Status: active

## 目标

让任何人拿到这个仓库后，能在 10 分钟内把 Workbench 跑起来，无需依赖原作者记忆或明文密钥。

---

## 第一步：克隆仓库 / 确认仓库在本机

```bash
git clone <仓库地址>
cd PPT-AI-Assistant
```

---

## 第二步：搭建 Python 环境（my-ppt-skill 子模块）

```bash
cd my-ppt-skill
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat

# macOS / Linux
source .venv/bin/activate

python -m pip install -e .
```

如需导入 PDF，再按需安装 PDF 可选依赖：

```bash
python -m pip install -r scripts/requirements-pdf.txt -c scripts/constraints.txt
```

> **注意**：Python 版本需为 3.11 或更高；可先运行 `python --version` 检查。`python -m pip install -e .` 是 Workbench 首次运行所需的默认安装，不包含 PyMuPDF，也不会改动任何代码。
> 如果报 "Multiple top-level packages" 错误，说明 pyproject.toml 版本过旧，请先 `git pull`。

只有需要额外的 SVG/PDF 栅格渲染 fallback 时，才安装可选依赖：

```bash
python -m pip install -r requirements-optional.txt
```

---

## 第三步：配置 API Key（回到仓库根目录）

Workbench 首次运行不需要创建或维护 `my-ppt-skill/.env`。那个模板用于其他图像后端 / 独立流水线场景，不属于本轮 Workbench 最小链路。

返回仓库根目录：

```bash
cd ..
```

现在已回到仓库根目录。在根目录创建 `.env`，写入 Workbench 用的 key：

```
# 项目根 .env（Workbench 读取）
WORKBENCH_DEEPSEEK_API_KEY=你的key
```

> **安全提示**：`.env` 文件已在 `.gitignore` 中，不会进入版本库。
> **永远不要把明文 key 提交进 git，也不要在对话或文档中粘贴真实 key。**

---

## 第四步：创建 Workbench 本地配置

在 `workbench/` 目录创建 `settings.local.json`（参考 `settings.local.example.json`）：

```json
{
  "generation_provider": "deepseek",
  "deepseek_api_key_env": "WORKBENCH_DEEPSEEK_API_KEY",
  "deepseek_model": "deepseek-v4-flash",
  "deepseek_base_url": "https://api.deepseek.com/v1"
}
```

> `deepseek_api_key_env` 是引用环境变量名，不是 key 本身。
> 不要写 `deepseek_api_key: "sk-..."` —— 明文 key 会被 healthcheck 拦截。

---

## 第五步：运行健康检查

在项目根目录执行：

```bash
python -m workbench.healthcheck
```

预期结果（全部 pass）：

```json
{
  "status": "pass",
  "checks": {
    "python": { "status": "pass" },
    "paths":  { "status": "pass" },
    "settings": { "status": "pass", "detail": "env-ref secret fields configured: ..." }
  }
}
```

---

## 第六步：启动 Workbench

```bash
# 项目根目录
python start_workbench.py
```

然后打开浏览器访问：**http://127.0.0.1:8765**

> `start_workbench.py` 会自动从根目录 `.env` 加载环境变量，然后启动服务器。
> 无需手动 `export` 或 `set` 环境变量。

---

## 常见问题

### healthcheck 报 `plaintext secret fields detected`

`settings.local.json` 里有明文 key（如 `deepseek_api_key: "sk-..."`）。
改为 env-ref 模式：删掉明文 key，改为 `deepseek_api_key_env: "WORKBENCH_DEEPSEEK_API_KEY"`，
并把真实 key 写入根目录 `.env`。

### healthcheck 报 `required repo paths not found`

不在仓库根目录，或 clone 不完整。切换到项目根目录再运行。

### healthcheck 报 `configured env refs missing values`

`settings.local.json` 中引用的环境变量不存在或为空。按第三步在根目录 `.env` 填写对应 Provider 的 key，或在当前终端安全注入同名环境变量，然后重新运行 healthcheck。

### Workbench 启动但生成功能不可用

没有可用 key 时可以浏览界面，但不能调用模型。按第三步配置 key 后重启即可。

### `pip install -e .` 失败

确认在 `my-ppt-skill/` 目录下执行，且 venv 已激活。

### cairosvg 报 `no library called cairo-2`

Windows 上缺系统级 Cairo 原生库。SVG 渲染会自动降级为系统浏览器（Edge/Chrome），
通常无需额外处理。如需安装 Cairo，参考 [GTK for Windows](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer)。

---

## 阅读顺序（了解项目）

看完 first-run 之后，建议按以下顺序阅读：

1. `AGENTS.md` — 公开贡献协议与核心原则
2. `docs/development/SDD.md` — 轻量 SDD 开发方法
3. `workbench/README.md` — Workbench 运行路径
4. `docs/security-local-boundary.md` — 本地 / 网络安全边界
