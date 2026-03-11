# PM to Dev - 产品需求到技术方案翻译助手

一个帮助产品经理和开发工程师互相理解需求的 AI Native 应用。基于 LangGraph 框架，将产品需求转化为结构化的需求简报，并基于公司技术现状调研生成完整的技术方案报告。

## 功能特点

- **需求澄清**：智能询问产品层面的关键信息（业务目标、用户场景、功能范围、时间规划）
- **需求简报生成**：将产品需求整理成结构化的需求简报
- **技术现状调研**：自动查询公司内部技术文档，了解当前技术栈、系统架构、数据基础
- **技术方案报告**：生成包含方案对比、架构设计、实施计划、风险评估的完整技术方案

## 工作流程

```
产品需求输入
    ↓
需求澄清（Clarify）
    - 澄清业务目标、用户场景、功能范围、时间规划
    ↓
需求简报生成（Research Brief）
    - 整理成结构化需求简报
    ↓
技术现状调研（Research）
    - 并行调研：技术栈、系统架构、数据基础、团队资源
    - 使用 get_system_info 查询内部文档
    ↓
技术方案报告生成（Final Report）
    - 需求理解、技术现状分析、方案对比
    - 架构设计、实施计划、风险评估
    - 报告自动保存到 output/ 目录
```

## 环境要求

- Python 3.13
- uv（推荐）或 pip

## 快速开始

### 1. 安装 uv（如果未安装）

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

### 2. 克隆项目并进入目录

```bash
cd /Volumes/sanxing1t/gitwork/leishikeji/pm_to_dev
```

### 3. 创建虚拟环境并安装依赖

```bash
# 使用 uv（推荐）
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv sync
```

或使用传统方式：

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### 4. 配置环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置必要的 API 密钥：

```env
# OpenAI API（用于 GPT 模型）
OPENAI_API_KEY=your_openai_api_key_here

# Anthropic API（用于 Claude 模型）
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

### 5. 启动服务

```bash
# 方式一：使用 langgraph CLI（推荐）
langgraph dev

# 方式二：使用 uv run
uv run langgraph dev

# 方式三：允许阻塞操作
langgraph dev --allow-blocking
```

### 6. 访问服务

启动成功后，访问以下地址：

- **Studio UI**: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
- **API**: http://127.0.0.1:2024
- **API 文档**: http://127.0.0.1:2024/docs

在 Studio UI 中输入产品需求，系统将自动生成技术方案报告。

## 项目结构

```
pm_to_dev/
├── data/
│   ├── system_info.md      # 公司技术现状文档（手动维护）
│   └── more_info.md         # 技术知识库（自动积累）
├── output/                  # 生成的技术方案报告保存目录
├── src/
│   └── open_deep_research/
│       ├── deep_researcher.py    # 主工作流
│       ├── configuration.py       # 配置管理
│       ├── state.py               # 状态定义
│       ├── prompts.py             # 提示词（已中文化）
│       └── utils.py               # 工具函数
├── langgraph.json           # LangGraph 配置
├── pyproject.toml           # 项目依赖
└── .env                     # 环境变量
```

## 配置说明

### 模型配置

在 Studio UI 的 "Manage Assistants" 中配置：

- **Research Model**: 用于需求澄清和技术调研的模型（推荐：`openai:gpt-4.1` 或 `anthropic:claude-sonnet-4-20250514`）
- **Final Report Model**: 用于生成最终技术方案的模型（推荐：`openai:gpt-4.1`）

### 搜索配置

本项目使用内部技术文档查询（`get_system_info`），无需配置外部搜索 API。

## 技术栈

- **框架**: LangGraph
- **LLM 支持**: OpenAI (GPT)、Anthropic (Claude)、Google (Gemini) 等
- **Python**: 3.11+

## 输出示例

生成的技术方案报告将包含：

1. 需求理解摘要
2. 技术现状分析
3. 技术方案对比
4. 推荐方案及理由
5. 架构设计
6. 数据设计
7. 性能与可扩展性
8. 实施计划
9. 风险与应对
10. 工作量评估

报告自动保存到 `output/technical_report_YYYYMMDD_HHMMSS.md`

## 开发

### 安装开发依赖

```bash
uv sync --all-extras
```

### 代码检查

```bash
ruff check
mypy src/open_deep_research/
```

## License

MIT
