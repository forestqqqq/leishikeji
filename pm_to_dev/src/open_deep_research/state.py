"""Graph state definitions and data structures for the Deep Research agent."""

import operator
from typing import Annotated, Optional

from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


###################
# Structured Outputs
# 结构化输出模型 - 用于 LLM 工具调用的输出格式
###################
class ConductResearch(BaseModel):
    """Call this tool to conduct research on a specific topic."""
    # 委派技术调研任务工具 - 由 Supervisor 调用，启动新的 Researcher 子任务
    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should be described in high detail (at least a paragraph).",
    )  # 调研主题，需要详细描述（至少一段话）

class ResearchComplete(BaseModel):
    """Call this tool to indicate that the research is complete."""
    # 标记调研完成工具 - 由 Supervisor 调用，结束调研循环进入报告生成阶段

class Summary(BaseModel):
    """Research summary with key findings."""
    # 网页内容摘要 - 对搜索到的网页内容进行结构化摘要
    summary: str  # 网页内容的摘要，保留主要信息和关键点
    key_excerpts: str  # 关键引用片段，最多5个

class ClarifyWithUser(BaseModel):
    """Model for user clarification requests."""
    # 用户澄清请求 - 用于需求澄清阶段，判断是否需要向产品经理提问
    need_clarification: bool = Field(
        description="Whether the user needs to be asked a clarifying question.",
    )  # 是否需要向用户提问澄清需求
    question: str = Field(
        description="A question to ask the user to clarify the report scope",
    )  # 需要向用户提出的澄清问题
    verification: str = Field(
        description="Verify message that we will start research after the user has provided the necessary information.",
    )  # 当信息充足时，向用户确认已理解需求并即将开始技术调研的确认消息

class ResearchQuestion(BaseModel):
    """Research question and brief for guiding research."""
    # 需求简报 - 将产品需求转化为结构化的需求简报，只描述"要什么"
    research_brief: str = Field(
        description="A research question that will be used to guide the research.",
    )  # 结构化的需求简报，包含业务目标、用户场景、功能范围等


###################
# State Definitions
# 状态定义 - 工作流各节点的状态传递
###################

def override_reducer(current_value, new_value):
    """Reducer function that allows overriding values in state."""
    # 状态覆盖 Reducer 函数 - 支持覆盖模式和累加模式
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    else:
        return operator.add(current_value, new_value)
    
class AgentInputState(MessagesState):
    """InputState is only 'messages'."""
    # 主工作流输入状态 - 仅包含用户输入的消息

class AgentState(MessagesState):
    """Main agent state containing messages and research data."""
    # 主工作流状态 - 贯穿整个工作流的状态
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]  # 调研监管者的对话消息
    research_brief: Optional[str]  # 需求简报
    raw_notes: Annotated[list[str], override_reducer] = []  # 原始调研笔记（未压缩）
    notes: Annotated[list[str], override_reducer] = []  # 压缩整理后的调研结果
    final_report: str  # 最终生成的技术方案报告

class SupervisorState(TypedDict):
    """State for the supervisor that manages research tasks."""
    # 调研监管者状态 - 管理技术调研阶段的状态
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]  # 监管者的对话消息历史
    research_brief: str  # 需求简报，指导调研方向
    notes: Annotated[list[str], override_reducer] = []  # 收集的调研结果
    research_iterations: int = 0  # 调研迭代计数器
    raw_notes: Annotated[list[str], override_reducer] = []  # 原始调研笔记

class ResearcherState(TypedDict):
    """State for individual researchers conducting research."""
    # 单个调研员状态 - 每个 Researcher 子任务的独立状态
    researcher_messages: Annotated[list[MessageLikeRepresentation], operator.add]  # 调研员的对话消息历史
    tool_call_iterations: int = 0  # 工具调用次数计数器
    research_topic: str  # 本次调研的主题
    compressed_research: str  # 压缩后的调研结果
    raw_notes: Annotated[list[str], override_reducer] = []  # 原始调研笔记

class ResearcherOutputState(BaseModel):
    """Output state from individual researchers."""
    # 调研员输出状态 - Researcher 完成后返回给 Supervisor 的输出
    compressed_research: str  # 压缩整理后的调研结果
    raw_notes: Annotated[list[str], override_reducer] = []  # 原始调研笔记