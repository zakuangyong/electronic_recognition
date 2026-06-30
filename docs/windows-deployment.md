# Windows 本地部署（含向量库 / 图纸检索）

本指南面向在 Windows 本地**单机**真正运行图纸识别 + 检索（嵌入式 Qdrant 形态，无需外部服务）。

## 形态说明
- 单进程 FastAPI（`er`）+ 进程内嵌入式 Qdrant（向量库写在 `data/search/qdrant`）+ SQLite FTS5（`data/search/drawings.db`）。
- **嵌入式 Qdrant 同一时刻只允许一个进程访问**该目录。因此：
  - 启动服务**不要加多 worker**（默认单进程即可）。
  - 服务运行期间需要重建索引时，**走 HTTP API**（`--via-api`），不要再开一个直连进程，否则会抢锁失败。

## 一、安装与配置
```powershell
cd D:\project\electronic_recognition
conda env create -f environment.yml
conda activate electronic
Copy-Item .env.example .env
# 编辑 .env：填入大模型 ER_LLM_* 与检索相关项
```

## 二、（离线必做）预取嵌入模型
首次需联网一次，把嵌入模型下载到本地目录，之后即可断网运行：
```powershell
python scripts/prefetch_models.py
# 完成后在 .env 设置脚本提示的路径，例如：
# ER_SEARCH_EMBEDDING_MODEL_PATH=data/models/bge-small-zh-v1.5
```
设置 `ER_SEARCH_EMBEDDING_MODEL_PATH` 后，运行时以 `local_files_only` 加载，不再访问网络。
迁移到内网机时，连同 `data/models/` 一起拷贝即可。

## 三、启动服务（单进程）
```powershell
er                 # 默认 127.0.0.1:8892
er --port 8899     # 指定端口
```
启动后会在后台**预热检索栈**（加载嵌入模型、打开向量库）。预热未完成或失败时，
`/api/search/health` 会返回 `degraded=true` 并带 `warmup_error` 原因，前端检索页自动显示降级状态。

## 四、自检
```powershell
curl http://127.0.0.1:8892/api/search/health
```
正常应为 `enabled=true`、`degraded=false`、`vector_points>0`（已有索引时）。

## 五、重建索引
- **服务运行中**（推荐，复用进程内向量库，不抢锁）：
  ```powershell
  python -m electronic_recognition.search.rebuild --via-api --force
  ```
- **服务已停止**（离线批量直连）：
  ```powershell
  python -m electronic_recognition.search.rebuild --force
  ```
  若直连时报“无法打开本地向量库 / already accessed / .lock”，说明服务还在运行，改用 `--via-api`。

## 六、修复历史中文文件名乱码（一次性）
旧数据中若存在 `A17387_..._??????_05.pdf` 这类 GBK 乱码文件名：
```powershell
python scripts/fix_filename_encoding.py --dry-run   # 先预览
python scripts/fix_filename_encoding.py             # 实际修正 result.json/manifest.json
# 然后按脚本提示重建索引（服务运行中用 --via-api，否则直连）
```
新上传的文件名已在上传入口自动按 UTF-8 纠正，无需再处理。

## 七、残留锁处理
若进程异常退出后再次启动报 Qdrant 被占用：
1. 确认**没有**其他 `er` / python 进程在跑（任务管理器）。
2. 确认无误后，删除 `data/search/qdrant/.lock`，重新启动。
   （`.lock` 是活跃进程的独占标记，仅在确认无其他进程时才可删除。）

## 故障：页面提示 “sentence-transformers 未安装 / 降级运行 / 模式 standard”
说明**启动服务的那个 Python 环境**没有装向量检索依赖（`sentence-transformers` + `torch`），
后端因此关闭向量检索、降级成 BM25。注意：**建索引的环境和起服务的环境必须是同一个**，
否则会出现“向量已建好、服务却说没装”的分裂状态。

排查与修复：
1. 确认 `er` 用的是哪个 Python：`Get-Command er | Format-List Source`。
2. 在该环境实测导入：`python -c "import sentence_transformers, torch; print('ok')"`
   - `ModuleNotFoundError` → 没装好，执行 `pip install -e .`（依赖已并入基础依赖，会拉 torch）。
   - DLL/OSError → torch 在本机加载失败，换匹配的 torch 版本。
3. 或者直接用仓库内已装好的 `.venv` 启动（最省事）：
   ```powershell
   # 先停掉当前降级中的服务（释放 8892 端口与向量库锁），再：
   .\.venv\Scripts\er.exe --port 8892
   ```
4. 重启后确认 `/api/search/health` 为 `degraded:false`、`embedding_backend_available:true`。

## 不适用场景
- 需要多 worker / 多进程并发写入：请改用独立 Qdrant 服务（`ER_SEARCH_QDRANT_MODE=remote` + Docker），不在本指南范围。
