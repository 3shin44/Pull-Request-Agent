# agents.py
from typing import Annotated, TypedDict, Sequence
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.prebuilt import ToolNode, tools_condition
from tools import tools
import os

from dotenv import load_dotenv
load_dotenv()

# 1. 核心參數：限制 Agent 最大圖形迴圈次數
# 1次循環包含：Agent思考(Node 1) + Tool執行(Node 2)。嘗試5次約需 11~15 次節點轉換。
MAX_RECURSION = int(os.environ["MAX_RECURSION"])

# 2. 情境專屬的 System Prompt
CI_REPAIR_SYSTEM_PROMPT = SystemMessage(content=(
    "# 目標\n"
    "Git Repository 在執行CI後失敗, 依據失敗的Pull Request執行CI結果進行修復\n\n"
    
    "# 操作工具與權限\n"
    "1. 完整 BASH 權限，可以執行任何 Linux 指令。\n"
    "2. 遵循以下步驟：\n"
    "   - 尋找並閱讀測試失敗的 LOG 檔案（例如使用 `cat`, `grep`, `less`）。\n"
    "   - 檢視相關的原始碼與測試檔案。\n"
    "   - 使用 BASH 工具直接修改程式碼（例如使用 `sed`、利用 `cat << 'EOF'` 重寫檔案）。\n"
    "   - 修改後，在容器內重新運行單元測試指令（如 `pytest`, `npm test` 等），驗證是否修復成功。\n\n"
))

# 3. 定義狀態
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

# 4. 初始化模型並綁定工具
llm = ChatOllama(
    model=os.environ["MODEL_NAME"],
    base_url=os.environ["MODEL_HOST"],
    temperature=int(os.environ["MODEL_TEMERATURE"])
).bind_tools(tools)

# 5. 定義圖節點：動態注入 System Prompt
def call_model(state: AgentState):
    current_messages = state['messages']
    
    # 確保 System Prompt 永遠處於對話歷史的最開頭
    if not any(isinstance(m, SystemMessage) for m in current_messages):
        full_messages = [CI_REPAIR_SYSTEM_PROMPT] + list(current_messages)
    else:
        full_messages = current_messages
        
    response = llm.invoke(full_messages)
    return {"messages": [response]}

# 6. 建立與編譯 LangGraph
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

# 匯出編譯好的 App 物件
agent_app = workflow.compile()