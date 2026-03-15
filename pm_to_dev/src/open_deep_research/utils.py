"""Utility functions and helpers for the Deep Research agent."""
# PM to Dev - 工具函数和辅助方法 - 包含搜索工具、系统信息查询、思考工具等

import asyncio
import logging
import os
import warnings
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional

import aiohttp
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    MessageLikeRepresentation,
    filter_messages,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import (
    BaseTool,
    InjectedToolArg,
    StructuredTool,
    ToolException,
    tool,
)
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.config import get_store
from mcp import McpError
from tavily import AsyncTavilyClient

from .configuration import Configuration, SearchAPI
from .prompts import summarize_webpage_prompt
from .state import ResearchComplete, Summary

##########################
# Tavily 搜索工具
##########################
TAVILY_SEARCH_DESCRIPTION = (  # Tavily 搜索描述（注：本项目未启用外部搜索）
    "A search engine optimized for comprehensive, accurate, and trusted results. "
    "Useful for when you need to answer questions about current events."
)
@tool(description=TAVILY_SEARCH_DESCRIPTION)
async def tavily_search(
    queries: List[str],  # 搜索查询列表
    max_results: Annotated[int, InjectedToolArg] = 5,  # 每个查询的最大结果数
    topic: Annotated[Literal["general", "news", "finance"], InjectedToolArg] = "general",  # 主题过滤
    config: RunnableConfig = None
) -> str:
    """Fetch and summarize search results from Tavily search API.
    # 从 Tavily 搜索 API 获取并总结搜索结果（注：本项目未启用）

    Args:
        queries: List of search queries to execute
        max_results: Maximum number of results to return per query
        topic: Topic filter for search results (general, news, or finance)
        config: Runtime configuration for API keys and model settings

    Returns:
        Formatted string containing summarized search results
    """
    # 步骤1: 异步执行搜索查询
    search_results = await tavily_search_async(
        queries,
        max_results=max_results,
        topic=topic,
        include_raw_content=True,
        config=config
    )

    # 步骤2: 按 URL 去重，避免重复处理相同内容
    unique_results = {}
    for response in search_results:
        for result in response['results']:
            url = result['url']
            if url not in unique_results:
                unique_results[url] = {**result, "query": response['query']}
    
    # Step 3: Set up the summarization model with configuration
    configurable = Configuration.from_runnable_config(config)
    
    # Character limit to stay within model token limits (configurable)
    max_char_to_include = configurable.max_content_length
    
    # Initialize summarization model with retry logic
    model_api_key = get_api_key_for_model(configurable.summarization_model, config)
    summarization_model = init_chat_model(
        model=configurable.summarization_model,
        max_tokens=configurable.summarization_model_max_tokens,
        api_key=model_api_key,
        tags=["langsmith:nostream"]
    ).with_structured_output(Summary).with_retry(
        stop_after_attempt=configurable.max_structured_output_retries
    )
    
    # Step 4: Create summarization tasks (skip empty content)
    async def noop():
        """No-op function for results without raw content."""
        return None
    
    summarization_tasks = [
        noop() if not result.get("raw_content") 
        else summarize_webpage(
            summarization_model, 
            result['raw_content'][:max_char_to_include]
        )
        for result in unique_results.values()
    ]
    
    # Step 5: Execute all summarization tasks in parallel
    summaries = await asyncio.gather(*summarization_tasks)
    
    # Step 6: Combine results with their summaries
    summarized_results = {
        url: {
            'title': result['title'], 
            'content': result['content'] if summary is None else summary
        }
        for url, result, summary in zip(
            unique_results.keys(), 
            unique_results.values(), 
            summaries
        )
    }
    
    # Step 7: Format the final output
    if not summarized_results:
        return "No valid search results found. Please try different search queries or use a different search API."
    
    formatted_output = "Search results: \n\n"
    for i, (url, result) in enumerate(summarized_results.items()):
        formatted_output += f"\n\n--- SOURCE {i+1}: {result['title']} ---\n"
        formatted_output += f"URL: {url}\n\n"
        formatted_output += f"SUMMARY:\n{result['content']}\n\n"
        formatted_output += "\n\n" + "-" * 80 + "\n"
    
    return formatted_output

