# agents.py
from typing import Annotated, TypedDict, Sequence
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage, AIMessage
from langgraph.prebuilt import ToolNode
from tools import tools
import os
import json

from dotenv import load_dotenv
load_dotenv()

# 1. 核心參數
MAX_RECURSION = int(os.environ["MAX_RECURSION"])
# 滑動視窗大小：保留最近 N 條訊息（不含 SystemMessage）以避免超出 context window
# 1 個工具循環 = AIMessage + ToolMessage = 2 條；預設 4 條 = 最近 2 次循環
MAX_HISTORY_MESSAGES = int(os.environ.get("MAX_HISTORY_MESSAGES", "4"))

# 2. 情境專屬的 System Prompt
CI_REPAIR_SYSTEM_PROMPT = SystemMessage(content=(
    "You are an automated CI Repair Agent operating in a Linux container (/workspace).\n"
    "CRITICAL: Never chat. Never ask humans for help. You must ONLY respond with a single raw JSON tool call.\n\n"

    "# AVAILABLE TOOL\n"
    "You have exactly ONE tool. To call it, output ONLY a raw JSON object — no markdown fences, no explanation, nothing else:\n"
    '{"name": "execute_bash_in_container", "arguments": {"command": "<bash command>"}}\n\n'

    "# OBJECTIVE\n"
    "Fix the failing Python unit tests. The task is successful ONLY when the test command returns Exit Code 0.\n\n"

    "# RULES & CONSTRAINTS\n"
    "1. Your very first action MUST be executing the test command to see the error log.\n"
    "2. Max retry limit: 5 loops of (Fix -> Test).\n"
    "3. When tests pass (Exit Code 0), stop calling tools and output a short summary of your fix.\n\n"

    "# COMMANDS TO USE\n"
    "- Run Tests: `python -m unittest discover -s tests`\n"
    "- View Files: `cat <filename>`\n"
    "- Edit Files: Use `cat << 'EOF' > filename` to rewrite or use `sed`."
))

# 3. 定義狀態
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# 4. 初始化模型（不透過 API 傳送 tools 參數以相容未啟用 --enable-auto-tool-choice 的 vLLM）
# 工具 schema 已寫入 System Prompt；my_router 負責解析 JSON 文字工具呼叫
llm = ChatOpenAI(
    model=os.environ["MODEL_NAME"],
    base_url=os.environ["MODEL_HOST"],
    temperature=float(os.environ["MODEL_TEMPERATURE"]),
    openai_api_key="dummy"
)

# 5. 定義圖節點：動態注入 System Prompt + 滑動視窗截斷
def call_model(state: AgentState):
    current_messages = state['messages']

    # 移除重複的 SystemMessage，確保唯一且在最前端
    cleaned_messages = [m for m in current_messages if not isinstance(m, SystemMessage)]

    # 滑動視窗：保留第一條（原始任務）+ 最近 MAX_HISTORY_MESSAGES-1 條
    # 避免小模型超出 context window（Qwen2.5-3B 上限 2048 tokens）
    if len(cleaned_messages) > MAX_HISTORY_MESSAGES:
        task_message = cleaned_messages[:1]
        recent_messages = cleaned_messages[-(MAX_HISTORY_MESSAGES - 1):]
        cleaned_messages = task_message + recent_messages

    full_messages = [CI_REPAIR_SYSTEM_PROMPT] + cleaned_messages

    response = llm.invoke(full_messages)
    return {"messages": [response]}

# 2. 💡 關鍵：自訂自調路由邏輯，精準捕捉 Ollama 的工具呼叫
def my_router(state: AgentState):
    last_message = state['messages'][-1]
    
    # 情況 A：標準 LangChain tool_calls 有抓到
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        print(f"🔗 [Router] 偵測到標準工具呼叫: {last_message.tool_calls[0]['name']}")
        return "tools"
    
    # 情況 B：攔截 JSON 文字
    if isinstance(last_message, AIMessage) and last_message.content:
        content_str = last_message.content.strip()
        
        try:
            # 移除 Markdown 程式碼區塊標記
            if content_str.startswith("```"):
                content_str = content_str.split("\n", 1)[-1].rsplit("\n", 1)[0].strip()
                if content_str.startswith("json"):
                    content_str = content_str[4:].strip()

            tool_data = json.loads(content_str)
            
            if isinstance(tool_data, dict) and "name" in tool_data:
                # 💡 優化 2：提取 AI 的實際指令字串
                # 兼容 "arguments" 與 "args"，並精準抓取內部的 "command"
                raw_args = tool_data.get("arguments", tool_data.get("args", {}))
                actual_command = raw_args.get("command") if isinstance(raw_args, dict) else raw_args
                
                if not actual_command:
                    # 有些極端情況 AI 的 JSON 格式為 {"name": "...", "command": "..."}
                    actual_command = tool_data.get("command")

                print(f"🎯 [Router] 成功攔截工具 [{tool_data['name']}]，執行指令: {actual_command}")
                
                # 💡 優化 3：【關鍵】將結構完全重組為官方認可的 "args" 欄位！
                # 這樣 ToolNode 才能真正抓到 `command` 參數並傳給 tools.py 執行
                last_message.tool_calls = [{
                    "name": tool_data["name"],
                    "args": {"command": actual_command},  # 👈 強制校正為標準 args 格式
                    "id": f"call_{len(state['messages'])}", # 動態產生 ID，避免框架判定重複
                    "type": "tool_call"
                }]
                return "tools"
                
        except json.JSONDecodeError:
            pass

    print("🏁 [Router] AI 確定未呼交工具，流程結束。")
    return "__end__"

# 3. 重新組裝 LangGraph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")

# 👈 關鍵修改：使用我們自己寫的 my_router 代替 tools_condition
workflow.add_conditional_edges(
    "agent",
    my_router,
    {
        "tools": "tools",
        "__end__": END
    }
)
workflow.add_edge("tools", "agent")

# 匯出編譯好的 App 物件
agent_app = workflow.compile()