# Dumplings 库文档

## 快速开始

### 安装依赖

```bash
uv sync
```

### 环境配置

创建 `.env` 文件：

```
API_KEY=your_api_key_here
```

---

## 工具注册

Dumplings 支持两种工具调用方式：**Function Calling** 和 **XML**。

### 注册工具

```python
import Dumplings

@Dumplings.tool_registry.register_tool(
    allowed_agents=["my_agent"],
    name="get_time",
    description="获取当前时间",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def get_time():
    """获取当前时间"""
    return "11:03"
```

### 工具函数签名

工具函数支持以下参数形式：

```python
# 无参数工具
@Dumplings.tool_registry.register_tool(name="get_time")
def get_time():
    return "11:03"

# 单参数工具
@Dumplings.tool_registry.register_tool(name="search")
def search(query: str):
    return f"搜索结果：{query}"

# 多参数工具
@Dumplings.tool_registry.register_tool(
    name="calculate",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
            "op": {"type": "string"}
        },
        "required": ["a", "b", "op"]
    }
)
def calculate(a: float, b: float, op: str):
    if op == "add":
        return a + b
    return a - b
```

---

## Agent 定义

### 基本 Agent

```python
import Dumplings
import os

@Dumplings.register_agent("unique_uuid", "agent_name")
class MyAgent(Dumplings.BaseAgent):
    prompt = "你是一个有用的助手"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = "qwen3.5-plus"
    api_key = os.getenv("API_KEY")

    def __init__(self):
        super().__init__()
```

### 启用 Function Calling

```python
@Dumplings.register_agent("uuid", "fc_agent")
class FCAgent(Dumplings.BaseAgent):
    prompt = "你是一个支持工具调用的 Agent"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = "qwen3.5-plus"
    api_key = os.getenv("API_KEY")
    fc_model = True  # 启用 Function Calling 模式
```

### 自定义输出

```python
@Dumplings.register_agent("uuid", "custom_agent")
class CustomAgent(Dumplings.BaseAgent):
    prompt = "你是一个自定义输出的 Agent"
    api_provider = "https://api.example.com/v1/chat/completions"
    model_name = "qwen3.5-plus"
    api_key = os.getenv("API_KEY")

    def out(self, content):
        """自定义输出处理"""
        if content.get("tool_name"):
            print(f"[工具] {content.get('tool_name')}: {content.get('tool_parameter')}")
            return
        if content.get("message"):
            print(content.get("message"), end="")
```

---

## Agent 间通讯

Agent 可以使用 `ask_for_help` 方法请求其他 Agent 帮助。

### Function Calling 方式

```python
# AI 会自动调用 ask_for_help 工具
agent.conversation_with_tool("请请求时间 Agent 查询当前时间")
```

AI 会生成类似以下调用：

```python
ask_for_help(agent_id="time_agent", message="请查询当前时间")
```

### XML 方式

AI 也可以生成 XML 格式的请求：

```xml
<ask_for_help>
    <agent_id>time_agent</agent_id>
    <message>请查询当前时间</message>
</ask_for_help>
```

### 手动调用

```python
from Dumplings import agent_list

# 获取目标 Agent
time_agent = agent_list["time_agent"]

# 发送请求
response = time_agent.conversation_with_tool("现在几点了？")
```

---

## 使用 Agent

### 获取 Agent 实例

```python
from Dumplings import agent_list

# 通过 UUID 获取
agent = agent_list["unique_uuid"]

# 通过名称获取
agent = agent_list["agent_name"]
```

### 运行对话

```python
# 简单对话
agent.conversation_with_tool("你好")

# 带工具调用的对话
agent.conversation_with_tool("请帮我查询北京今天的天气")

# 多模态对话（文本 + 图片）
agent.conversation_with_tool(
    "这张图片里有什么？",
    images=["base64_encoded_image_or_url"]
)
```

---

## MCP 集成

### 注册 MCP 服务器工具

```python
from Dumplings.mcp_bridge import register_mcp_tools

# 注册 MCP 服务器的所有工具
count = register_mcp_tools("path/to/mcp_server.py")
print(f"注册了 {count} 个工具")
```

### 使用会话池

```python
from Dumplings.mcp_bridge import _global_session_pool, start_health_check

# 启动健康检查（每 5 分钟检查一次）
start_health_check(interval=300)

# 获取会话信息
info = _global_session_pool.get_session_info()
print(f"当前会话：{info}")

# 关闭所有会话
_global_session_pool.close_all()
```

---

## 日志配置

### 统一日志模块

```python
from Dumplings.logging_config import setup_logging, get_logger

# 自定义日志配置
setup_logging(
    log_dir="logs",
    rotation="500 MB",
    retention="10 days",
    level="DEBUG"  # 或从环境变量 LOGURU_LEVEL 读取
)

# 获取 logger
logger = get_logger("my_module")
logger.info("应用启动")
```

### 环境变量

```bash
# 设置日志级别
export LOGURU_LEVEL=DEBUG

# 禁用自动初始化
export LOGURU_DISABLED=1
```

---

## API 参考

### Dumplings.BaseAgent

基类，所有 Agent 必须继承此类。

**抽象属性**：
- `api_key` - API 密钥
- `api_provider` - API 提供商 URL
- `model_name` - 模型名称
- `prompt` - 系统提示词

**通用方法**：
- `conversation_with_tool(messages, tool=False, images=None)` - 进行对话
- `ask_for_help(agent_id, message)` - 请求其他 Agent 帮助
- `list_agents()` - 列出所有可用 Agent
- `attempt_completion(report_content)` - 标记任务完成

### Dumplings.register_agent(uuid, name)

Agent 注册装饰器。

**参数**：
- `uuid` - Agent 的唯一标识符
- `name` - Agent 的人类可读名称

### Dumplings.tool_registry.register_tool(...)

工具注册装饰器。

**参数**：
- `allowed_agents` - 允许使用此工具的 Agent 列表
- `name` - 工具名称
- `description` - 工具描述
- `parameters` - OpenAI Function Calling schema

---

## 常见问题

### Q: 如何在 Agent 之间传递消息？

A: 使用 `ask_for_help` 方法：

```python
# AI 自动生成调用
agent.conversation_with_tool("请请求时间 Agent 帮助")
```

或手动调用：

```python
from Dumplings import agent_list
target = agent_list["other_agent"]
response = target.conversation_with_tool("你好")
```

### Q: 如何自定义工具？

A: 使用 `register_tool` 装饰器：

```python
@Dumplings.tool_registry.register_tool(
    name="my_tool",
    description="我的工具"
)
def my_tool(param1: str, param2: int):
    return f"{param1}: {param2}"
```

### Q: 如何集成 MCP 服务器？

A: 使用 `register_mcp_tools` 函数：

```python
from Dumplings.mcp_bridge import register_mcp_tools
register_mcp_tools("mcp_server.py")
```

### Q: 如何处理 Agent 的错误？

A: 重写 `out` 方法或使用日志：

```python
from Dumplings.logging_config import logger

try:
    agent.conversation_with_tool("...")
except Exception as e:
    logger.error(f"Agent 错误：{e}")
```

### Q: 如何保存对话历史？

A: 对话历史保存在 `agent.history` 中：

```python
# 查看历史
print(agent.history)

# 保存历史
import json
with open("history.json", "w") as f:
    json.dump(agent.history, f)
```