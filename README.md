# PPT-AI-Assistant

**本地运行的 AI PPT 生产工具，从真实材料生成逐页 PPT，支持单页修改，并导出原生可编辑 PPTX。**

---

## ⚡ Public Alpha

- **当前为 Public Alpha**，非 production-ready
- **已真实验证**：材料输入 → 大纲确认 → 逐页生成 → 单页修改 → QA → 原生 PPTX → PowerPoint 复核
- **最终结果仍建议人工复核**

---

## ✅ What It Can Do（已验证能力）

- Markdown / 文本材料输入
- 大纲确认
- AI 逐页生成
- Workbench 预览
- 单页修改 / 重生成
- QA / Delivery Contract
- 原生可编辑 PPTX 导出
- 多模型 Provider 配置

> 不包含未经验证的功能。

---

## 🎯 Why This Project（核心差异）

与常见"整页图片式"AI PPT 工具不同：

- **基于真实材料逐页生成**：输入你的 Markdown / 文本材料，AI 逐页组织信息，而不是一句话生成空洞模板
- **支持单页修改 / 重生成**：哪页不满意改哪页，其余页面保持不变
- **输出原生可编辑 PPTX**：文本框、形状直接在 PowerPoint 里编辑，不是整页截图
- **Local-first**：项目文件与生成产物默认保存在本机；调用第三方模型 Provider 时，生成所需的提示词与材料内容会发送给你配置的 Provider

---

## 🚀 Quick Start

```bash
# 1. 克隆仓库
git clone https://github.com/FrankChen668/PPT-AI-Assistant.git
cd PPT-AI-Assistant

# 2. 搭建 Python 环境（需 3.11+）
cd my-ppt-skill
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate   # macOS / Linux
python -m pip install -e .

# 3. 回到仓库根目录，配置 API Key
cd ..
# 在根目录创建 .env（已在 .gitignore 中）
# WORKBENCH_DEEPSEEK_API_KEY=你的key

# 4. 创建 Workbench 本地配置
# 在 workbench/ 目录创建 settings.local.json（参考 settings.local.example.json）
# {
#   "generation_provider": "deepseek",
#   "deepseek_api_key_env": "WORKBENCH_DEEPSEEK_API_KEY",
#   "deepseek_model": "deepseek-v4-flash",
#   "deepseek_base_url": "https://api.deepseek.com/v1"
# }

# 5. 运行健康检查
python -m workbench.healthcheck

# 6. 启动 Workbench
python start_workbench.py
# 打开 http://127.0.0.1:8765
```

> 详细安装与常见问题：[`docs/first-run-checklist.md`](docs/first-run-checklist.md)

---

## 🔄 Basic Workflow

```text
真实材料
  → 大纲确认
  → 风格 / 模板选择
  → 逐页生成
  → 预览
  → 修改单页
  → QA
  → 导出原生可编辑 PPTX
  → PowerPoint 人工复核
```

---

## 📝 Native Editable PPTX

- 当前主链输出 **PowerPoint 原生文本 / 形状**
- **不是**整页截图式导出
- **已通过真实 3 页端到端验证**
- **最终交付前仍应人工检查**

> ❌ 不承诺：100% perfect / production quality / 完全无损 / 完全自动化

---

## ⚠️ Current Limitations

- **Alpha 阶段**，视觉质量依赖输入材料与模型
- 可能仍出现对比度、层级、视觉节奏等问题
- 最终 PPT **需要人工复核**
- 当前定位为 **本地个人 / 小团队工具**
- 不支持公网 SaaS / 多租户 / 复杂权限
- PDF 输入为 optional，需额外依赖
- 第三方模型的可用性、额度、数据处理与保留规则由对应 Provider 决定

---

## 🤖 Models / Providers

支持：
- Google / Gemini
- Xiaomi
- SiliconFlow（运行时默认）
- DeepSeek

> Quick Start 以 DeepSeek 为配置示例。详细配置见 [Workbench README](workbench/README.md) 与 [First Run](docs/first-run-checklist.md)

---

## 🔒 Local & Security

- Workbench **默认仅监听 `127.0.0.1`**
- 只有在可信办公室私有内网共享时，才显式设置 `WORKBENCH_HOST=0.0.0.0`
- **不建议直接暴露公网**；当前没有认证、授权或用户数据隔离
- API Key 通过环境变量注入，**不提交仓库**
- 使用第三方模型 Provider 会把生成所需输入发送给该 Provider；请按对应 Provider 的隐私、处理与保留条款判断材料是否适合发送

> 详见：[`docs/security-local-boundary.md`](docs/security-local-boundary.md)

---

## 📄 License

- **项目自有代码**：Apache-2.0（见 [LICENSE](LICENSE)）
- **第三方代码 / 图标 / 依赖**：[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

---

## 💬 Feedback / Issues

Public Alpha 欢迎通过 [GitHub Issues](https://github.com/FrankChen668/PPT-AI-Assistant/issues) 反馈：

- 安装 / 启动问题
- 生成失败或报错
- 最影响专业质量的 PPT 问题（对比度、层级、信息组织等）

> 提交可复现输入时请**先脱敏**：禁止提交 API Key、真实客户材料或任何敏感内容。

---

## 📚 Documentation

### 普通用户优先
- [First Run Checklist](docs/first-run-checklist.md) — 本地启动与配置
- [Workbench README](workbench/README.md) — Workbench 运行路径
- [Security Boundary](docs/security-local-boundary.md) — 本地 / 网络 / Provider 数据边界

### 开发者 / 贡献者入口（公开版）
- [AGENTS.md](AGENTS.md) — 公开贡献协议与核心原则
- [docs/development/SDD.md](docs/development/SDD.md) — 轻量 SDD 开发方法
- [docs/development/SPEC_TEMPLATE.md](docs/development/SPEC_TEMPLATE.md) — 变更提案模板
