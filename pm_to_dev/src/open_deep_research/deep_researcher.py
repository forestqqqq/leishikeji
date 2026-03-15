"""Main LangGraph implementation for the Deep Research agent."""
# PM to Dev - 主工作流实现 - 基于 LangGraph 的产品需求到技术方案翻译助手

import asyncio
import logging
import os
from datetime import datetime
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    get_buffer_string,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from pm_to_dev.configuration import (
    Configuration,
)
from pm_to_dev.prompts import (
    clarify_with_user_instructions,
    compress_research_simple_human_message,
    compress_research_system_prompt,
    final_report_generation_prompt,
    lead_researcher_prompt,
    research_system_prompt,
    transform_messages_into_research_brief_prompt,
)
from pm_to_dev.state import (
    AgentInputState,
    AgentState,
    ClarifyWithUser,
    ConductResearch,
    ResearchComplete,
    ResearcherOutputState,
    ResearcherState,
    ResearchQuestion,
    SupervisorState,
)
from pm_to_dev.utils import (
    anthropic_websearch_called,
    get_all_tools,
    get_api_key_for_model,
    get_model_token_limit,
    get_notes_from_tool_calls,
    get_today_str,
    is_token_limit_exceeded,
    openai_websearch_called,
    remove_up_to_last_ai_message,
    think_tool,
)

# Initialize a configurable model that we will use throughout the agent
# 初始化可配置的模型 - 用于整个工作流的 LLM 调用
configurable_model = init_chat_model(
    configurable_fields=("model", "max_tokens", "api_key"),
)

# ====================
# 主工作流节点函数
# ====================

async def clarify_with_user(state: AgentState, config: RunnableConfig) -> Command[Literal["write_research_brief", "__end__"]]:
    """Analyze user messages and ask clarifying questions if the research scope is unclear.

    # 需求澄清节点 - 与产品经理交流，澄清业务目标、用户场景、功能范围、时间规划
    # 判断是否需要向产品经理提问，如果信息充足则直接进入需求简报生成阶段

    This function determines whether the user's request needs clarification before proceeding
    with research. If clarification is disabled or not needed, it proceeds directly to research.
    
    Args:
        state: Current agent state containing user messages
        config: Runtime configuration with model settings and preferences
        
    Returns:
        Command to either end with a clarifying question or proceed to research brief
    """
    # 步骤1: 检查是否启用需求澄清
    configurable = Configuration.from_runnable_config(config)
    if not configurable.allow_clarification:
        # 跳过澄清阶段，直接进入需求简报生成
        return Command(goto="write_research_brief")

    # 步骤2: 配置结构化输出模型
    messages = state["messages"]
    model_config = {
        "model": configurable.research_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.research_model, config),
        "tags": ["langsmith:nostream"]
    }

    # 配置模型（结构化输出 + 重试逻辑）
    clarification_model = (
        configurable_model
        .with_structured_output(ClarifyWithUser)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(model_config)
    )

    # 步骤3: 分析是否需要澄清
    prompt_content = clarify_with_user_instructions.format(
        messages=get_buffer_string(messages),
        date=get_today_str()
    )
    response = await clarification_model.ainvoke([HumanMessage(content=prompt_content)])

    # 步骤4: 根据分析结果路由
    if response.need_clarification:
        # 需要澄清：返回澄清问题给用户
        return Command(
            goto=END,
            update={"messages": [AIMessage(content=response.question)]}
        )
    else:
        # 信息充足：确认理解并进入需求简报生成
        return Command(
            goto="write_research_brief",
            update={"messages": [AIMessage(content=response.verification)]}
        )


