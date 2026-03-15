# think_tool 作用说明

## 1. 什么是 `think_tool`？

`think_tool` 是一个**战略思考工具**，它本质上是一个"暂停和反思"的机制，让 LLM 在执行调研过程中停下来，系统地分析当前进展并规划下一步。

### 工具定义

```python
@tool(description="Strategic reflection tool for research planning")
def think_tool(reflection: str) -> str:
    """用于调研过程中的战略思考和规划"""
    return f"Reflection recorded: {reflection}"
```

### 参数说明

- **reflection**: 调研者的详细反思内容，包括：
  - 当前发现了什么信息
  - 还缺少什么关键信息
  - 是否需要继续调研
  - 下一步应该做什么

---

## 2. 为什么需要 `think_tool`？

### 没有 `think_tool` 时的问题

- 盲目地连续调用工具，缺少整体规划
- 重复查询相同信息
- 不知道什么时候停止调研
- 缺少对信息质量的评估

### 有 `think_tool` 后的优势

- **强制暂停**：每次工具调用后停下来思考
- **系统规划**：明确下一步要做什么
- **质量评估**：判断信息是否充足
- **及时止损**：避免过度调研

---

## 3. 在哪些地方使用？

### Supervisor 使用（调研监管者）

**提示词位置**：`prompts.py` 中的 `lead_researcher_prompt`

#### 调用 ConductResearch 之前
```
使用 think_tool 规划你的方法：
- 需求简报中缺少哪些技术信息？
- 可以分解为哪些独立的调研方向？
- 哪些调研可以并行进行？
```

#### 调用 ConductResearch 之后
```
使用 think_tool 分析结果：
- 我发现了什么关键信息？
- 缺少什么？
- 有足够信息来补全技术细节了吗？
- 应该委派更多调研还是调用 ResearchComplete？
```

### Researcher 使用（调研员）

**提示词位置**：`prompts.py` 中的 `research_system_prompt`

```
在每次工具调用后，使用 think_tool 分析结果：
- 我发现了什么关键信息？
- 缺少什么？
- 我有足够信息来全面回答问题吗？
- 应该继续查询还是提供我的答案？
```

---

## 4. 实际执行流程示例

### 完整工作流

```
┌─────────────────────────────────────────────────────────────┐
│ Supervisor 节点 - 第1轮迭代                                   │
├─────────────────────────────────────────────────────────────┤
│ 1. 使用 think_tool:                                          │
│    "需求简报中缺少技术栈信息，需要调研后端框架、数据库、      │
│     中间件等"                                                 │
│ 2. 调用 ConductResearch("调研公司当前使用的后端技术栈...")    │
│ 3. 调用 ConductResearch("调研数据库和中间件...")             │
└─────────────────────────────────────────────────────────────┘
                        ↓ (并行执行 Researcher)
┌─────────────────────────────────────────────────────────────┐
│ Researcher #1: 调研后端技术栈                                │
├─────────────────────────────────────────────────────────────┤
│ 1. 使用 get_system_info("后端技术栈")                        │
│    → 返回: "Spring Boot 2.x, MySQL 8.0"                      │
│ 2. 使用 think_tool:                                          │
│    "发现使用 Spring Boot 2.x 和 MySQL 8.0，但还缺少          │
│     Redis 缓存信息，需要继续查询"                             │
│ 3. 使用 get_system_info("缓存中间件")                        │
│    → 返回: "Redis 6.x 集群"                                  │
│ 4. 使用 think_tool:                                          │
│    "信息已完整（后端框架、数据库、缓存），可以返回"           │
│ 5. 返回压缩的调研结果                                        │
└─────────────────────────────────────────────────────────────┘
                        ↓ (返回结果)
┌─────────────────────────────────────────────────────────────┐
│ Supervisor 节点 - 第2轮迭代                                   │
├─────────────────────────────────────────────────────────────┤
│ 1. 使用 think_tool:                                          │
│    "已获取技术栈信息（Spring Boot, MySQL, Redis），           │
│     还缺少系统架构信息"                                       │
│ 2. 调用 ConductResearch("调研系统架构设计...")               │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ Supervisor 节点 - 第3轮迭代                                   │
├─────────────────────────────────────────────────────────────┤
│ 1. 使用 think_tool:                                          │
│    "信息已完整，包括：                                       │
│     - 技术栈（Spring Boot, MySQL, Redis）                    │
│     - 系统架构（微服务、K8s部署）                            │
│     - 数据基础（分库分表、实时计算）                          │
│     - 团队资源（20人、Java技术栈）                           │
│     可以结束调研"                                            │
│ 2. 调用 ResearchComplete()                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 工具特点

| 特点 | 说明 |
|------|------|
| **不执行外部操作** | 只是记录思考内容，不调用外部 API |
| **可以和其他工具并行** | 代码实际支持并行（尽管提示词建议不要并行） |
| **返回确认消息** | 返回 "Reflection recorded: ..." |
| **可被 LLM 看到** | 消息会加入对话历史，供后续决策参考 |

---

## 6. 代码中的实现

### 工具定义位置

**文件**：`src/open_deep_research/utils.py`

```python
@tool(description="Strategic reflection tool for research planning")
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
```

### 在 Supervisor 中的使用

**文件**：`src/open_deep_research/deep_researcher.py`

```python
# 可用工具：委派调研、标记完成、战略思考
lead_researcher_tools = [ConductResearch, ResearchComplete, think_tool]
```

### 处理 think_tool 调用

```python
# 处理 think_tool 调用（战略思考）
think_tool_calls = [
    tool_call for tool_call in most_recent_message.tool_calls
    if tool_call["name"] == "think_tool"
]

