import sys
from dotenv import load_dotenv
import os
import Dumplings
import uuid
# from Dumplings import tool_registry

# 测试用
try:
    with open("logs/app.log", mode="w") as a:
        a.write()
except:
    pass

load_dotenv()

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
    # 兼容两种调用方式：Function Calling（无参数）和 XML（接收xml字符串）
    return "11:03"

@Dumplings.register_agent(uuid.uuid4().hex, "scheduling_agent")
class scheduling_agent(Dumplings.BaseAgent):
    """，你可以用<ask_for_help><agent_id>id</agent_id><message>message</message></ask_for_help>的方式与其他Agent通讯, 你可以使用<attempt_completion>标签直接退出对话（你不可再次获得任何信息）， 它的语法为<attempt_completion><report_content>放入你想播报的内容，或留空</report_content></attempt_completion>"""
    prompt = f"你是一个名为汤圆Agent的AGI"
    api_provider = "https://coding.dashscope.aliyuncs.com/v1/chat/completions"
    model_name = "qwen3.5-plus"
    api_key = os.getenv("API_KEY")
    fc_model = True
    def __init__(self):
        super().__init__()

    def out(self, content):
        #你可以通过劫持out获取内容
        if content.get("tool_name"):
            print("调用工具:", content.get("tool_name"), "参数", content.get("tool_parameter"))
            return
        if not content.get("task"):
            print(content.get("message"), end="")
        else:
            print()


@Dumplings.register_agent("8841cd45eef54217bc8122cafebe5fd6", "time_agent")
class time_agent(Dumplings.BaseAgent):
    """，你可以用<ask_for_help><agent_id>id</agent_id><message>message</message></ask_for_help>的方式与其他Agent通讯, 你还有get_time可以查询时间（直接<get_time></get_time>即可）"""
    prompt = "你是一个名为汤圆Agent的AGI的子agent名为时间管理者， 你可以通过工具获取时间"
    api_provider = "https://coding.dashscope.aliyuncs.com/v1/chat/completions"
    model_name = "qwen3.5-plus"
    api_key = os.getenv("API_KEY")
    def __init__(self):
        super().__init__()


if __name__ == "__main__":
    schedule_agent = Dumplings.agent_list["scheduling_agent"]
    # schedule_agent.conversation_with_tool("你好")
    schedule_agent.conversation_with_tool("你现在有一个id为8841cd45eef54217bc8122cafebe5fd6的同伴，请求它帮你查看现在时间")

