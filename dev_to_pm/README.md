# Dev to PM - 技术实现到产品价值翻译助手

一个帮助开发者和产品经理互相理解的 AI Native 应用。基于 LangGraph 框架，将技术实现转化为结构化的产品价值报告，帮助产品团队理解技术实现背后的用户价值和商业机会。

## 功能特点

- **技术澄清**：智能询问产品层面的关键信息（用户价值、商业目标、用户场景、市场定位）
- **技术简报生成**：将技术实现整理成结构化的技术简报
- **产品价值调研**：自动查询产品知识库，了解市场趋势、用户需求、竞品分析
- **产品价值报告**：生成包含用户价值、商业价值、市场定位、推广策略的完整产品价值报告

## 工作流程

```
技术实现输入
    ↓
技术澄清（Clarify）
    - 澄清用户价值、用户场景、市场定位、商业目标
    ↓
技术简报生成（Tech Brief）
    - 整理成结构化技术简报
    ↓
产品价值调研（Research）
    - 并行调研：市场趋势、用户需求、竞品分析、商业模式
    - 使用 get_product_info 查询产品知识库
    ↓
产品价值报告生成（Final Report）
    - 技术理解、用户价值分析、市场定位
    - 商业模式、推广策略、成功指标
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

### 2. 进入项目目录

```bash
git clone https://github.com/forestqqqq/leishikeji.git
cd leishikeji/dev_to_pm
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

在 Studio UI 中输入技术实现描述，系统将自动生成产品价值报告。

## 项目结构

```
dev_to_pm/
├── data/
│   ├── market_info.md      # 市场信息知识库（手动维护）
│   ├── user_research.md    # 用户研究知识库（手动维护）
│   └── product_info.md     # 产品信息知识库（手动维护）
├── output/                  # 生成的产品价值报告保存目录
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

- **Research Model**: 用于技术澄清和产品调研的模型（推荐：`openai:gpt-4.1` 或 `anthropic:claude-sonnet-4-20250514`）
- **Final Report Model**: 用于生成最终产品价值报告的模型（推荐：`openai:gpt-4.1`）

### 产品知识库配置

本项目使用产品知识库查询（`get_product_info`），需要在 `data/` 目录下创建以下文档：

- `market_info.md`: 市场趋势、行业动态、竞品分析
- `user_research.md`: 用户需求、用户画像、使用场景
- `product_info.md`: 产品定位、商业模式、产品指标

## 技术栈

- **框架**: LangGraph
- **LLM 支持**: OpenAI (GPT)、Anthropic (Claude)、Google (Gemini) 等
- **Python**: 3.13

## 输出示例

生成的产品价值报告将包含：

1. 技术理解摘要
2. 产品价值分析（用户价值、商业价值、市场机会、差异化优势）
3. 目标用户分析（用户画像、使用场景、用户痛点、用户收益）
4. 功能产品化（用产品语言描述功能）
5. 市场定位（市场趋势、竞品分析、差异化定位）
6. 商业模式（盈利方式、定价策略、成本结构、收益预测）
7. 推广策略（推广渠道、推广重点、增长策略、阶段规划）
8. 成功指标（用户指标、业务指标、体验指标、技术指标）
9. 风险与应对
10. 产品路线图

报告自动保存到 `output/product_value_report_YYYYMMDD_HHMMSS.md`

## 测试用例

查看完整的测试用例和输出示例：[**data/dev_to_pm_测试用例.md**](./data/dev_to_pm_测试用例.md)

**输入示例**：
```
我们优化了数据库查询，QPS提升了30%
```

**输出**：完整产品价值报告（参见 `output/technical_report_20260312_010516.md`）

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
