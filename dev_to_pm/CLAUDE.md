# Dev to PM - 技术实现到产品价值翻译助手

## 项目概述

这是雷石 AI Native 工程师面试题的项目之一，实现**开发工程师 → 产品经理**的技术价值翻译。基于 LangGraph 框架，将技术实现转化为结构化的产品价值报告。

## 核心功能

### 1. 技术澄清 (Clarify)
- 资深架构师与开发工程师交流
- 澄清技术实现对业务和产品的影响
- 关注：用户场景、功能影响、预期效果

### 2. 技术简报生成 (Tech Brief)
- 将技术实现整理成结构化的技术简报
- 提炼核心技术要点和产品影响

### 3. 产品价值调研 (Research)
- 使用 `get_product_info` 工具查询产品知识库
- Supervisor 并行调度多个 Researcher
- 调研方向（按优先级）：
  1. **公司战略和企业目标**（最优先）
  2. **产品KPI和成功指标**（高优先级）
  3. **市场趋势和行业动态**
  4. **用户需求和痛点**
  5. **竞品分析和市场定位**
  6. **商业模式和盈利方式**

### 4. 产品价值报告生成 (Final Report)
- 综合调研结果生成完整产品价值报告
- 包含：产品价值分析、目标用户、市场定位、商业模式、推广策略、成功指标
- 自动保存到 `output/product_value_report_YYYYMMDD_HHMMSS.md`

## 项目结构

```
dev_to_pm/
├── data/
│   ├── product_info.md      # 产品知识库（公司战略、产品KPI）
│   ├── market_info.md       # 市场信息（市场趋势、竞品分析）
│   ├── user_research.md     # 用户研究（用户需求、用户画像）
│   └── dev_to_pm_测试用例.md  # 测试用例
├── output/                  # 生成的产品价值报告
├── src/open_deep_research/
│   ├── __init__.py          # 包入口，导出 deep_researcher
│   ├── deep_researcher.py   # 主工作流实现
│   ├── configuration.py      # 配置管理
│   ├── state.py              # 状态定义
│   ├── prompts.py            # 提示词（已中文化）
│   └── utils.py              # 工具函数（含 get_product_info）
├── langgraph.json            # LangGraph 配置
├── pyproject.toml            # 项目依赖（包名：dev_to_pm）
├── README.md                 # 项目文档
└── CLAUDE.md                 # 本文件
```

## 工作流程

```
技术实现输入
    ↓
clarify_with_user (技术澄清)
    - clarify_with_user_instructions 提示词
    - 架构师角色，澄清对业务和产品的影响
    - 关注：用户场景、功能影响、预期效果
    ↓
write_research_brief (技术简报)
    - transform_messages_into_research_brief_prompt 提示词
    - 生成结构化技术简报
    ↓
research_supervisor (产品价值调研监管者)
    - lead_researcher_prompt 提示词
    - 规划并行调研策略（战略 > KPI > 市场 > 用户 > 竞品）
    - 使用 ConductResearch 工具委派调研
    ↓
researcher (产品价值调研员)
    - research_system_prompt 提示词
    - 使用 get_product_info 工具查询产品知识库
    - 使用 tavily_search 搜索外部市场信息
    - compress_research 压缩调研结果
    ↓
final_report_generation (产品价值报告)
    - final_report_generation_prompt 提示词
    - 生成完整产品价值报告
    - 自动保存到 output/ 目录
```

## 提示词设计

### 提示词列表

| 提示词 | 用途 | 关键设计 |
|--------|------|----------|
| `clarify_with_user_instructions` | 技术澄清 | 资深架构师角色，从产品视角提问：用户场景、功能影响、预期效果 |
| `transform_messages_into_research_brief_prompt` | 技术简报 | 将技术实现转化为产品价值调研问题 |
| `lead_researcher_prompt` | 调研监管者 | 产品价值调研专家，优先调研战略和KPI |
| `research_system_prompt` | 调研员 | 产品价值研究员，查询产品知识库和搜索市场信息 |
| `compress_research_system_prompt` | 结果压缩 | 压缩产品调研结果，保留关键价值信息 |
| `final_report_generation_prompt` | 报告生成 | 生成结构化产品价值报告 |

### 角色设计

- **技术澄清阶段**：资深架构师，能够以产品经理的视角来思考，用开发工程师能理解的语言交流
- **产品价值调研阶段**：
  - Supervisor：产品价值首席调研员，优先关注战略和KPI
  - Researcher：产品价值研究员，使用工具获取产品和市场信息
- **报告生成阶段**：产品经理，综合调研结果生成产品价值报告

### 工具使用

- **get_product_info**：查询产品知识库（`data/*.md`）
  - `product_info.md`: 公司战略、企业目标、产品KPI
  - `market_info.md`: 市场趋势、行业动态、竞品分析
  - `user_research.md`: 用户需求、用户画像、使用场景
- **tavily_search**：搜索外部市场信息和竞品动态
- **think_tool**：战略性思考，规划调研策略

### 调研优先级

产品价值调研的优先级顺序：
1. **公司战略和企业目标**（最优先）- 了解技术实现与战略的契合度
2. **产品KPI和成功指标**（高优先级）- 评估对核心指标的贡献
3. **市场趋势和行业动态** - 了解市场环境
4. **用户需求和痛点** - 理解用户价值
5. **竞品分析和市场定位** - 找差异化机会
6. **商业模式和盈利方式** - 评估商业价值

## 配置说明

### 环境变量

```bash
# .env 文件
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
```

### 模型配置

在 LangGraph Studio 中配置：
- **Research Model**: `openai:gpt-4.1` 或 `anthropic:claude-sonnet-4-20250514`
- **Final Report Model**: `openai:gpt-4.1`

### 可调参数

- `max_researcher_iterations`: 最大调研迭代次数（默认：10）
- `max_concurrent_research_units`: 最大并行调研数量（默认：3）
- `max_react_tool_calls`: 单次调研最大工具调用次数（默认：5）

## 开发指南

### 快速启动

```bash
cd dev_to_pm
uv venv
source .venv/bin/activate
uv sync
langgraph dev
```

访问：https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024

### 代码检查

```bash
ruff check
mypy src/open_deep_research/
```

### 修改提示词

提示词位于 `src/open_deep_research/prompts.py`，所有提示词已中文化。

修改提示词后无需重启，LangGraph Studio 会自动重新加载。

### 维护产品知识库

在 `data/` 目录下维护三个知识库文件：

1. **product_info.md** - 公司战略、产品KPI
2. **market_info.md** - 市场趋势、竞品分析
3. **user_research.md** - 用户需求、用户画像

## 输出报告

报告自动保存到 `output/`目录

## 测试用例

测试用例位于：`data/dev_to_pm_测试用例.md`

**输入示例**：
```
我们优化了数据库查询，QPS提升了30%
```

**输出**：完整产品价值报告（参见 `output/technical_report_20260312_010516.md`）

## 关键技术

- **LangGraph**: 状态图工作流编排
- **LangChain**: LLM 集成和工具调用
- **结构化输出**: 使用 Pydantic 模型确保输出格式
- **并行处理**: Supervisor 调度多个 Researcher 并行调研
- **工具调用**: get_product_info 查询产品知识库，tavily_search 搜索市场信息
- **中文支持**: 所有提示词和输出均为中文
- **优先级调研**: 优先关注战略和KPI，确保技术实现与公司目标对齐

## 包信息

- **包名**: `dev_to_pm`
- **版本**: 0.0.16
- **Python**: >= 3.10
- **依赖管理**: uv

## License

MIT
