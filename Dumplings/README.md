# Dumplings 库使用文档

## 目录

1. [简介](#简介)
2. [安装与配置](#安装与配置)
3. [核心组件](#核心组件)
4. [快速开始](#快速开始)
5. [API 参考](#api-参考)
6. [高级功能](#高级功能)
7. [最佳实践](#最佳实践)
8. [常见问题](#常见问题)

---

## 简介

**Dumplings** 是一个轻量级多 Agent 协作框架，支持：

- ✅ 多 Agent 注册与发现
- ✅ 工具注册与权限控制
- ✅ 两种调用模式：Function Calling / XML
- ✅ Agent 间通信协作
- ✅ MCP (Model Context Protocol) 服务器集成
- ✅ 流式响应与多模态支持

---

## 安装与配置

### 环境依赖

```bash
pip install requests beautifulsoup4 loguru pydantic python-dotenv
# MCP 支持（可选）
pip install mcp
```

### 环境配置

创建 `.env` 文件配置 API 密钥：

```env
API_KEY=your_api_key_here
```

---

## 核心组件

### 组件架构图

```
Dumplings/
├── __init__.py        # 模块导出
├── agent_list.py      # Agent 注册与发现
├── Agent_Base_.py     # Agent 基类与核心逻辑
├── agent_tool.py      # 工具注册器
└── mcp_bridge.py      # MCP 服务器桥接
```

| 模块 | 说明 |
|------|------|
| `agent_list.py` | Agent 注册表，支持 UUID 和名称双键访问 |
| `Agent_Base_.py` | Agent 基类，包含对话、工具调用等核心逻辑 |
| `agent_tool.py` | 工具注册器，支持权限控制和 schema 生成 |
| `mcp_bridge.py` | MCP 服务器桥接，将 MCP 工具转换为标准工具 |

---

## 快速开始

### 完整示例

```python
import sys
from dotenv import load_dotenv
import os
import Dumplings
import uuid

load_dotenv()

# 1. 注册工具
@Dumplings.tool_registry.register_tool(
    allowed_agents=["8841cd45eef54217bc8122cafebe5fd6", "time_agent"],
    name="get_time",
    description="获取当前时间",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_time(xml=None):
    return "11:03"

# 2. 注册 Agent - 调度 Agent
@Dumplings.register_agent(uuid.uuid4().hex, "scheduling_agent")
class scheduling_agent(Dumplings.BaseAgent):
    """你可以用<ask_for_help>的方式与其他 Agent 通讯"""
    prompt = "你是一个名为汤圆 Agent 的 AGI"
    api_provider = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    model_name = "deepseek-v3.2"
    api_key = os.getenv("API_KEY")
    fc_model = True  # 启用 Function Calling 模式

    def __init__(self):
        super().__init__()

# 3. 注册 Agent - 时间管理者
@Dumplings.register_agent("8841cd45eef54217bc8122cafebe5fd6", "time_agent")
class time_agent(Dumplings.BaseAgent):
    """你可以通过工具获取时间"""
    prompt = "你是一个名为汤圆 Agent 的 AGI 的子 agent 名为时间管理者"
    api_provider = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    model_name = "deepseek-v3.2"
    api_key = os.getenv("API_KEY")

    def __init__(self):
        super().__init__()

# 4. 运行
if __name__ == "__main__":
    schedule_agent = Dumplings.agent_list["scheduling_agent"]
    schedule_agent.conversation_with_tool(
        "你现在有一个 id 为 8841cd45eef54217bc8122cafebe5fd6 的同伴，请求它帮你查看现在时间"
    )
```

---

## API 参考

### 1. Agent 注册 (`agent_list.py`)

#### `register_agent(uuid, name)` - Agent 注册装饰器

```python
import Dumplings

@Dumplings.register_agent("unique-uuid-here", "agent_name")
class MyAgent(Dumplings.BaseAgent):
    """Agent 描述文档字符串"""
    prompt = "你是一个助手"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = "gpt-4"
    api_key = os.getenv("API_KEY")

    def __init__(self):
        super().__init__()
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `uuid` | str | Agent 唯一标识符 |
| `name` | str | Agent 名称（也可用于访问） |

**注意**：装饰器会自动实例化类，`agent_list` 中存储的是实例对象。

### 2. 工具注册 (`agent_tool.py`)

#### `tool_registry.register_tool()` - 工具注册装饰器

```python
@Dumplings.tool_registry.register_tool(
    allowed_agents=["agent-uuid", "agent_name"],
    name="get_weather",
    description="获取天气信息",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称"}
        },
        "required": ["city"]
    }
)
def get_weather(city: str) -> str:
    return f"{city} 的天气：晴"
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `allowed_agents` | str/List[str] | None | 允许使用的 Agent（UUID 或名称），None 表示全部开放 |
| `name` | str | 函数名 | 工具名称 |
| `description` | str | "" | 工具描述 |
| `parameters` | dict | 空对象 | OpenAI Function Calling schema |

#### 工具注册器其他方法

```python
# 检查 Agent 是否有工具使用权限
Dumplings.tool_registry.check_permission(agent_uuid, tool_name)

# 获取工具信息
Dumplings.tool_registry.get_tool_info(tool_name)

# 获取 Agent 有权限的所有工具 schema
Dumplings.tool_registry.get_all_tools_schema(agent_uuid)

# 获取 Agent 有权限的所有工具信息
Dumplings.tool_registry.get_all_tools_info(agent_uuid)
```

### 3. BaseAgent 核心类 (`Agent_Base_.py`)

#### 类属性配置

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | str | ✅ | Agent 系统提示词 |
| `api_provider` | str | ✅ | API 端点 URL |
| `model_name` | str | ✅ | 模型名称 |
| `api_key` | str | ✅ | API 密钥 |
| `fc_model` | bool | ❌ | 是否启用 Function Calling 模式（默认 False，使用 XML 模式） |

#### 核心方法

##### `conversation_with_tool(messages=None, tool=False, images=None)`

主对话方法，支持多模态和工具调用。

```python
agent = Dumplings.agent_list["my_agent"]
agent.conversation_with_tool("你好，请帮我查询天气")
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `messages` | str | 用户输入消息 |
| `tool` | bool | 是否为工具调用后的继续对话（内部使用） |
| `images` | list | 图片列表（base64 或 URL） |

### 4. 内置工具

所有 Agent 自动拥有以下内置工具：

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `ask_for_help` | 请求其他 Agent 帮助 | `agent_id`, `message` |
| `list_agents` | 列出所有可用 Agent | 无 |
| `attempt_completion` | 标记任务完成并退出 | `report_content` |

---

## 高级功能

### 1. 两种调用模式

#### Function Calling 模式（推荐）

配置 `fc_model = True`，模型返回标准工具调用格式：

```python
class MyAgent(Dumplings.BaseAgent):
    fc_model = True  # 启用 Function Calling
```

工具调用示例（由模型自动生成）：
```json
{
  "name": "get_time",
  "arguments": {}
}
```

#### XML 模式（传统）

默认模式，模型返回 XML 格式工具调用：

```xml
<get_time></get_time>
```

### 2. Agent 间通信

使用 `ask_for_help` 工具请求其他 Agent：

**Function Calling 方式：**
```python
# 模型自动调用
ask_for_help(agent_id="time_agent", message="请告诉我现在的时间")
```

**XML 方式：**
```xml
<ask_for_help>
    <agent_id>time_agent</agent_id>
    <message>请告诉我现在的时间</message>
</ask_for_help>
```

### 3. 多模态支持

```python
agent.conversation_with_tool(
    messages="这张图片里有什么？",
    images=["https://example.com/image.jpg"]  # 或 base64 字符串
)
```

### 4. MCP 服务器集成

```python
from Dumplings.mcp_bridge import register_mcp_tools

# 注册 MCP 服务器的所有工具
register_mcp_tools(
    server_path="path/to/mcp_server.py",
    register_resources=True,  # 是否注册资源为工具
    allowed_agents=None       # 限制 Agent 访问（可选）
)
```

#### MCP 相关方法

```python
# 关闭指定 MCP 会话
Dumplings.mcp_bridge.close_mcp_session_sync("path/to/mcp_server.py")

# 关闭所有 MCP 会话
Dumplings.mcp_bridge.close_all_mcp_sessions_sync()

# 获取会话信息
Dumplings.mcp_bridge.get_session_info()  # 获取所有会话
Dumplings.mcp_bridge.get_session_info("path/to/mcp_server.py")  # 获取指定会话
```

### 5. 日志配置

Dumplings 使用 `loguru` 记录详细日志：

```bash
# 设置日志级别
export LOGURU_LEVEL=DEBUG  # TRACE/DEBUG/INFO/WARNING/ERROR
```

日志文件位置：`logs/app.log`

日志轮转配置：
- 单个文件最大：500 MB
- 保留天数：10 天
- 压缩：是

---

## 最佳实践

### 1. Agent 设计原则

- **单一职责**：每个 Agent 专注于特定领域
- **清晰文档**：在类文档字符串中说明 Agent 能力和可用工具
- **权限最小化**：工具只开放给需要的 Agent

### 2. 工具命名规范

```python
# 好：清晰描述功能
@tool_registry.register_tool(name="get_weather", description="获取指定城市的天气信息")

# 避免：模糊命名
@tool_registry.register_tool(name="tool1", description="一个工具")
```

### 3. 错误处理

工具函数应处理异常并返回有意义的错误信息：

```python
@tool_registry.register_tool(name="read_file", description="读取文件内容")
def read_file(path: str) -> str:
    try:
        with open(path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return f"错误：文件不存在 - {path}"
```

### 4. Agent UUID 生成

```python
import uuid

# 推荐：使用 uuid4 生成唯一标识
@Dumplings.register_agent(uuid.uuid4().hex, "my_agent")

# 或使用固定 UUID（便于其他 Agent 引用）
@Dumplings.register_agent("8841cd45eef54217bc8122cafebe5fd6", "time_agent")
```

---

## 常见问题

### Q: 如何调试工具调用？

A: 设置 `LOGURU_LEVEL=TRACE` 查看详细调用日志：

```bash
# Linux/Mac
export LOGURU_LEVEL=TRACE
python agent.py

# Windows (PowerShell)
$env:LOGURU_LEVEL="TRACE"
python agent.py

# Windows (CMD)
set LOGURU_LEVEL=TRACE
python agent.py
```

### Q: Function Calling 和 XML 模式能混用吗？

A: 可以，但不推荐。建议统一使用 Function Calling 模式，它更符合标准且易于维护。

### Q: 如何查看已注册的 Agent？

A: 调用任意 Agent 的 `list_agents()` 工具，或直接访问 `Dumplings.agent_list`。

### Q: 工具注册后为什么无法使用？

A: 检查以下几点：
1. 工具是否正确注册（查看日志确认）
2. Agent 是否在 `allowed_agents` 列表中
3. 如果 `allowed_agents` 为 None，则所有 Agent 可用

### Q: 如何添加自定义输出处理？

A: 重写 Agent 的 `out` 方法：

```python
class MyAgent(Dumplings.BaseAgent):
    def out(self, content):
        # 自定义输出逻辑
        if content.get("tool_name"):
            print(f"[工具] {content.get('tool_name')}: {content.get('tool_parameter')}")
        elif not content.get("task"):
            print(f"[回复] {content.get('message')}")
```

### Q: MCP 工具注册失败怎么办？

A: 检查：
1. MCP 服务器脚本路径是否正确
2. MCP 服务器是否可独立运行
3. 查看 `logs/app.log` 中的详细错误信息

---

## 更新日志

- **当前版本**：初始版本
- 支持 Function Calling 和 XML 两种工具调用模式
- 支持多 Agent 协作通信
- 支持 MCP 服务器集成
- 支持多模态输入（文本 + 图片）
- 详细的日志记录