for tool_call in think_tool_calls:
    reflection_content = tool_call["args"]["reflection"]
    all_tool_messages.append(ToolMessage(
        content=f"Reflection recorded: {reflection_content}",
        name="think_tool",
        tool_call_id=tool_call["id"]
    ))
```

---

## 7. 使用规则

### 提示词中的指示

**Supervisor 提示词**（`lead_researcher_prompt`）：
```
重要提示：在每次调用 ConductResearch 前后使用 think_tool 进行思考和评估。
不要将 think_tool 与其他工具并行调用。
```

**Researcher 提示词**（`research_system_prompt`）：
```
重要提示：每次查询系统信息后使用 think_tool 反思结果并规划下一步。
不要将 get_system_info 与其他工具并行调用。
```

---

## 8. 核心价值

`think_tool` 的核心价值是 **质量 > 数量**：

| 价值 | 说明 |
|------|------|
| **避免盲目调用** | 在每次工具调用前规划，减少无效查询 |
| **确保方向正确** | 分析当前结果，调整调研方向 |
| **及时发现缺口** | 识别缺失的关键信息 |
| **防止过度调研** | 信息充足时及时停止 |

这种"慢思考"机制虽然增加了额外的工具调用步骤，但能显著提高调研的效率和质量。

---

## 9. 工作流中的位置

```
                    ┌──────────────┐
                    │ START        │
                    └──────┬───────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ clarify_with_user      │
              │ (需求澄清)              │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │ write_research_brief   │
              │ (需求简报)              │
              └───────────┬────────────┘
                          │
                          ▼
      ┌─────────────────────────────────────┐
      │     research_supervisor 子图        │
      ├─────────────────────────────────────┤
      │                                     │
      │   ┌─────────────┐                   │
      │   │ supervisor  │ ◄── 使用 think_tool
      │   └──────┬──────┘                   │
      │          │                           │
      │          ▼                           │
      │   ┌──────────────┐                  │
      │   │supervisor_   │                  │
      │   │tools         │                  │
      │   └──────┬───────┘                  │
      │          │                           │
      │          ▼                           │
      │   ┌─────────────┐                   │
      │   │ researcher  │ ◄── 使用 think_tool
      │   │ 子图        │                   │
      │   └─────────────┘                   │
      │                                     │
      └─────────────┬───────────────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │ final_report_generation   │
        │ (技术方案报告)              │
        └───────────┬───────────────┘
                    │
                    ▼
              ┌──────────────┐
              │ END          │
              └──────────────┘
```

---

## 10. 总结

`think_tool` 是一个简单但强大的工具，通过强制 LLM 在关键决策点停下来思考，显著提高了调研的质量和效率。它的设计理念是：

> **"慢思考，快行动"** - 在行动前充分思考，避免返工和资源浪费
