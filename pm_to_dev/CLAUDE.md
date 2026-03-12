# PM to Dev - 产品需求到技术方案翻译助手

## 项目概述

这是雷石 AI Native 工程师面试题的项目之一，实现**产品经理 → 开发工程师**的需求翻译。基于 LangGraph 框架，将产品需求转化为结构化的技术方案报告。

## 核心功能

### 1. 需求澄清 (Clarify)
- 与产品经理交流，澄清业务目标、用户场景、功能范围、时间规划
- 使用结构化输出判断是否需要进一步澄清
- 智能识别需求中的关键信息缺失

### 2. 需求简报生成 (Research Brief)
- 将产品需求整理成结构化的技术调研简报
- 识别核心技术问题、调研方向、评估标准

### 3. 技术现状调研 (Research)
- 使用 `get_system_info` 工具查询公司内部技术文档
- Supervisor 并行调度多个 Researcher
- 调研方向：技术栈、系统架构、数据基础、团队资源

### 4. 技术方案报告生成 (Final Report)
- 综合调研结果生成完整技术方案
- 包含：需求理解、技术现状分析、方案对比、架构设计、实施计划、风险评估
- 自动保存到 `output/technical_report_YYYYMMDD_HHMMSS.md`

## 项目结构

```
pm_to_dev/
├── data/
│   ├── system_info.md      # 技术文档知识库（系统架构、技术栈、数据基础）
│   └── more_info.md         # 额外技术信息
├── output/                  # 生成的技术方案报告
├── src/open_deep_research/
│   ├── __init__.py          # 包入口，导出 deep_researcher
│   ├── deep_researcher.py   # 主工作流实现
│   ├── configuration.py      # 配置管理
│   ├── state.py              # 状态定义
│   ├── prompts.py            # 提示词（已中文化）
│   └── utils.py              # 工具函数（含 get_system_info）
├── langgraph.json            # LangGraph 配置
├── pyproject.toml            # 项目依赖（包名：pm_to_dev）
├── README.md                 # 项目文档
└── CLAUDE.md                 # 本文件
```

## 工作流程

```
产品需求输入
    ↓
clarify_with_user (需求澄清)
    - clarify_with_user_instructions 提示词
    - 判断是否需要澄清业务目标、用户场景、功能范围、时间规划
    ↓
write_research_brief (需求简报)
    - transform_messages_into_research_brief_prompt 提示词
    - 生成结构化技术调研简报
    ↓
research_supervisor (技术调研监管者)
    - lead_researcher_prompt 提示词
    - 并行调度多个 researcher 子任务
    - 使用 ConductResearch 工具委派调研
    ↓
researcher (技术调研员)
    - research_system_prompt 提示词
    - 使用 get_system_info 工具查询技术文档
    - 使用 tavily_search 搜索外部技术资料
    - compress_research 压缩调研结果
    ↓
final_report_generation (技术方案报告)
    - final_report_generation_prompt 提示词
    - 生成完整技术方案报告
    - 自动保存到 output/ 目录
```

## 提示词设计

### 提示词列表

| 提示词 | 用途 | 关键设计 |
|--------|------|----------|
| `clarify_with_user_instructions` | 需求澄清 | 从产品视角提问：业务目标、用户场景、功能范围、时间规划 |
| `transform_messages_into_research_brief_prompt` | 需求简报 | 将产品需求转化为技术调研问题 |
| `lead_researcher_prompt` | 调研监管者 | 规划并行调研策略，分配技术调研任务 |
| `research_system_prompt` | 调研员 | 技术调研专家，查询技术文档和搜索外部资料 |
| `compress_research_system_prompt` | 结果压缩 | 压缩技术调研结果，保留关键信息 |
| `final_report_generation_prompt` | 报告生成 | 生成结构化技术方案报告 |

### 角色设计

- **需求澄清阶段**：架构师角色，理解产品需求，澄清技术相关信息
- **技术调研阶段**：
  - Supervisor：技术调研专家，规划调研策略
  - Researcher：技术调研员，使用工具获取技术信息
- **报告生成阶段**：技术架构师，综合调研结果生成技术方案

### 工具使用

- **get_system_info**：查询公司内部技术文档（`data/system_info.md`）
- **tavily_search**：搜索外部技术资料和最佳实践
- **think_tool**：战略性思考，规划调研策略

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
cd pm_to_dev
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

### 添加技术文档

在 `data/system_info.md` 中添加公司技术文档：
- 系统架构说明
- 技术栈清单
- 数据基础设施
- 团队资源和能力

## 输出报告

报告自动保存到 `output/`目录

## 测试用例

测试用例位于：`data/pm_to_dev_测试用例.md`

**输入示例**：
```
我们需要一个智能推荐功能,提升用户停留时长
```

**输出**：完整技术方案报告（参见 `output/technical_report_20260311_192556.md`）

## 关键技术

- **LangGraph**: 状态图工作流编排
- **LangChain**: LLM 集成和工具调用
- **结构化输出**: 使用 Pydantic 模型确保输出格式
- **并行处理**: Supervisor 调度多个 Researcher 并行调研
- **工具调用**: get_system_info 查询内部文档，tavily_search 搜索外部资料
- **中文支持**: 所有提示词和输出均为中文

## 包信息

- **包名**: `pm_to_dev`
- **版本**: 0.0.16
- **Python**: >= 3.10
- **依赖管理**: uv

## License

MIT
