# Agent Service Toolkit 更新与启动操作

本文档记录在 Windows 本地更新并启动 `agent-service-toolkit` 的操作流程。当前项目包含两个主要服务：

- FastAPI 后端服务：`src/run_service.py`，默认地址 `http://localhost:8080`
- Streamlit 前端应用：`src/streamlit_app.py`，默认地址 `http://localhost:8501`

## 适用场景

- 项目目录：`D:\github\agenttoolkit`
- 依赖管理：`uv` 或 `pip`（Conda 虚拟环境）
- Python 版本：`>=3.11,<3.14` (当前环境为 Python 3.12.11)
- Python 环境路径：`D:\software\anaconda\envs\py312\python.exe`
- 默认后端端口：`8080`
- 默认前端端口：`8501`
- 当前本地模型配置：`deepseek-chat`
- 当前默认 agent：`research-assistant`

## 前置要求

### 1. 安装 uv

如果本机还没有 `uv`，先安装：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

检查是否可用：

```powershell
uv --version
```

### 2. 配置环境变量

项目根目录需要 `.env` 文件。可从示例文件复制：

```powershell
cd D:\github\agenttoolkit
Copy-Item .env.example .env
```

至少需要配置一个 LLM 提供商，例如当前项目使用 DeepSeek：

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key
DEFAULT_MODEL=deepseek-chat
```

数据库可以选择 Postgres 或 SQLite：

```dotenv
# 使用外部 Postgres
DATABASE_TYPE=postgres
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_HOST=...
POSTGRES_PORT=5432
POSTGRES_DB=...

# 或者本地临时启动时使用 SQLite
DATABASE_TYPE=sqlite
SQLITE_DB_PATH=checkpoints.db
```

如果设置了 `AUTH_SECRET`，调用 `/info`、`/invoke`、`/stream` 等接口时需要加 Bearer token。`/health` 不需要认证。

## 更新项目代码

在项目根目录执行：

```powershell
cd D:\github\agenttoolkit
git pull --ff-only
```

如果 `pyproject.toml` 或 `uv.lock` 有变化，重新同步依赖：

```powershell
uv sync --frozen
```

首次启动前也需要执行一次：

```powershell
uv sync --frozen
```

## 启动后端服务

### 使用 `.env` 配置启动

```powershell
cd D:\github\agenttoolkit
.\.venv\Scripts\python.exe src\run_service.py
```

启动成功后会监听：

```text
http://localhost:8080
```

### 本地临时使用 SQLite 启动

如果 `.env` 配置了外部 Postgres，但数据库网络不可达，可以临时用 SQLite 启动后端验证服务。该方式只影响当前 PowerShell 会话，不修改 `.env`：

```powershell
cd D:\github\agenttoolkit
$env:DATABASE_TYPE = "sqlite"
$env:SQLITE_DB_PATH = ".codex-run\checkpoints.db"
.\.venv\Scripts\python.exe src\run_service.py
```

## 验证后端

健康检查：

```powershell
Invoke-RestMethod http://localhost:8080/health
```

预期输出：

```json
{"status":"ok"}
```

查看服务元信息：

```powershell
Invoke-RestMethod http://localhost:8080/info | ConvertTo-Json -Depth 6
```

当前验证到的关键信息：

```text
default_agent: research-assistant
default_model: deepseek-chat
models: deepseek-chat
```

## 启动前端应用

保持后端运行，在另一个 PowerShell 窗口执行：

```powershell
cd D:\github\agenttoolkit
$env:AGENT_URL = "http://localhost:8080"
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py --server.port 8501 --server.address localhost
```

如果是首次运行 Streamlit，建议关闭统计提示，避免后台启动时卡在交互输入：

```powershell
cd D:\github\agenttoolkit
$env:AGENT_URL = "http://localhost:8080"
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$env:STREAMLIT_SERVER_HEADLESS = "true"
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py --server.port 8501 --server.address localhost --server.headless true --browser.gatherUsageStats false
```

打开前端：

```text
http://localhost:8501
```

验证前端健康检查：

```powershell
Invoke-WebRequest http://localhost:8501/healthz -UseBasicParsing
```

预期状态码为 `200`，内容为 `ok`。

## Docker 启动方式

如果本机安装了 Docker，可以使用项目自带的 `compose.yaml`：

```powershell
cd D:\github\agenttoolkit
docker compose watch
```

该方式会启动：

- `agent_service`：映射到 `8080`
- `streamlit_app`：映射到 `8501`

停止服务：

```powershell
docker compose down
```

注意：当前机器未检测到 `docker` 命令时，应使用上面的本地 Python 启动方式。

## 后台启动示例

如需在当前机器后台启动，可将日志写入 `.codex-run`：

```powershell
cd D:\github\agenttoolkit
New-Item -ItemType Directory -Force .codex-run | Out-Null

