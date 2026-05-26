# tools.py
import docker
from langchain_core.tools import tool
import os

from dotenv import load_dotenv
load_dotenv()

client = docker.from_env()
CONTAINER_NAME = os.environ["CONTAINER_NAME"]

@tool
def execute_bash_in_container(command: str) -> str:
    """
    在 Docker 容器內的 /workspace 目錄下執行任意 BASH 指令。
    支援所有標準 Linux 指令、檔案操作、Git 操作與測試執行。
    """
    try:
        container = client.containers.get(CONTAINER_NAME)
        wrapped_command = f"cd /workspace && {command}"
        
        result = container.exec_run(
            cmd=["bash", "-c", wrapped_command],
            environment={"LANG": "C.UTF-8"}
        )
        
        output = result.output.decode('utf-8', errors='ignore')
        return f"[Exit Code: {result.exit_code}]\n[Output]:\n{output}"
        
    except docker.errors.NotFound:
        return f"錯誤：找不到名為 {CONTAINER_NAME} 的 Docker 容器，請確保它已啟動。"
    except Exception as e:
        return f"執行指令時發生未預期錯誤: {str(e)}"

tools = [execute_bash_in_container]