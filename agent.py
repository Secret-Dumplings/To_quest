import json
import base64
import time
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import Dumplings
import mss
import mss.tools
import pyautogui

# from openai import OpenAI


@dataclass
class Action:
    action_type: str
    parameters: Dict[str, Any]
    thought: str


@Dumplings.register_agent("screen_agent", "screen_agent")
class screen_agent(Dumplings.BaseAgent):
    fc_model = True

    def __init__(self, config_path: str = "config.json"):
        # 设置 prompt
        self.prompt = """你是一个电脑操作助手。你的任务是根据用户的指令，通过一系列操作来完成用户的任务。

        每次响应必须返回一个 JSON 对象，格式如下：
        {
            "thought": "你的思考过程，分析当前屏幕状态和下一步该做什么",
            "action": "动作类型",
            "parameters": {
                "参数 1": "值 1",
                "参数 2": "值 2"
            }
        }

        可用的动作类型：
        - click: 点击，参数：x, y (0-1000 的归一化坐标)
        - double_click: 双击，参数：x, y
        - right_click: 右键点击，参数：x, y
        - type: 输入文本，参数：text (要输入的文本)
        - press: 按键，参数：keys (按键数组，如 ["ctrl", "c"])
        - scroll: 滚动，参数：amount (滚动量), x, y (可选，滚动位置)
        - drag: 拖拽，参数：start_x, start_y, end_x, end_y, duration (可选)
        - move: 移动鼠标，参数：x, y, duration (可选)
        - wait: 等待，参数：seconds
        - task_complete: 任务完成，参数：result (任务结果描述)

        注意：
        1. 坐标系统使用 1000x1000 的归一化坐标，(0,0) 是左上角，(1000,1000) 是右下角
        2. 每次只执行一个动作
        3. 仔细观察屏幕内容，做出合理的决策
        4. 如果任务完成，使用 task_complete 动作
        5. 如果遇到困难，尝试不同的方法
        6. VSCode 打开控制台的快捷键是 ctrl+shfit+`
        7. window 电脑用 Set-Content -Encoding utf8 文件名 "内容" 来写文件
        8. 如果遇到输入英文却打出中文的情况请切换输入法
        9. 请使用工具上手操作
        """

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 设置 BaseAgent 需要的属性
        self.api_provider = self.config["api"]["base_url"]
        self.model_name = self.config["api"]["model"]
        self.api_key = self.config["api"]["api_key"]
        self.model = self.model_name  # 兼容 run 方法中的 self.model

        # Agent 配置
        self.max_iterations = self.config.get("agent", {}).get("max_iterations", 50)
        self.max_tokens = self.config["api"].get("max_tokens", 2048)
        self.temperature = self.config["api"].get("temperature", 0.7)
        self.delay = self.config.get("agent", {}).get("delay_between_actions", 1.0)

        self.screen_width, self.screen_height = pyautogui.size()
        print(f"Screen resolution: {self.screen_width}x{self.screen_height}")

        self.conversation_history: List[Dict[str, Any]] = []

        # 在 super().__init__() 之前注册工具，这样 BaseAgent 可以看到它们
        self._register_tools()

        super().__init__()

    def _register_tools(self):
        """注册工具函数"""
        # 注册 wait 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="等待指定的秒数",
            name="wait",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "等待的秒数"}
                },
                "required": ["seconds"]
            }
        )
        def wait_tool(seconds: float) -> str:
            time.sleep(seconds)
            return f"Waited for {seconds} seconds"

        # 注册 scroll 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="滚动鼠标滚轮",
            name="scroll",
            parameters={
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "滚动量，正数向上滚动，负数向下滚动"},
                    "x": {"type": "number", "description": "x 坐标 (可选)"},
                    "y": {"type": "number", "description": "y 坐标 (可选)"}
                },
                "required": ["amount"]
            }
        )
        def scroll_tool(amount: float, x: float = None, y: float = None) -> str:
            if x is not None and y is not None:
                real_x, real_y = self.map_coordinates(x, y)
                pyautogui.scroll(int(amount), x=real_x, y=real_y)
            else:
                pyautogui.scroll(int(amount))
            return f"Scrolled: {amount}"

        # 注册 move 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="移动鼠标到指定位置",
            name="move",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "x 坐标 (0-1000 的归一化坐标)"},
                    "y": {"type": "number", "description": "y 坐标 (0-1000 的归一化坐标)"},
                    "duration": {"type": "number", "description": "移动持续时间 (秒)"}
                },
                "required": ["x", "y"]
            }
        )
        def move_tool(x: float, y: float, duration: float = 0.5) -> str:
            real_x, real_y = self.map_coordinates(x, y)
            pyautogui.moveTo(real_x, real_y, duration=duration)
            return f"Moved to ({real_x}, {real_y})"

        # 注册 drag 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="拖拽鼠标",
            name="drag",
            parameters={
                "type": "object",
                "properties": {
                    "start_x": {"type": "number", "description": "起始 x 坐标"},
                    "start_y": {"type": "number", "description": "起始 y 坐标"},
                    "end_x": {"type": "number", "description": "结束 x 坐标"},
                    "end_y": {"type": "number", "description": "结束 y 坐标"},
                    "duration": {"type": "number", "description": "拖拽持续时间 (秒)"}
                },
                "required": ["start_x", "start_y", "end_x", "end_y"]
            }
        )
        def drag_tool(start_x: float, start_y: float, end_x: float, end_y: float, duration: float = 1.0) -> str:
            start_real_x, start_real_y = self.map_coordinates(start_x, start_y)
            end_real_x, end_real_y = self.map_coordinates(end_x, end_y)
            pyautogui.moveTo(start_real_x, start_real_y)
            pyautogui.drag(end_real_x - start_real_x, end_real_y - start_real_y, duration=duration)
            return f"Dragged from ({start_real_x}, {start_real_y}) to ({end_real_x}, {end_real_y})"

        # 注册 click 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="点击鼠标左键",
            name="click",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "x 坐标 (0-1000 的归一化坐标)"},
                    "y": {"type": "number", "description": "y 坐标 (0-1000 的归一化坐标)"}
                },
                "required": ["x", "y"]
            }
        )
        def click_tool(x: float, y: float) -> str:
            real_x, real_y = self.map_coordinates(x, y)
            pyautogui.click(real_x, real_y)
            return f"Clicked at ({real_x}, {real_y})"

        # 注册 double_click 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="双击鼠标左键",
            name="double_click",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "x 坐标 (0-1000 的归一化坐标)"},
                    "y": {"type": "number", "description": "y 坐标 (0-1000 的归一化坐标)"}
                },
                "required": ["x", "y"]
            }
        )
        def double_click_tool(x: float, y: float) -> str:
            real_x, real_y = self.map_coordinates(x, y)
            pyautogui.doubleClick(real_x, real_y)
            return f"Double clicked at ({real_x}, {real_y})"

        # 注册 right_click 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="点击鼠标右键",
            name="right_click",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "x 坐标 (0-1000 的归一化坐标)"},
                    "y": {"type": "number", "description": "y 坐标 (0-1000 的归一化坐标)"}
                },
                "required": ["x", "y"]
            }
        )
        def right_click_tool(x: float, y: float) -> str:
            real_x, real_y = self.map_coordinates(x, y)
            pyautogui.rightClick(real_x, real_y)
            return f"Right clicked at ({real_x}, {real_y})"

        # 注册 type 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="输入文本",
            name="type",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要输入的文本"}
                },
                "required": ["text"]
            }
        )
        def type_tool(text: str) -> str:
            pyautogui.typewrite(text, interval=0.1)
            return f"Typed: {text}"

        # 注册 press 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="按下键盘按键",
            name="press",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {"type": "array", "items": {"type": "string"}, "description": "按键数组，如 ['ctrl', 'c']"}
                },
                "required": ["keys"]
            }
        )
        def press_tool(keys: list) -> str:
            pyautogui.hotkey(*keys)
            return f"Pressed: {'+'.join(keys)}"

        # 注册 task_complete 工具
        @Dumplings.tool_registry.register_tool(
            allowed_agents=["screen_agent"],
            description="标记任务完成并退出",
            name="task_complete",
            parameters={
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "任务结果描述"}
                },
                "required": []
            }
        )
        def task_complete_tool(result: str = "") -> str:
            print(f"\n{'=' * 60}")
            print("Task completed!")
            print(f"{'=' * 60}")
            sys.exit(0)

    def capture_screen(self) -> str:
        """截取屏幕并返回 base64 编码的图片"""
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)
            img_data = mss.tools.to_png(screenshot.rgb, screenshot.size)
            return base64.b64encode(img_data).decode("utf-8")

    def map_coordinates(self, x: float, y: float) -> tuple[int, int]:
        """将模型返回的 1000x1000 坐标映射到实际屏幕分辨率"""
        real_x = int(x / 1000 * self.screen_width)
        real_y = int(y / 1000 * self.screen_height)
        return real_x, real_y

    def execute_action(self, action: Action) -> str:
        """执行 AI 返回的动作"""
        action_type = action.action_type.lower()
        params = action.parameters

        try:
            if action_type == "click":
                x, y = self.map_coordinates(params.get("x", 500), params.get("y", 500))
                pyautogui.click(x, y)
                return f"Clicked at ({x}, {y})"

            elif action_type == "double_click":
                x, y = self.map_coordinates(params.get("x", 500), params.get("y", 500))
                pyautogui.doubleClick(x, y)
                return f"Double clicked at ({x}, {y})"

            elif action_type == "right_click":
                x, y = self.map_coordinates(params.get("x", 500), params.get("y", 500))
                pyautogui.rightClick(x, y)
                return f"Right clicked at ({x}, {y})"

            elif action_type == "type":
                text = params.get("text", "")
                interval = 0.1
                pyautogui.typewrite(text, interval=interval)
                return f"Typed: {text}"

            elif action_type == "press":
                keys = params.get("keys", [])
                if isinstance(keys, str):
                    keys = [keys]
                pyautogui.hotkey(*keys)
                return f"Pressed: {'+'.join(keys)}"

            elif action_type == "scroll":
                amount = params.get("amount", 100)
                x = params.get("x")
                y = params.get("y")
                if x is not None and y is not None:
                    x, y = self.map_coordinates(x, y)
                    pyautogui.scroll(amount, x=x, y=y)
                else:
                    pyautogui.scroll(amount)
                return f"Scrolled: {amount}"

            elif action_type == "drag":
                start_x, start_y = self.map_coordinates(params.get("start_x", 500), params.get("start_y", 500))
                end_x, end_y = self.map_coordinates(params.get("end_x", 500), params.get("end_y", 500))
                duration = params.get("duration", 1.0)
                pyautogui.moveTo(start_x, start_y)
                pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)
                return f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"

            elif action_type == "move":
                x, y = self.map_coordinates(params.get("x", 500), params.get("y", 500))
                duration = params.get("duration", 0.5)
                pyautogui.moveTo(x, y, duration=duration)
                return f"Moved to ({x}, {y})"

            elif action_type == "wait":
                seconds = params.get("seconds", 1.0)
                time.sleep(seconds)
                return f"Waited for {seconds} seconds"

            elif action_type == "task_complete":
                return "Task completed successfully"

            else:
                return f"Unknown action type: {action_type}"

        except Exception as e:
            return f"Error executing action: {str(e)}"

    def parse_action(self, response_text: str) -> Optional[Action]:
        """解析 AI 返回的动作"""
        try:
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                action_json = json.loads(json_match.group())
                return Action(
                    action_type=action_json.get("action", "wait"),
                    parameters=action_json.get("parameters", {}),
                    thought=action_json.get("thought", "")
                )
        except Exception as e:
            print(f"Error parsing action: {e}")
        return None

    def run(self, task: str) -> str:
        """运行 Agent 完成用户任务"""
        system_prompt = """你是一个电脑操作助手。你的任务是根据用户的指令，通过一系列操作来完成用户的任务。

每次响应必须返回一个 JSON 对象，格式如下：
{
    "thought": "你的思考过程，分析当前屏幕状态和下一步该做什么",
    "action": "动作类型",
    "parameters": {
        "参数 1": "值 1",
        "参数 2": "值 2"
    }
}

可用的动作类型：
- click: 点击，参数：x, y (0-1000 的归一化坐标)
- double_click: 双击，参数：x, y
- right_click: 右键点击，参数：x, y
- type: 输入文本，参数：text (要输入的文本)
- press: 按键，参数：keys (按键数组，如 ["ctrl", "c"])
- scroll: 滚动，参数：amount (滚动量), x, y (可选，滚动位置)
- drag: 拖拽，参数：start_x, start_y, end_x, end_y, duration (可选)
- move: 移动鼠标，参数：x, y, duration (可选)
- wait: 等待，参数：seconds
- task_complete: 任务完成，参数：result (任务结果描述)

注意：
1. 坐标系统使用 1000x1000 的归一化坐标，(0,0) 是左上角，(1000,1000) 是右下角
2. 每次只执行一个动作
3. 仔细观察屏幕内容，做出合理的决策
4. 如果任务完成，使用 task_complete 动作
5. 如果遇到困难，尝试不同的方法
6. VSCode 打开控制台的快捷键是 ctrl+shfit+`
7. window 电脑用 Set-Content -Encoding utf8 文件名 "内容" 来写文件
8. 如果遇到输入英文却打出中文的情况请切换输入法
9. 请尽量使用edge而不是Google Chrome
"""

        self.conversation_history = [
            {"role": "system", "content": system_prompt}
        ]

        print(f"\n{'=' * 60}")
        print(f"Starting task: {task}")
        print(f"{'=' * 60}\n")

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration}/{self.max_iterations} ---")

            screenshot_base64 = self.capture_screen()
            print("Captured screenshot")

            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"当前任务：{task}\n请分析屏幕并决定下一步操作。"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    }
                ]
            }

            messages = self.conversation_history + [user_message]

            print("Sending to AI...")

            # 使用 conversation_with_tool 发送请求
            # 构建完整的消息历史
            self.history = messages.copy()

            # 使用 BaseAgent 的 conversation_with_tool 方法
            ai_response = self.conversation_with_tool(
                messages=f"当前任务：{task}\n请分析屏幕并决定下一步操作，务必使用工具上手操作",
                images=[screenshot_base64]
            )
            print(f"AI response:\n{ai_response}\n")

            self.conversation_history.append(user_message)
            self.conversation_history.append({
                "role": "assistant",
                "content": ai_response
            })

            action = self.parse_action(ai_response)
            if action is None:
                print("Failed to parse action, retrying...")
                continue

            print(f"Thought: {action.thought}")
            print(f"Executing action: {action.action_type}")

            result = self.execute_action(action)
            print(f"Result: {result}")

            if action.action_type.lower() == "task_complete":
                print(f"\n{'=' * 60}")
                print("Task completed!")
                print(f"{'=' * 60}")
                return result

            time.sleep(self.delay)

        print("\nMax iterations reached without completing the task")
        return "Task incomplete - max iterations reached"


def main():
    agent = Dumplings.agent_list["screen_agent"]

    task = input("Enter your task: ")
    result = agent.run(task)
    print(f"\nFinal result: {result}")


if __name__ == "__main__":
    main()