$env:DATABASE_TYPE = "sqlite"
$env:SQLITE_DB_PATH = ".codex-run\checkpoints.db"
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "src/run_service.py" `
  -WorkingDirectory "D:\github\agenttoolkit" `
  -RedirectStandardOutput ".codex-run\service.out.log" `
  -RedirectStandardError ".codex-run\service.err.log" `
  -WindowStyle Hidden

$env:AGENT_URL = "http://localhost:8080"
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"
$env:STREAMLIT_SERVER_HEADLESS = "true"
Start-Process -FilePath ".\.venv\Scripts\streamlit.exe" `
  -ArgumentList "run src/streamlit_app.py --server.port 8501 --server.address localhost --server.headless true --browser.gatherUsageStats false" `
  -WorkingDirectory "D:\github\agenttoolkit" `
  -RedirectStandardOutput ".codex-run\streamlit.out.log" `
  -RedirectStandardError ".codex-run\streamlit.err.log" `
  -WindowStyle Hidden
```

查看日志：

```powershell
Get-Content -Tail 100 .codex-run\service.err.log
Get-Content -Tail 100 .codex-run\streamlit.out.log
```

## 常见问题

### 1. 后端进程存在但 8080 无法访问

如果 `.env` 中 `DATABASE_TYPE=postgres`，启动阶段会连接外部 Postgres。数据库网络不通或端口不可达时，服务可能卡在应用启动阶段，导致 8080 暂时没有监听。

检查端口：

```powershell
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue
```

临时验证可改用 SQLite 启动：

```powershell
$env:DATABASE_TYPE = "sqlite"
$env:SQLITE_DB_PATH = ".codex-run\checkpoints.db"
.\.venv\Scripts\python.exe src\run_service.py
```

### 2. Streamlit 启动时要求输入邮箱

首次运行 Streamlit 可能出现统计邮件提示。使用以下参数关闭：

```powershell
--server.headless true --browser.gatherUsageStats false
```

### 3. 端口被占用

查看端口占用：

```powershell
Get-NetTCPConnection -LocalPort 8080,8501 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess
```

结束对应进程：

```powershell
Stop-Process -Id <PID> -Force
```

### 4. 需要认证

如果 `.env` 中配置了：

```dotenv
AUTH_SECRET=your_secret
```

调用受保护接口时需要：

```powershell
Invoke-RestMethod http://localhost:8080/info -Headers @{
  Authorization = "Bearer your_secret"
}
```

## 本次本机验证记录

- 已配置并使用 Anaconda Python 环境：`D:\software\anaconda\envs\py312\python.exe`
- 依赖管理：在 `D:\software\anaconda\envs\py312\` 环境中通过 `pip` 安装项目所需的库
- 本机未检测到 `docker` 命令
- 使用临时 `DATABASE_TYPE=sqlite` 成功启动后端
- `http://localhost:8080/health` 返回 `{"status":"ok"}`
- `http://localhost:8080/info` 返回默认 agent `research-assistant`，默认模型 `deepseek-chat`
- 使用 `AGENT_URL=http://localhost:8080` 成功启动 Streamlit
- `http://localhost:8501/healthz` 返回 `ok`
