# -*- coding: utf-8 -*-
"""
MCP Bridge - 将 MCP 服务器工具转换为标准工具（非XML）
使用 Dumplings.tool_registry.register_tool 直接注册
"""
import asyncio
import os
import threading
from typing import Optional, Dict, Any, Callable
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .agent_tool import tool_registry
from loguru import logger


# ==================== 全局会话池 ====================
MCP_SESSION_POOL: Dict[str, Dict[str, Any]] = {}
SESSION_LOCK = threading.Lock()


async def _initialize_mcp_session(server_path: str) -> Dict[str, Any]:
    """
    异步初始化 MCP 服务器会话
    如果会话已存在则直接返回
    """
    global MCP_SESSION_POOL

    with SESSION_LOCK:
        # 检查会话是否已存在
        if server_path in MCP_SESSION_POOL:
            session_info = MCP_SESSION_POOL[server_path]
            if session_info.get("initialized"):
                logger.debug(f"MCP 会话已存在: {server_path}")
                return session_info

        # 会话不存在或未初始化,创建新会话
        logger.info(f"正在初始化 MCP 会话: {server_path}")

        # 验证文件存在
        if not os.path.isfile(server_path):
            raise FileNotFoundError(f"MCP 服务器脚本不存在: {server_path}")

        # 确定执行命令
        cmd = "python" if server_path.endswith(".py") else "node"
        logger.debug(f"使用命令启动 MCP 服务器: {cmd} {server_path}")

        try:
            # 创建 stdio 客户端
            params = StdioServerParameters(command=cmd, args=[server_path], env=None)

            # 注意: __aenter__ 返回的是 (transport, session)
            # transport 是 (reader, writer) 元组
            stdio_ctx = stdio_client(params)
            transport = await stdio_ctx.__aenter__()
            reader, writer = transport
            session = ClientSession(reader, writer)

            # 初始化会话
            await session.__aenter__()
            await session.initialize()

            # 获取工具列表
            tools_response = await session.list_tools()
            tools = tools_response.tools
            logger.info(f"MCP 服务器 {server_path} 共有 {len(tools)} 个工具")

            # 获取资源列表
            resources_response = await session.list_resources()
            resources = resources_response.resources
            logger.info(f"MCP 服务器 {server_path} 共有 {len(resources)} 个资源")

            # 保存到会话池
            session_info = {
                "session": session,
                "transport": transport,
                "context": stdio_ctx,
                "tools": tools,
                "resources": resources,
                "initialized": True,
                "server_path": server_path
            }
            MCP_SESSION_POOL[server_path] = session_info

            logger.success(f"MCP 会话初始化成功: {server_path}")
            return session_info

        except Exception as e:
            logger.error(f"MCP 会话初始化失败 {server_path}: {e}")
            # 清理可能已创建的部分资源
            if server_path in MCP_SESSION_POOL:
                del MCP_SESSION_POOL[server_path]
            raise


def _make_tool_wrapper(tool_name: str, server_path: str, input_schema: Dict[str, Any]):
    """
    创建工具包装器
    将 MCP 工具转换为标准工具，支持同步调用
    """
    def sync_wrapper(**kwargs) -> str:
        try:
            # 从会话池获取 session
            with SESSION_LOCK:
                session_info = MCP_SESSION_POOL.get(server_path)

                if not session_info or not session_info.get("initialized"):
                    error_msg = f"MCP 会话未初始化: {server_path}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                session = session_info["session"]

            # 在新事件循环中执行异步调用
            # 避免嵌套事件循环问题
            loop = asyncio.new_event_loop()
            try:
                logger.trace(f"调用 MCP 工具: {tool_name} @ {server_path}, args={kwargs}")
                result = loop.run_until_complete(session.call_tool(tool_name, kwargs))
                content = result.content or ""
                logger.debug(f"工具 {tool_name} 返回: {content[:100]}")
                return content
            except Exception as e:
                error_msg = f"调用工具失败 {tool_name}: {str(e)}"
                logger.error(error_msg)
                raise
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"执行工具 {tool_name} 出错: {e}")
            raise

    return sync_wrapper