async def tavily_search_async(
    search_queries, 
    max_results: int = 5, 
    topic: Literal["general", "news", "finance"] = "general", 
    include_raw_content: bool = True, 
    config: RunnableConfig = None
):
    """Execute multiple Tavily search queries asynchronously.
    
    Args:
        search_queries: List of search query strings to execute
        max_results: Maximum number of results per query
        topic: Topic category for filtering results
        include_raw_content: Whether to include full webpage content
        config: Runtime configuration for API key access
        
    Returns:
        List of search result dictionaries from Tavily API
    """
    # Initialize the Tavily client with API key from config
    tavily_client = AsyncTavilyClient(api_key=get_tavily_api_key(config))
    
    # Create search tasks for parallel execution
    search_tasks = [
        tavily_client.search(
            query,
            max_results=max_results,
            include_raw_content=include_raw_content,
            topic=topic
        )
        for query in search_queries
    ]
    
    # Execute all search queries in parallel and return results
    search_results = await asyncio.gather(*search_tasks)
    return search_results

async def summarize_webpage(model: BaseChatModel, webpage_content: str) -> str:
    """Summarize webpage content using AI model with timeout protection.
    
    Args:
        model: The chat model configured for summarization
        webpage_content: Raw webpage content to be summarized
        
    Returns:
        Formatted summary with key excerpts, or original content if summarization fails
    """
    try:
        # Create prompt with current date context
        prompt_content = summarize_webpage_prompt.format(
            webpage_content=webpage_content, 
            date=get_today_str()
        )
        
        # Execute summarization with timeout to prevent hanging
        summary = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt_content)]),
            timeout=60.0  # 60 second timeout for summarization
        )
        
        # Format the summary with structured sections
        formatted_summary = (
            f"<summary>\n{summary.summary}\n</summary>\n\n"
            f"<key_excerpts>\n{summary.key_excerpts}\n</key_excerpts>"
        )
        
        return formatted_summary
        
    except asyncio.TimeoutError:
        # Timeout during summarization - return original content
        logging.warning("Summarization timed out after 60 seconds, returning original content")
        return webpage_content
    except Exception as e:
        # Other errors during summarization - log and return original content
        logging.warning(f"Summarization failed with error: {str(e)}, returning original content")
        return webpage_content

##########################
# Reflection Tool Utils
##########################

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
##########################
# System Info Tool Utils
# 系统信息查询工具 - PM to Dev 核心工具
##########################

import os

@tool(description="查询公司技术现状文档，了解当前技术栈、系统架构、数据基础设施等信息")
async def get_system_info(
    query: str,  # 查询问题
    config: RunnableConfig = None
) -> str:
    """查询公司技术现状知识库，获取当前系统技术信息。
    
    这个工具用于查询公司内部的技术文档，了解：
    - 当前技术栈（编程语言、框架、数据库等）
    - 系统架构（微服务、消息队列、缓存等）
    - 数据基础设施（数据存储、处理能力等）
    - 团队规模和资源约束
    - 已有功能模块
    
    Args:
        query: 要查询的技术问题或信息需求
        config: 运行时配置
        
    Returns:
        查询到的技术信息，如果没有相关信息则返回建议
    """
    # 获取项目根目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    data_dir = os.path.join(project_root, "data")

    # 定义要查询的文件列表（data/system_info.md 和 data/more_info.md）
    info_files = [
        os.path.join(data_dir, "system_info.md"),
        os.path.join(data_dir, "more_info.md")
    ]

    # 收集所有相关信息
    collected_info = []
    for file_path in info_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                    collected_info.append(f"=== 来自 {os.path.basename(file_path)} 的信息 ===\\n")
                    collected_info.append(file_content)
                    collected_info.append("\\n\\n")
            except Exception as e:
                logging.warning(f"无法读取文件 {file_path}: {e}")
    
    if not collected_info:
        return "未找到系统技术现状文档。请先在 data 目录下创建 system_info.md 或 more_info.md 文档。"
    
    # 使用 LLM 从文档中提取相关信息
    configurable = Configuration.from_runnable_config(config) if config else None
    if configurable:
        try:
            # 获取模型
            model_api_key = get_api_key_for_model(configurable.research_model, config) if config else None
            query_model = init_chat_model(
                model=configurable.research_model,
                max_tokens=4000,
                api_key=model_api_key,
                tags=["langsmith:nostream"]
            )
            
            # 构建查询提示
            query_prompt = f"""你是一位技术文档查询助手。请根据用户的问题，从以下技术文档中提取相关信息。

用户问题：{query}

技术文档内容：
{"".join(collected_info)}

请只提取与用户问题直接相关的信息，使用清晰的中文回答。如果文档中没有相关信息，请明确说明。
"""
            
            result = await asyncio.wait_for(
                query_model.ainvoke([HumanMessage(content=query_prompt)]),
                timeout=30.0
            )
            
            return str(result.content)
            
        except Exception as e:
            logging.warning(f"使用 LLM 查询失败，返回原始内容: {e}")
    
    # 如果 LLM 查询失败，返回所有文档内容
    return "".join(collected_info)

