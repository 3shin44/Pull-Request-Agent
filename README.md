# Pull Request Agent

## 說明

Pull Request觸發CI, CI執行失敗後, 呼叫Agent嘗試修復錯誤, 若成功則推送修正版到對應分支

## 材料方法

### 啟動方式

### 沙盒容器

Dockerfile注意最終賦予容器名稱, 需與.env檔案內設定一致

```
# 1. 建立本地對應的資料夾（對應 tools.py 的 /workspace）
mkdir -p sandbox_workspace

# 2. 建立並編譯沙盒 Image
docker build -t ai-sandbox-image .

# 3. 啟動容器，帶入 .env 設定並掛載目錄 (${pwd}是當前的絕對路徑, 掛載用)
docker run -d \
  --name ai-sandbox \
  --env-file .env \
  -v $(pwd)/sandbox_workspace:/workspace \
  ai-sandbox-image
```

### 主服務啟動

1. `python -m venv venv`
2. (依據OS) `.\venv\Scripts\Activate.ps1`
3. `python /src/server.py`

POST EXAMPLE

```
{
  "error_report": "Python專案執行UNIT TEST失敗, 檢查並嘗試修復, 檔案掛載於'/workspace'"
}
```

### 流程

1. 目標Git Repository手動觸發CI Error
2. 手動觸發本服務執行自動修復
3. 觀察AI Model運作過程

### 測試情境

| TestCase | Senario                    | Expect           |
| -------- | -------------------------- | ---------------- |
| TC01     | UT失敗                     | 修正UT           |
| TC02     | 過時的套件與語法           | 更新套件與語法   |
| TC03     | 共用方法更新後導致引用錯誤 | 更新使用共用方法 |

## 檔案說明

```
│  README.md            // 說明文件
│  Dockerfile           // 建立Sandbox容器
│  .env                 // 設定檔
│  .env_example
│  requirements.txt     // 依賴庫
└─src
   │  agents.py         // AGENT & LangGraph設定
   │  tools.py          // 授權TOOL
   └─ server.py         // WEB 接口與轉發給AGENT
```

## 結果與討論

使用模型: qwen2.5-coder:7b

| TestCase | Senario                    | Expect           | Result               |
| -------- | -------------------------- | ---------------- | -------------------- |
| TC01     | UT失敗                     | 修正UT           | 失敗, 去改錯誤條件   |
| TC02     | 過時的套件與語法           | 更新套件與語法   | 成功, 更新為新版語法 |
| TC03     | 共用方法更新後導致引用錯誤 | 更新使用共用方法 | 失敗, 無法辨別       |

LangSmith紀錄檔案參考: Notes/thread-ci_fail_event_001.md
