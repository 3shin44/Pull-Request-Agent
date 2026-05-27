# server.py
import os
import uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI, BackgroundTasks
from langchain_core.messages import HumanMessage

from dotenv import load_dotenv
load_dotenv()

# 1. 監控啟動（在匯入 LangChain 前設定）
# LangSmith參數已設定在.env

# 2. 僅匯入 agent_app 與其設定好的限制常數
from agents import agent_app, MAX_RECURSION

app = FastAPI(title="CI Event Webhook Receiver")

def run_background_repair(event_description: str):
    """純粹的轉發邏輯，放手讓 Agent 執行完畢"""
    print(f"📡 [接收外部 CI 事件] 開始投遞任務...")
    
    # 將外部傳進來的事件文字（例如："專案 A 的 pytest 失敗了，請修復"）包裝成 HumanMessage
    inputs = {"messages": [HumanMessage(content=event_description)]}
    
    try:
        # 使用從 agents.py 帶過來的安全遞迴上限 MAX_RECURSION
        final_state = agent_app.invoke(
            inputs, 
            config={
                "configurable": {"thread_id": "ci_fail_event_001"},
                "recursion_limit": MAX_RECURSION
            }
        )
        print("✅ [Agent 任務結束] 最後輸出報告：")
        print(final_state["messages"][-1].content)
        
    except Exception as e:
        print(f"❌ [Agent 終止] 任務未完成，可能已達到最大嘗試次數。錯誤原因: {str(e)}")

@app.post("/api/v1/ci-trigger")
async def handle_ci_event(payload: dict, background_tasks: BackgroundTasks):
    """
    外部 Webhook 入口
    Payload 範例: {"error_report": "Pull Request #123 執行CI失敗, 讀取LOG並嘗試修復"}
    """
    error_report = payload.get("error_report", "")
    if not error_report:
        return {"status": "error", "message": "Missing 'error_report'"}
    
    # 異步非同步處理，不卡住 CI/CD 流程
    background_tasks.add_task(run_background_repair, error_report)
    
    return {"status": "accepted", "message": "Agent has taken over the task."}

@app.get("/api/v1/health")
async def health_check():
    """
    健康檢查接口，用於檢測服務是否存活
    """
    return {
        "status": "healthy",
        "message": "CI Trigger service is running up and good.",
        "timestamp": datetime.now().astimezone().isoformat()
    }

if __name__ == "__main__":
    # 將 uvicorn 的執行目錄指向 src
    uvicorn.run(
        "server:app",  
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        app_dir="src"       #  uvicorn 去哪裡找 server.py
    )