##########################
# MCP Utils
# MCP（Model Context Protocol）工具集成 - 可选的外部工具
##########################

async def get_mcp_access_token(
    supabase_token: str,  # Supabase 认证令牌
    base_mcp_url: str,  # MCP 服务器基础 URL
) -> Optional[Dict[str, Any]]:
    """Exchange Supabase token for MCP access token using OAuth token exchange.
    # 使用 OAuth 令牌交换将 Supabase 令牌转换为 MCP 访问令牌
    
    Args:
        supabase_token: Valid Supabase authentication token
        base_mcp_url: Base URL of the MCP server
        
    Returns:
        Token data dictionary if successful, None if failed
    """
    try:
        # Prepare OAuth token exchange request data
        form_data = {
            "client_id": "mcp_default",
            "subject_token": supabase_token,
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "resource": base_mcp_url.rstrip("/") + "/mcp",
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        
        # Execute token exchange request
        async with aiohttp.ClientSession() as session:
            token_url = base_mcp_url.rstrip("/") + "/oauth/token"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            async with session.post(token_url, headers=headers, data=form_data) as response:
                if response.status == 200:
                    # Successfully obtained token
                    token_data = await response.json()
                    return token_data
                else:
                    # Log error details for debugging
                    response_text = await response.text()
                    logging.error(f"Token exchange failed: {response_text}")
                    
    except Exception as e:
        logging.error(f"Error during token exchange: {e}")
    
    return None

async def get_tokens(config: RunnableConfig):
    """Retrieve stored authentication tokens with expiration validation.
    
    Args:
        config: Runtime configuration containing thread and user identifiers
        
    Returns:
        Token dictionary if valid and not expired, None otherwise
    """
    store = get_store()
    
    # Extract required identifiers from config
    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return None
        
    user_id = config.get("metadata", {}).get("owner")
    if not user_id:
        return None
    
    # Retrieve stored tokens
    tokens = await store.aget((user_id, "tokens"), "data")
    if not tokens:
        return None
    
    # Check token expiration
    expires_in = tokens.value.get("expires_in")  # seconds until expiration
    created_at = tokens.created_at  # datetime of token creation
    current_time = datetime.now(timezone.utc)
    expiration_time = created_at + timedelta(seconds=expires_in)
    
    if current_time > expiration_time:
        # Token expired, clean up and return None
        await store.adelete((user_id, "tokens"), "data")
        return None

    return tokens.value

async def set_tokens(config: RunnableConfig, tokens: dict[str, Any]):
    """Store authentication tokens in the configuration store.
    
    Args:
        config: Runtime configuration containing thread and user identifiers
        tokens: Token dictionary to store
    """
    store = get_store()
    
    # Extract required identifiers from config
    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return
        
    user_id = config.get("metadata", {}).get("owner")
    if not user_id:
        return
    
    # Store the tokens
    await store.aput((user_id, "tokens"), "data", tokens)

async def fetch_tokens(config: RunnableConfig) -> dict[str, Any]:
    """Fetch and refresh MCP tokens, obtaining new ones if needed.
    
    Args:
        config: Runtime configuration with authentication details
        
    Returns:
        Valid token dictionary, or None if unable to obtain tokens
    """
    # Try to get existing valid tokens first
    current_tokens = await get_tokens(config)
    if current_tokens:
        return current_tokens
    
    # Extract Supabase token for new token exchange
    supabase_token = config.get("configurable", {}).get("x-supabase-access-token")
    if not supabase_token:
        return None
    
    # Extract MCP configuration
    mcp_config = config.get("configurable", {}).get("mcp_config")
    if not mcp_config or not mcp_config.get("url"):
        return None
    
    # Exchange Supabase token for MCP tokens
    mcp_tokens = await get_mcp_access_token(supabase_token, mcp_config.get("url"))
    if not mcp_tokens:
        return None

    # Store the new tokens and return them
    await set_tokens(config, mcp_tokens)
    return mcp_tokens

def wrap_mcp_authenticate_tool(tool: StructuredTool) -> StructuredTool:
    """Wrap MCP tool with comprehensive authentication and error handling.
    
    Args:
        tool: The MCP structured tool to wrap
        
    Returns:
        Enhanced tool with authentication error handling
    """
    original_coroutine = tool.coroutine
    
    async def authentication_wrapper(**kwargs):
        """Enhanced coroutine with MCP error handling and user-friendly messages."""
        
        def _find_mcp_error_in_exception_chain(exc: BaseException) -> McpError | None:
            """Recursively search for MCP errors in exception chains."""
            if isinstance(exc, McpError):
                return exc
            
            # Handle ExceptionGroup (Python 3.11+) by checking attributes
            if hasattr(exc, 'exceptions'):
                for sub_exception in exc.exceptions:
                    if found_error := _find_mcp_error_in_exception_chain(sub_exception):
                        return found_error
            return None
        
        try:
            # Execute the original tool functionality
            return await original_coroutine(**kwargs)
            
        except BaseException as original_error:
            # Search for MCP-specific errors in the exception chain
            mcp_error = _find_mcp_error_in_exception_chain(original_error)
            if not mcp_error:
                # Not an MCP error, re-raise the original exception
                raise original_error
            
            # Handle MCP-specific error cases
            error_details = mcp_error.error
            error_code = getattr(error_details, "code", None)
            error_data = getattr(error_details, "data", None) or {}
            
            # Check for authentication/interaction required error
            if error_code == -32003:  # Interaction required error code
                message_payload = error_data.get("message", {})
                error_message = "Required interaction"
                
                # Extract user-friendly message if available
                if isinstance(message_payload, dict):
                    error_message = message_payload.get("text") or error_message
                
                # Append URL if provided for user reference
                if url := error_data.get("url"):
                    error_message = f"{error_message} {url}"
                
                raise ToolException(error_message) from original_error
            
            # For other MCP errors, re-raise the original
            raise original_error
    
    # Replace the tool's coroutine with our enhanced version
    tool.coroutine = authentication_wrapper
    return tool

async def load_mcp_tools(
    config: RunnableConfig,
    existing_tool_names: set[str],
) -> list[BaseTool]:
    """Load and configure MCP (Model Context Protocol) tools with authentication.
    
    Args:
        config: Runtime configuration containing MCP server details
        existing_tool_names: Set of tool names already in use to avoid conflicts
        
    Returns:
        List of configured MCP tools ready for use
    """
    configurable = Configuration.from_runnable_config(config)
    
    # Step 1: Handle authentication if required
    if configurable.mcp_config and configurable.mcp_config.auth_required:
        mcp_tokens = await fetch_tokens(config)
    else:
        mcp_tokens = None
    
    # Step 2: Validate configuration requirements
    config_valid = (
        configurable.mcp_config and 
        configurable.mcp_config.url and 
        configurable.mcp_config.tools and 
        (mcp_tokens or not configurable.mcp_config.auth_required)
    )
    
    if not config_valid:
        return []
    
    # Step 3: Set up MCP server connection
    server_url = configurable.mcp_config.url.rstrip("/") + "/mcp"
    
    # Configure authentication headers if tokens are available
    auth_headers = None
    if mcp_tokens:
        auth_headers = {"Authorization": f"Bearer {mcp_tokens['access_token']}"}
    
    mcp_server_config = {
        "server_1": {
            "url": server_url,
            "headers": auth_headers,
            "transport": "streamable_http"
        }
    }
    # TODO: When Multi-MCP Server support is merged in OAP, update this code
    
    # Step 4: Load tools from MCP server
    try:
        client = MultiServerMCPClient(mcp_server_config)
        available_mcp_tools = await client.get_tools()
    except Exception:
        # If MCP server connection fails, return empty list
        return []
    
    # Step 5: Filter and configure tools
    configured_tools = []
    for mcp_tool in available_mcp_tools:
        # Skip tools with conflicting names
        if mcp_tool.name in existing_tool_names:
            warnings.warn(
                f"MCP tool '{mcp_tool.name}' conflicts with existing tool name - skipping"
            )
            continue
        
        # Only include tools specified in configuration
        if mcp_tool.name not in set(configurable.mcp_config.tools):
            continue
        
        # Wrap tool with authentication handling and add to list
        enhanced_tool = wrap_mcp_authenticate_tool(mcp_tool)
        configured_tools.append(enhanced_tool)
    
    return configured_tools


##########################
# Tool Utils
# 工具获取函数 - 组装所有可用工具
##########################

async def get_search_tool(search_api: SearchAPI):
    """Configure and return search tools based on the specified API provider.
    # 根据指定的 API 提供商配置并返回搜索工具（注：本项目未启用外部搜索）
    
    Args:
        search_api: The search API provider to use (Anthropic, OpenAI, Tavily, or None)
        
    Returns:
        List of configured search tool objects for the specified provider
    """
    if search_api == SearchAPI.ANTHROPIC:
        # Anthropic's native web search with usage limits
        return [{
            "type": "web_search_20250305", 
            "name": "web_search", 
            "max_uses": 5
        }]
        
    elif search_api == SearchAPI.OPENAI:
        # OpenAI's web search preview functionality
        return [{"type": "web_search_preview"}]
        
    elif search_api == SearchAPI.TAVILY:
        # Configure Tavily search tool with metadata
        search_tool = tavily_search
        search_tool.metadata = {
            **(search_tool.metadata or {}), 
            "type": "search", 
            "name": "web_search"
        }
        return [search_tool]
        
    elif search_api == SearchAPI.NONE:
        # No search functionality configured
        return []
        
    # Default fallback for unknown search API types
    return []

async def get_all_tools(config: RunnableConfig):
    """为技术调研组装完整的工具集，包括系统信息查询、思考工具等.

    Args:
        config: 运行时配置，指定搜索API和MCP设置

    Returns:
        所有已配置和可用于技术调研的工具列表
    """
    # 从核心工具开始：完成标记工具、思考工具和系统信息查询工具
    tools = [tool(ResearchComplete), think_tool, get_system_info]

    # 注意：此场景下不使用网络搜索工具，而是使用 get_system_info 查询内部技术文档
    
    # 跟踪现有工具名称以防止冲突
    existing_tool_names = {
        tool.name if hasattr(tool, "name") else tool.get("name", "tool") 
        for tool in tools
    }
    
    # 如果配置了MCP工具则添加（可选）
    mcp_tools = await load_mcp_tools(config, existing_tool_names)
    tools.extend(mcp_tools)
    
    return tools

def get_notes_from_tool_calls(messages: list[MessageLikeRepresentation]):
    """Extract notes from tool call messages."""
    # 从工具调用消息中提取笔记
    return [tool_msg.content for tool_msg in filter_messages(messages, include_types="tool")]

##########################
# Model Provider Native Websearch Utils
# 模型提供商原生网络搜索检测工具
##########################

def anthropic_websearch_called(response):
    """Detect if Anthropic's native web search was used in the response.
    # 检测是否使用了 Anthropic 的原生网络搜索
    
    Args:
        response: The response object from Anthropic's API
        
    Returns:
        True if web search was called, False otherwise
    """
    try:
        # Navigate through the response metadata structure
        usage = response.response_metadata.get("usage")
        if not usage:
            return False
        
        # Check for server-side tool usage information
        server_tool_use = usage.get("server_tool_use")
        if not server_tool_use:
            return False
        
        # Look for web search request count
        web_search_requests = server_tool_use.get("web_search_requests")
        if web_search_requests is None:
            return False
        
        # Return True if any web search requests were made
        return web_search_requests > 0
        
    except (AttributeError, TypeError):
        # Handle cases where response structure is unexpected
        return False

def openai_websearch_called(response):
    """Detect if OpenAI's web search functionality was used in the response.
    # 检测是否使用了 OpenAI 的网络搜索功能
    
    Args:
        response: The response object from OpenAI's API
        
    Returns:
        True if web search was called, False otherwise
    """
    # Check for tool outputs in the response metadata
    tool_outputs = response.additional_kwargs.get("tool_outputs")
    if not tool_outputs:
        return False
    
    # Look for web search calls in the tool outputs
    for tool_output in tool_outputs:
        if tool_output.get("type") == "web_search_call":
            return True
    
    return False


##########################
# Token Limit Exceeded Utils
# Token 超限检测工具
##########################

def is_token_limit_exceeded(exception: Exception, model_name: str = None) -> bool:
    """Determine if an exception indicates a token/context limit was exceeded.
    # 判断异常是否表示 token/上下文限制被超出
    
    Args:
        exception: The exception to analyze
        model_name: Optional model name to optimize provider detection
        
    Returns:
        True if the exception indicates a token limit was exceeded, False otherwise
    """
    error_str = str(exception).lower()
    
    # Step 1: Determine provider from model name if available
    provider = None
    if model_name:
        model_str = str(model_name).lower()
        if model_str.startswith('openai:'):
            provider = 'openai'
        elif model_str.startswith('anthropic:'):
            provider = 'anthropic'
        elif model_str.startswith('gemini:') or model_str.startswith('google:'):
            provider = 'gemini'
    
    # Step 2: Check provider-specific token limit patterns
    if provider == 'openai':
        return _check_openai_token_limit(exception, error_str)
    elif provider == 'anthropic':
        return _check_anthropic_token_limit(exception, error_str)
    elif provider == 'gemini':
        return _check_gemini_token_limit(exception, error_str)
    
    # Step 3: If provider unknown, check all providers
    return (
        _check_openai_token_limit(exception, error_str) or
        _check_anthropic_token_limit(exception, error_str) or
        _check_gemini_token_limit(exception, error_str)
    )

def _check_openai_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates OpenAI token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is an OpenAI exception
    is_openai_exception = (
        'openai' in exception_type.lower() or 
        'openai' in module_name.lower()
    )
    
    # Check for typical OpenAI token limit error types
    is_request_error = class_name in ['BadRequestError', 'InvalidRequestError']
    
    if is_openai_exception and is_request_error:
        # Look for token-related keywords in error message
        token_keywords = ['token', 'context', 'length', 'maximum context', 'reduce']
        if any(keyword in error_str for keyword in token_keywords):
            return True
    
    # Check for specific OpenAI error codes
    if hasattr(exception, 'code') and hasattr(exception, 'type'):
        error_code = getattr(exception, 'code', '')
        error_type = getattr(exception, 'type', '')
        
        if (error_code == 'context_length_exceeded' or
            error_type == 'invalid_request_error'):
            return True
    
    return False

def _check_anthropic_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates Anthropic token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is an Anthropic exception
    is_anthropic_exception = (
        'anthropic' in exception_type.lower() or 
        'anthropic' in module_name.lower()
    )
    
    # Check for Anthropic-specific error patterns
    is_bad_request = class_name == 'BadRequestError'
    
    if is_anthropic_exception and is_bad_request:
        # Anthropic uses specific error messages for token limits
        if 'prompt is too long' in error_str:
            return True
    
    return False

def _check_gemini_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates Google/Gemini token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is a Google/Gemini exception
    is_google_exception = (
        'google' in exception_type.lower() or 
        'google' in module_name.lower()
    )
    
    # Check for Google-specific resource exhaustion errors
    is_resource_exhausted = class_name in [
        'ResourceExhausted', 
        'GoogleGenerativeAIFetchError'
    ]
    
    if is_google_exception and is_resource_exhausted:
        return True
    
    # Check for specific Google API resource exhaustion patterns
    if 'google.api_core.exceptions.resourceexhausted' in exception_type.lower():
        return True
    
    return False

# NOTE: This may be out of date or not applicable to your models. Please update this as needed.
MODEL_TOKEN_LIMITS = {
    "openai:gpt-4.1-mini": 1047576,
    "openai:gpt-4.1-nano": 1047576,
    "openai:gpt-4.1": 1047576,
    "openai:gpt-4o-mini": 128000,
    "openai:gpt-4o": 128000,
    "openai:o4-mini": 200000,
    "openai:o3-mini": 200000,
    "openai:o3": 200000,
    "openai:o3-pro": 200000,
    "openai:o1": 200000,
    "openai:o1-pro": 200000,
    "anthropic:claude-opus-4": 200000,
    "anthropic:claude-sonnet-4": 200000,
    "anthropic:claude-3-7-sonnet": 200000,
    "anthropic:claude-3-5-sonnet": 200000,
    "anthropic:claude-3-5-haiku": 200000,
    "google:gemini-1.5-pro": 2097152,
    "google:gemini-1.5-flash": 1048576,
    "google:gemini-pro": 32768,
    "cohere:command-r-plus": 128000,
    "cohere:command-r": 128000,
    "cohere:command-light": 4096,
    "cohere:command": 4096,
    "mistral:mistral-large": 32768,
    "mistral:mistral-medium": 32768,
    "mistral:mistral-small": 32768,
    "mistral:mistral-7b-instruct": 32768,
    "ollama:codellama": 16384,
    "ollama:llama2:70b": 4096,
    "ollama:llama2:13b": 4096,
    "ollama:llama2": 4096,
    "ollama:mistral": 32768,
    "bedrock:us.amazon.nova-premier-v1:0": 1000000,
    "bedrock:us.amazon.nova-pro-v1:0": 300000,
    "bedrock:us.amazon.nova-lite-v1:0": 300000,
    "bedrock:us.amazon.nova-micro-v1:0": 128000,
    "bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0": 200000,
    "bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0": 200000,
    "bedrock:us.anthropic.claude-opus-4-20250514-v1:0": 200000,
    "anthropic.claude-opus-4-1-20250805-v1:0": 200000,
}

def get_model_token_limit(model_string):
    """Look up the token limit for a specific model.
    
    Args:
        model_string: The model identifier string to look up
        
    Returns:
        Token limit as integer if found, None if model not in lookup table
    """
    # Search through known model token limits
    for model_key, token_limit in MODEL_TOKEN_LIMITS.items():
        if model_key in model_string:
            return token_limit
    
    # Model not found in lookup table
    return None

def remove_up_to_last_ai_message(messages: list[MessageLikeRepresentation]) -> list[MessageLikeRepresentation]:
    """Truncate message history by removing up to the last AI message.
    
    This is useful for handling token limit exceeded errors by removing recent context.
    
    Args:
        messages: List of message objects to truncate
        
    Returns:
        Truncated message list up to (but not including) the last AI message
    """
    # Search backwards through messages to find the last AI message
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage):
            # Return everything up to (but not including) the last AI message
            return messages[:i]
    
    # No AI messages found, return original list
    return messages