async def write_research_brief(state: AgentState, config: RunnableConfig) -> Command[Literal["research_supervisor"]]:
    """Transform user messages into a structured research brief and initialize supervisor.

    # 需求简报生成节点 - 将产品需求转化为结构化的需求简报
    # 只描述"要什么"，不涉及"怎么做"，为后续技术调研提供清晰的需求边界

    This function analyzes the user's messages and generates a focused research brief
    that will guide the research supervisor. It also sets up the initial supervisor
    context with appropriate prompts and instructions.
    
    Args:
        state: Current agent state containing user messages
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to research supervisor with initialized context
    """
    # 步骤1: 配置调研模型（结构化输出）
    configurable = Configuration.from_runnable_config(config)
    research_model_config = {
        "model": configurable.research_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.research_model, config),
        "tags": ["langsmith:nostream"]
    }

    # 配置模型（结构化输出 + 重试逻辑）
    research_model = (
        configurable_model
        .with_structured_output(ResearchQuestion)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )

    # 步骤2: 生成结构化的需求简报
    prompt_content = transform_messages_into_research_brief_prompt.format(
        messages=get_buffer_string(state.get("messages", [])),
        date=get_today_str()
    )
    response = await research_model.ainvoke([HumanMessage(content=prompt_content)])

    # 步骤3: 初始化调研监管者（Supervisor）
    supervisor_system_prompt = lead_researcher_prompt.format(
        date=get_today_str(),
        max_concurrent_research_units=configurable.max_concurrent_research_units,
        max_researcher_iterations=configurable.max_researcher_iterations
    )

    return Command(
        goto="research_supervisor",
        update={
            "research_brief": response.research_brief,  # 需求简报
            "supervisor_messages": {  # 初始化监管者消息
                "type": "override",
                "value": [
                    SystemMessage(content=supervisor_system_prompt),
                    HumanMessage(content=response.research_brief)
                ]
            }
        }
    )


# ====================
# 调研监管者子图节点
# ====================