def _make_resource_wrapper(resource_uri: str, server_path: str):
    """
    创建资源包装器
    将 MCP 资源转换为工具，支持同步调用
    """
    def sync_wrapper() -> str:
        try:
            # 从会话池获取 session
            with SESSION_LOCK:
                session_info = MCP_SESSION_POOL.get(server_path)

                if not session_info or not session_info.get("initialized"):
                    error_msg = f"MCP 会话未初始化: {server_path}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                session = session_info["session"]

            # 在新事件循环中执行
            loop = asyncio.new_event_loop()
            try:
                logger.trace(f"读取 MCP 资源: {resource_uri} @ {server_path}")
                result = loop.run_until_complete(session.read_resource(resource_uri))
                content = result.contents or ""
                logger.debug(f"资源 {resource_uri} 内容长度: {len(content)}")
                return content
            except Exception as e:
                error_msg = f"读取资源失败 {resource_uri}: {str(e)}"
                logger.error(error_msg)
                raise
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"访问资源 {resource_uri} 出错: {e}")
            raise

    return sync_wrapper


def _convert_mcp_schema_to_openai(mcp_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 MCP 的 inputSchema 转换为 OpenAI Function Calling 格式
    """
    if not mcp_schema:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    # MCP schema 已经是 JSON Schema 格式，直接返回
    # 确保包含必需字段
    result = {
        "type": "object",
        "properties": mcp_schema.get("properties", {}),
        "required": mcp_schema.get("required", [])
    }
    return result


async def register_mcp_tools_async(
    server_path: str,
    register_resources: bool = True,
    allowed_agents=None
) -> int:
    """
    异步注册 MCP 服务器的所有工具为标准工具（非XML）

    Args:
        server_path: MCP 服务器脚本路径
        register_resources: 是否注册资源为工具 (默认 True)
        allowed_agents: 允许使用这些工具的 Agent 列表 (None 表示所有 Agent)

    Returns:
        int: 注册成功的工具数量
    """
    try:
        # 初始化会话
        session_info = await _initialize_mcp_session(server_path)

        tools = session_info["tools"]
        resources = session_info["resources"]

        registered_count = 0

        # 注册工具
        for tool in tools:
            tool_name = tool.name
            desc = tool.description or f"MCP 工具: {tool_name}"
            input_schema = tool.inputSchema

            logger.debug(f"注册工具: {tool_name}")

            # 转换 schema
            openai_schema = _convert_mcp_schema_to_openai(input_schema)

            # 创建包装器并注册
            wrapper = _make_tool_wrapper(tool_name, server_path, input_schema)

            tool_registry.register_tool(
                name=tool_name,
                description=desc,
                allowed_agents=allowed_agents,
                parameters=openai_schema
            )(wrapper)

            registered_count += 1
            logger.success(f"已注册标准工具 <{tool_name}>")

        # 注册资源 (如果启用)
        if register_resources and resources:
            for resource in resources:
                # 从 URI 提取工具名 (移除特殊字符)
                uri = resource.uri
                # 创建资源工具名: 例如 file_test_txt
                resource_name = f"read_{uri.split('://')[-1].replace('/', '_').replace('.', '_')}"
                desc = f"读取 MCP 资源: {uri}"

                logger.debug(f"注册资源工具: {resource_name} ({uri})")

                # 创建包装器并注册
                wrapper = _make_resource_wrapper(uri, server_path)

                tool_registry.register_tool(
                    name=resource_name,
                    description=desc,
                    allowed_agents=allowed_agents,
                    parameters={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                )(wrapper)

                registered_count += 1
                logger.success(f"已注册资源工具 <{resource_name}>")

        logger.info(f"MCP 服务器 {server_path} 共注册 {registered_count} 个工具")
        return registered_count

    except Exception as e:
        logger.error(f"注册 MCP 工具失败 {server_path}: {e}")
        raise


def register_mcp_tools(
    server_path: str,
    register_resources: bool = True,
    allowed_agents=None
) -> int:
    """
    同步入口: 注册 MCP 服务器的所有工具为标准工具

    Args:
        server_path: MCP 服务器脚本路径
        register_resources: 是否注册资源为工具 (默认 True)
        allowed_agents: 允许使用这些工具的 Agent 列表 (None 表示所有 Agent)

    Returns:
        int: 注册成功的工具数量

    Example:
        >>> register_mcp_tools("path/to/mcp_server.py")
        3
    """
    if not os.path.isfile(server_path):
        raise FileNotFoundError(f"MCP 服务器脚本不存在: {server_path}")

    # 运行异步注册
    return asyncio.run(
        register_mcp_tools_async(server_path, register_resources, allowed_agents)
    )


async def close_mcp_session(server_path: str) -> bool:
    """
    异步关闭指定的 MCP 会话

    Args:
        server_path: MCP 服务器脚本路径

    Returns:
        bool: 是否成功关闭
    """
    global MCP_SESSION_POOL

    with SESSION_LOCK:
        session_info = MCP_SESSION_POOL.get(server_path)

        if not session_info:
            logger.warning(f"MCP 会话不存在: {server_path}")
            return False

        try:
            logger.info(f"正在关闭 MCP 会话: {server_path}")

            # 关闭会话
            session = session_info.get("session")
            context = session_info.get("context")

            if session:
                await session.__aexit__(None, None, None)
            if context:
                await context.__aexit__(None, None, None)

            # 从池中移除
            del MCP_SESSION_POOL[server_path]

            logger.success(f"MCP 会话已关闭: {server_path}")
            return True

        except Exception as e:
            logger.error(f"关闭 MCP 会话失败 {server_path}: {e}")
            # 即使失败也从池中移除,避免残留
            if server_path in MCP_SESSION_POOL:
                del MCP_SESSION_POOL[server_path]
            return False


def close_mcp_session_sync(server_path: str) -> bool:
    """
    同步关闭指定的 MCP 会话
    """
    return asyncio.run(close_mcp_session(server_path))


async def close_all_mcp_sessions() -> int:
    """
    异步关闭所有 MCP 会话

    Returns:
        int: 成功关闭的会话数量
    """
    global MCP_SESSION_POOL

    closed_count = 0

    # 复制键列表,避免在遍历时修改字典
    server_paths = list(MCP_SESSION_POOL.keys())

    for server_path in server_paths:
        try:
            if await close_mcp_session(server_path):
                closed_count += 1
        except Exception as e:
            logger.error(f"关闭会话时出错 {server_path}: {e}")
            continue

    logger.info(f"共关闭 {closed_count} 个 MCP 会话")
    return closed_count


def close_all_mcp_sessions_sync() -> int:
    """
    同步关闭所有 MCP 会话
    """
    return asyncio.run(close_all_mcp_sessions())


def get_session_info(server_path: Optional[str] = None) -> Dict[str, Any]:
    """
    获取会话信息

    Args:
        server_path: MCP 服务器脚本路径 (如果为 None,返回所有会话)

    Returns:
        Dict: 会话信息
    """
    with SESSION_LOCK:
        if server_path is None:
            return {
                path: {
                    "initialized": info.get("initialized", False),
                    "tools_count": len(info.get("tools", [])),
                    "resources_count": len(info.get("resources", []))
                }
                for path, info in MCP_SESSION_POOL.items()
            }
        else:
            info = MCP_SESSION_POOL.get(server_path)
            if info:
                return {
                    "initialized": info.get("initialized", False),
                    "tools_count": len(info.get("tools", [])),
                    "resources_count": len(info.get("resources", [])),
                    "tools": [t.name for t in info.get("tools", [])],
                    "resources": [r.uri for r in info.get("resources", [])]
                }
            return {}


# ==================== 兼容性接口 ====================
# 保留旧接口名,向后兼容
connect_and_register = register_mcp_tools