##########################
# Misc Utils
# 其他工具函数
##########################

def get_today_str() -> str:
    """Get current date formatted for display in prompts and outputs.
    # 获取当前日期字符串（用于提示词和输出）
    
    Returns:
        Human-readable date string in format like 'Mon Jan 15, 2024'
    """
    now = datetime.now()
    return f"{now:%a} {now:%b} {now.day}, {now:%Y}"

def get_config_value(value):
    """Extract value from configuration, handling enums and None values."""
    # 从配置中提取值（处理枚举和 None 值）
    if value is None:
        return None
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        return value
    else:
        return value.value

def get_api_key_for_model(model_name: str, config: RunnableConfig):
    """Get API key for a specific model from environment or config."""
    # 从环境变量或配置中获取指定模型的 API 密钥
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false")
    model_name = model_name.lower()
    if should_get_from_config.lower() == "true":
        api_keys = config.get("configurable", {}).get("apiKeys", {})
        if not api_keys:
            return None
        if model_name.startswith("openai:"):
            return api_keys.get("OPENAI_API_KEY")
        elif model_name.startswith("anthropic:"):
            return api_keys.get("ANTHROPIC_API_KEY")
        elif model_name.startswith("google"):
            return api_keys.get("GOOGLE_API_KEY")
        return None
    else:
        if model_name.startswith("openai:"): 
            return os.getenv("OPENAI_API_KEY")
        elif model_name.startswith("anthropic:"):
            return os.getenv("ANTHROPIC_API_KEY")
        elif model_name.startswith("google"):
            return os.getenv("GOOGLE_API_KEY")
        return None

def get_tavily_api_key(config: RunnableConfig):
    """Get Tavily API key from environment or config."""
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false")
    if should_get_from_config.lower() == "true":
        api_keys = config.get("configurable", {}).get("apiKeys", {})
        if not api_keys:
            return None
        return api_keys.get("TAVILY_API_KEY")
    else:
        return os.getenv("TAVILY_API_KEY")