async def supervisor(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor_tools"]]:
    """Lead research supervisor that plans research strategy and delegates to researchers.

    # 调研监管者节点 - 负责规划调研策略并并行委派调研任务
    # 使用 think_tool 战略思考，使用 ConductResearch 委派任务，使用 ResearchComplete 标记完成

    The supervisor analyzes the research brief and decides how to break down the research
    into manageable tasks. It can use think_tool for strategic planning, ConductResearch
    to delegate tasks to sub-researchers, or ResearchComplete when satisfied with findings.
    
    Args:
        state: Current supervisor state with messages and research context
        config: Runtime configuration with model settings
        
    Returns:
        Command to proceed to supervisor_tools for tool execution
    """
    # 步骤1: 配置监管者模型（绑定工具）
    configurable = Configuration.from_runnable_config(config)
    research_model_config = {
        "model": configurable.research_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.research_model, config),
        "tags": ["langsmith:nostream"]
    }

    # 可用工具：委派调研、标记完成、战略思考
    lead_researcher_tools = [ConductResearch, ResearchComplete, think_tool]

    # 配置模型（绑定工具 + 重试逻辑）
    research_model = (
        configurable_model
        .bind_tools(lead_researcher_tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )

    # 步骤2: 生成监管者响应
    supervisor_messages = state.get("supervisor_messages", [])
    response = await research_model.ainvoke(supervisor_messages)

    # 步骤3: 更新状态并进入工具执行阶段
    return Command(
        goto="supervisor_tools",
        update={
            "supervisor_messages": [response],
            "research_iterations": state.get("research_iterations", 0) + 1  # 递增迭代计数
        }
    )

async def supervisor_tools(state: SupervisorState, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Execute tools called by the supervisor, including research delegation and strategic thinking.

    # 监管者工具执行节点 - 处理 Supervisor 调用的工具
    # 1. think_tool - 战略思考（继续对话）
    # 2. ConductResearch - 委派调研任务给子调研员（并行执行）
    # 3. ResearchComplete - 标记调研完成（结束调研阶段）

    This function handles three types of supervisor tool calls:
    1. think_tool - Strategic reflection that continues the conversation
    2. ConductResearch - Delegates research tasks to sub-researchers
    3. ResearchComplete - Signals completion of research phase
    
    Args:
        state: Current supervisor state with messages and iteration count
        config: Runtime configuration with research limits and model settings
        
    Returns:
        Command to either continue supervision loop or end research phase
    """
    # 步骤1: 提取状态并检查退出条件
    configurable = Configuration.from_runnable_config(config)
    supervisor_messages = state.get("supervisor_messages", [])
    research_iterations = state.get("research_iterations", 0)
    most_recent_message = supervisor_messages[-1]

    # 定义退出条件
    exceeded_allowed_iterations = research_iterations > configurable.max_researcher_iterations  # 超过最大迭代次数
    no_tool_calls = not most_recent_message.tool_calls  # 没有工具调用
    research_complete_tool_call = any(
        tool_call["name"] == "ResearchComplete"
        for tool_call in most_recent_message.tool_calls
    )  # 调用了 ResearchComplete 工具

    # 满足任一退出条件则结束调研阶段
    if exceeded_allowed_iterations or no_tool_calls or research_complete_tool_call:
        return Command(
            goto=END,
            update={
                "notes": get_notes_from_tool_calls(supervisor_messages),  # 提取调研结果
                "research_brief": state.get("research_brief", "")
            }
        )

    # 步骤2: 处理所有工具调用（think_tool 和 ConductResearch）
    all_tool_messages = []
    update_payload = {"supervisor_messages": []}

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

    # 处理 ConductResearch 调用（委派调研任务）
    conduct_research_calls = [
        tool_call for tool_call in most_recent_message.tool_calls
        if tool_call["name"] == "ConductResearch"
    ]

    if conduct_research_calls:
        try:
            # 限制并发调研数量，防止资源耗尽
            allowed_conduct_research_calls = conduct_research_calls[:configurable.max_concurrent_research_units]
            overflow_conduct_research_calls = conduct_research_calls[configurable.max_concurrent_research_units:]

            # 并行执行调研任务
            research_tasks = [
                researcher_subgraph.ainvoke({
                    "researcher_messages": [
                        HumanMessage(content=tool_call["args"]["research_topic"])
                    ],
                    "research_topic": tool_call["args"]["research_topic"]
                }, config)
                for tool_call in allowed_conduct_research_calls
            ]

            tool_results = await asyncio.gather(*research_tasks)

            # 创建工具消息（调研结果）
            for observation, tool_call in zip(tool_results, allowed_conduct_research_calls):
                all_tool_messages.append(ToolMessage(
                    content=observation.get("compressed_research", "Error synthesizing research report: Maximum retries exceeded"),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"]
                ))

            # 处理超出的调研任务（返回错误消息）
            for overflow_call in overflow_conduct_research_calls:
                all_tool_messages.append(ToolMessage(
                    content=f"Error: Did not run this research as you have already exceeded the maximum number of concurrent research units. Please try again with {configurable.max_concurrent_research_units} or fewer research units.",
                    name="ConductResearch",
                    tool_call_id=overflow_call["id"]
                ))

            # 聚合所有原始调研笔记
            raw_notes_concat = "\n".join([
                "\n".join(observation.get("raw_notes", []))
                for observation in tool_results
            ])

            if raw_notes_concat:
                update_payload["raw_notes"] = [raw_notes_concat]

        except Exception as e:
            # 处理调研执行错误
            if is_token_limit_exceeded(e, configurable.research_model) or True:
                # Token 超限或其他错误 - 结束调研阶段
                return Command(
                    goto=END,
                    update={
                        "notes": get_notes_from_tool_calls(supervisor_messages),
                        "research_brief": state.get("research_brief", "")
                    }
                )

    # 步骤3: 返回命令（包含所有工具结果）
    update_payload["supervisor_messages"] = all_tool_messages
    return Command(
        goto="supervisor",
        update=update_payload
    )

# ====================
# 调研监管者子图构建
# ====================
# Supervisor Subgraph Construction - 创建监管者工作流
supervisor_builder = StateGraph(SupervisorState, config_schema=Configuration)

# 添加监管者节点
supervisor_builder.add_node("supervisor", supervisor)  # 主监管者逻辑
supervisor_builder.add_node("supervisor_tools", supervisor_tools)  # 工具执行处理

# 定义监管者工作流边
supervisor_builder.add_edge(START, "supervisor")  # 入口

# 编译监管者子图
supervisor_subgraph = supervisor_builder.compile()

# ====================
# 调研员子图节点
# ====================

async def researcher(state: ResearcherState, config: RunnableConfig) -> Command[Literal["researcher_tools"]]:
    """Individual researcher that conducts focused research on specific topics.

    # 调研员节点 - 执行具体的技术调研工作
    # 使用 get_system_info 查询技术文档，使用 think_tool 战略思考

    This researcher is given a specific research topic by the supervisor and uses
    available tools (search, think_tool, MCP tools) to gather comprehensive information.
    It can use think_tool for strategic planning between searches.
    
    Args:
        state: Current researcher state with messages and topic context
        config: Runtime configuration with model settings and tool availability
        
    Returns:
        Command to proceed to researcher_tools for tool execution
    """
    # 步骤1: 加载配置并验证工具可用性
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])

    # 获取所有可用工具（搜索、MCP、think_tool）
    tools = await get_all_tools(config)
    if len(tools) == 0:
        raise ValueError(
            "No tools found to conduct research: Please configure either your "
            "search API or add MCP tools to your configuration."
        )

    # 步骤2: 配置调研员模型（绑定工具）
    research_model_config = {
        "model": configurable.research_model,
        "max_tokens": configurable.research_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.research_model, config),
        "tags": ["langsmith:nostream"]
    }

    # 准备系统提示词（含 MCP 上下文）
    researcher_prompt = research_system_prompt.format(
        mcp_prompt=configurable.mcp_prompt or "",
        date=get_today_str()
    )

    # 配置模型（绑定工具 + 重试逻辑）
    research_model = (
        configurable_model
        .bind_tools(tools)
        .with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        .with_config(research_model_config)
    )

    # 步骤3: 生成调研员响应（含系统上下文）
    messages = [SystemMessage(content=researcher_prompt)] + researcher_messages
    response = await research_model.ainvoke(messages)

    # 步骤4: 更新状态并进入工具执行阶段
    return Command(
        goto="researcher_tools",
        update={
            "researcher_messages": [response],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1  # 递增工具调用计数
        }
    )


# ====================
# 工具执行辅助函数
# ====================

async def execute_tool_safely(tool, args, config):
    """Safely execute a tool with error handling."""
    # 安全执行工具（带错误处理）
    try:
        return await tool.ainvoke(args, config)
    except Exception as e:
        return f"Error executing tool: {str(e)}"


async def researcher_tools(state: ResearcherState, config: RunnableConfig) -> Command[Literal["researcher", "compress_research"]]:
    """Execute tools called by the researcher, including search tools and strategic thinking.

    # 调研员工具执行节点 - 处理调研员调用的工具
    # 1. think_tool - 战略思考
    # 2. get_system_info - 查询技术文档
    # 3. MCP tools - 外部工具集成
    # 4. ResearchComplete - 标记调研完成

    This function handles various types of researcher tool calls:
    1. think_tool - Strategic reflection that continues the research conversation
    2. Search tools (tavily_search, web_search) - Information gathering
    3. MCP tools - External tool integrations
    4. ResearchComplete - Signals completion of individual research task
    
    Args:
        state: Current researcher state with messages and iteration count
        config: Runtime configuration with research limits and tool settings
        
    Returns:
        Command to either continue research loop or proceed to compression
    """
    # 步骤1: 提取状态并检查早期退出条件
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    most_recent_message = researcher_messages[-1]

    # 检查是否有工具调用（包括原生网络搜索）
    has_tool_calls = bool(most_recent_message.tool_calls)
    has_native_search = (
        openai_websearch_called(most_recent_message) or
        anthropic_websearch_called(most_recent_message)
    )

    # 没有工具调用，直接进入压缩阶段
    if not has_tool_calls and not has_native_search:
        return Command(goto="compress_research")

    # 步骤2: 处理工具调用（搜索、MCP 工具等）
    tools = await get_all_tools(config)
    tools_by_name = {
        tool.name if hasattr(tool, "name") else tool.get("name", "web_search"): tool
        for tool in tools
    }

    # 并行执行所有工具调用
    tool_calls = most_recent_message.tool_calls
    tool_execution_tasks = [
        execute_tool_safely(tools_by_name[tool_call["name"]], tool_call["args"], config)
        for tool_call in tool_calls
    ]
    observations = await asyncio.gather(*tool_execution_tasks)

    # 创建工具消息（执行结果）
    tool_outputs = [
        ToolMessage(
            content=observation,
            name=tool_call["name"],
            tool_call_id=tool_call["id"]
        )
        for observation, tool_call in zip(observations, tool_calls)
    ]

    # 步骤3: 检查后期退出条件（处理工具后）
    exceeded_iterations = state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls
    research_complete_called = any(
        tool_call["name"] == "ResearchComplete"
        for tool_call in most_recent_message.tool_calls
    )

    # 超过最大迭代次数或标记完成，进入压缩阶段
    if exceeded_iterations or research_complete_called:
        return Command(
            goto="compress_research",
            update={"researcher_messages": tool_outputs}
        )

    # 继续调研循环
    return Command(
        goto="researcher",
        update={"researcher_messages": tool_outputs}
    )

async def compress_research(state: ResearcherState, config: RunnableConfig):
    """Compress and synthesize research findings into a concise, structured summary.

    # 调研结果压缩节点 - 将调研发现压缩成简洁的结构化摘要
    # 保留所有重要信息，清理冗余内容

    This function takes all the research findings, tool outputs, and AI messages from
    a researcher's work and distills them into a clean, comprehensive summary while
    preserving all important information and findings.
    
    Args:
        state: Current researcher state with accumulated research messages
        config: Runtime configuration with compression model settings
        
    Returns:
        Dictionary containing compressed research summary and raw notes
    """
    # 步骤1: 配置压缩模型
    configurable = Configuration.from_runnable_config(config)
    synthesizer_model = configurable_model.with_config({
        "model": configurable.compression_model,
        "max_tokens": configurable.compression_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.compression_model, config),
        "tags": ["langsmith:nostream"]
    })

    # 步骤2: 准备压缩消息
    researcher_messages = state.get("researcher_messages", [])
    
    # 添加指令（从调研模式切换到压缩模式）
    researcher_messages.append(HumanMessage(content=compress_research_simple_human_message))

    # 步骤3: 尝试压缩（带 token 限制重试逻辑）
    synthesis_attempts = 0
    max_attempts = 3

    while synthesis_attempts < max_attempts:
        try:
            # 创建系统提示词（聚焦压缩任务）
            compression_prompt = compress_research_system_prompt.format(date=get_today_str())
            messages = [SystemMessage(content=compression_prompt)] + researcher_messages

            # 执行压缩
            response = await synthesizer_model.ainvoke(messages)

            # 提取原始笔记（来自工具和 AI 消息）
            raw_notes_content = "\n".join([
                str(message.content)
                for message in filter_messages(researcher_messages, include_types=["tool", "ai"])
            ])

            # 返回成功的压缩结果
            return {
                "compressed_research": str(response.content),
                "raw_notes": [raw_notes_content]
            }

        except Exception as e:
            synthesis_attempts += 1

            # 处理 token 超限（移除旧消息）
            if is_token_limit_exceeded(e, configurable.research_model):
                researcher_messages = remove_up_to_last_ai_message(researcher_messages)
                continue

            # 其他错误继续重试
            continue

    # 步骤4: 所有尝试失败，返回错误
    raw_notes_content = "\n".join([
        str(message.content)
        for message in filter_messages(researcher_messages, include_types=["tool", "ai"])
    ])
    
    return {
        "compressed_research": "Error synthesizing research report: Maximum retries exceeded",
        "raw_notes": [raw_notes_content]
    }

# ====================
# 调研员子图构建
# ====================
# Researcher Subgraph Construction - 创建单个调研员工作流
researcher_builder = StateGraph(
    ResearcherState,
    output=ResearcherOutputState,
    config_schema=Configuration
)

# 添加调研员节点
researcher_builder.add_node("researcher", researcher)  # 主调研员逻辑
researcher_builder.add_node("researcher_tools", researcher_tools)  # 工具执行处理
researcher_builder.add_node("compress_research", compress_research)  # 调研结果压缩

# 定义调研员工作流边
researcher_builder.add_edge(START, "researcher")  # 入口
researcher_builder.add_edge("compress_research", END)  # 出口（压缩后结束）

# 编译调研员子图（由 supervisor 并行调用）
researcher_subgraph = researcher_builder.compile()


# ====================
# 辅助函数和最终报告生成
# ====================

async def save_report_to_file(report_content: str) -> str:
    """Save the generated report to a file in the output directory (async version).
    # 保存生成的报告到 output 目录

    Args:
        report_content: The content of the report to save

    Returns:
        Path to the saved file
    """
    # Get the output directory path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    output_dir = os.path.join(project_root, "output")

    # Create output directory if it doesn't exist (using async-compatible approach)
    await asyncio.to_thread(os.makedirs, output_dir, exist_ok=True)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"technical_report_{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    # Write report to file (using async-compatible approach)
    def _write_file():
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        return filepath

    saved_path = await asyncio.to_thread(_write_file)

    print(f"✅ 报告已保存到: {saved_path}")
    return saved_path


async def final_report_generation(state: AgentState, config: RunnableConfig):
    """Generate the final comprehensive research report with retry logic for token limits.

    # 技术方案报告生成节点 - 综合需求简报和调研结果生成完整技术方案
    # 包含：需求理解、技术现状分析、方案对比、架构设计、实施计划、风险评估

    This function takes all collected research findings and synthesizes them into a
    well-structured, comprehensive final report using the configured report generation model.
    
    Args:
        state: Agent state containing research findings and context
        config: Runtime configuration with model settings and API keys
        
    Returns:
        Dictionary containing the final report and cleared state
    """
    # 步骤1: 提取调研结果并准备状态清理
    notes = state.get("notes", [])
    cleared_state = {"notes": {"type": "override", "value": []}}
    findings = "\n".join(notes)

    # 步骤2: 配置最终报告生成模型
    configurable = Configuration.from_runnable_config(config)
    writer_model_config = {
        "model": configurable.final_report_model,
        "max_tokens": configurable.final_report_model_max_tokens,
        "api_key": get_api_key_for_model(configurable.final_report_model, config),
        "tags": ["langsmith:nostream"]
    }

    # 步骤3: 尝试生成报告（带 token 限制重试逻辑）
    max_retries = 3
    current_retry = 0
    findings_token_limit = None

    while current_retry <= max_retries:
        try:
            # 创建综合提示词（含所有调研上下文）
            final_report_prompt = final_report_generation_prompt.format(
                research_brief=state.get("research_brief", ""),
                messages=get_buffer_string(state.get("messages", [])),
                findings=findings,
                date=get_today_str()
            )

            # 生成最终报告
            final_report = await configurable_model.with_config(writer_model_config).ainvoke([
                HumanMessage(content=final_report_prompt)
            ])

            # 保存报告到文件
            report_content = final_report.content
            try:
                saved_path = await save_report_to_file(report_content)
                report_content_with_path = f"{report_content}\n\n---\n\n报告已保存到: {saved_path}"
            except Exception as save_error:
                logging.error(f"保存报告到文件失败: {save_error}")
                report_content_with_path = report_content

            # 返回成功的报告生成结果
            return {
                "final_report": report_content_with_path,
                "messages": [final_report],
                **cleared_state
            }

        except Exception as e:
            # 处理 token 超限错误（逐步截断）
            if is_token_limit_exceeded(e, configurable.final_report_model):
                current_retry += 1

                if current_retry == 1:
                    # 首次重试：确定初始截断限制
                    model_token_limit = get_model_token_limit(configurable.final_report_model)
                    if not model_token_limit:
                        return {
                            "final_report": f"Error generating final report: Token limit exceeded, however, we could not determine the model's maximum context length. Please update the model map in deep_researcher/utils.py with this information. {e}",
                            "messages": [AIMessage(content="Report generation failed due to token limits")],
                            **cleared_state
                        }
                    # 使用 4x token 限制作为字符截断近似值
                    findings_token_limit = model_token_limit * 4
                else:
                    # 后续重试：每次减少 10%
                    findings_token_limit = int(findings_token_limit * 0.9)

                # 截断 findings 并重试
                findings = findings[:findings_token_limit]
                continue
            else:
                # 非 token 限制错误：立即返回
                return {
                    "final_report": f"Error generating final report: {e}",
                    "messages": [AIMessage(content="Report generation failed due to an error")],
                    **cleared_state
                }

    # 步骤4: 所有重试失败，返回错误
    return {
        "final_report": "Error generating final report: Maximum retries exceeded",
        "messages": [AIMessage(content="Report generation failed after maximum retries")],
        **cleared_state
    }

# ====================
# 主工作流图构建
# ====================
# Main Deep Researcher Graph Construction - 创建完整的产品需求到技术方案翻译工作流
deep_researcher_builder = StateGraph(
    AgentState,
    input=AgentInputState,
    config_schema=Configuration
)

# 添加主工作流节点
deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)  # 需求澄清阶段
deep_researcher_builder.add_node("write_research_brief", write_research_brief)  # 需求简报生成阶段
deep_researcher_builder.add_node("research_supervisor", supervisor_subgraph)  # 技术现状调研阶段
deep_researcher_builder.add_node("final_report_generation", final_report_generation)  # 技术方案报告生成阶段

# 定义主工作流边（顺序执行）
deep_researcher_builder.add_edge(START, "clarify_with_user")  # 入口
deep_researcher_builder.add_edge("research_supervisor", "final_report_generation")  # 调研到报告
deep_researcher_builder.add_edge("final_report_generation", END)  # 最终出口

# 编译完整工作流
deep_researcher = deep_researcher_builder.compile()