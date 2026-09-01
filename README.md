# 库存管理收银系统

这是一个基于 Flask 的库存管理与收银系统，支持扫码、商品管理、会员折扣等功能。

Inventory and cashier management system.

## 云部署

### 1. 使用 Heroku / Render / Railway

项目已包含：

- `Procfile`：用于 Heroku / Railway / Render 的 Web 启动命令
- `requirements.txt`：包含 `gunicorn` 作为生产级 WSGI 服务器
- `runtime.txt`：指定 Python 3.11

部署时，平台会自动读取这些文件。

### 2. 环境变量

你可以在云平台上设置：

- `PORT`：平台通常会自动提供
- `SECRET_KEY`：Flask 会使用它作为 session 加密密钥
- `FLASK_DEBUG`：如果需要调试模式，可以设置为 `true`
- `DATABASE_URL`：如果你使用 PostgreSQL 或其他云数据库，请设置此环境变量。
  - 例如：`postgresql://user:password@host:port/dbname`
  - 如果未设置，项目默认使用本地 SQLite 文件 `data.db`。
- `ACCOUNTING_API_TOKEN`：新月会计系统服务器调用专用 API 的共享密钥。请使用随机长字符串，并在会计网站服务器端设置相同的值；不要写入前端 JavaScript。
- `FIREBASE_PROJECT_ID`：Firebase 项目 ID，必须与会计网站的 Google 登录项目一致。会计 API 会独立验证 Firebase ID Token，并根据数据库白名单执行管理员、录入和只读权限。

### 会计系统共用数据库

本服务同时提供受 Bearer Token 保护的 `/api/accounting/*` 接口。会计系统的仕訳、员工、工资、年度手续、资料附件和操作记录使用独立的 `accounting_*` 表，不会修改库存、商品或收银销售表。Mooon Shop 销售由现有 `sales` 表同步为只读仕訳。

- 附件当前保存到 PostgreSQL，单个文件上限 10 MB。
- `GET /api/accounting/backup` 可导出会计状态和附件目录 JSON。
- Render 的数据库备份策略由当前付费 PostgreSQL 套餐管理；上线后应在 Render 控制台确认备份保留期。

### 3. 本地 Docker 运行

```bash
docker build -t inventory-cashier .
docker run -p 5000:5000 inventory-cashier
```

然后访问 `http://localhost:5000`。

## 提示

- 当前项目默认使用数据库存储：本地环境下使用 SQLite `data.db`，云平台建议使用 PostgreSQL。
- 如果部署到 Heroku / Railway 等平台，请务必设置 `DATABASE_URL` 指向云数据库，以保证数据持久化。

## Render 部署指南

1. 将项目提交到 GitHub 或 GitLab。
2. 登录 Render，创建新服务：
   - 类型选择 `Web Service`
   - 环境选择 `Docker`
   - Dockerfile 路径保持默认 `Dockerfile`
3. 创建 PostgreSQL 数据库：
   - 名称可设为 `inventory-cashier-db`
   - 选择 `Starter` 计划即可
4. 在 Render Web Service 设置中添加环境变量：
   - `SECRET_KEY`，值请改成生产用随机字符串
   - `DATABASE_URL`，选择从 `inventory-cashier-db` 自动注入
   - `ACCOUNTING_API_TOKEN`，与会计网站服务器端相同
   - `FIREBASE_PROJECT_ID`，与 Firebase Authentication 项目一致
5. 部署后访问 Render 提供的 HTTPS 域名即可。

> 如果你已经添加 `render.yaml`，Render 也会自动识别该配置并按定义创建服务。

## 一键部署步骤

1. 在 GitHub/GitLab 上创建一个新仓库。
2. 在项目根目录执行：

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

3. 在 Render 控制台中：
   - 创建 `Web Service`
   - 选择 `Docker`
   - 选择你刚刚推送的仓库
   - 使用默认 `Dockerfile`
4. 创建 PostgreSQL 数据库（例如 `inventory-cashier-db` Starter 计划）。
5. 在 Render 服务设置中添加环境变量：
   - `SECRET_KEY`
   - `DATABASE_URL`（从 PostgreSQL 数据库自动注入或手动填写）
   - `ACCOUNTING_API_TOKEN`
   - `FIREBASE_PROJECT_ID`

## Render CLI 使用说明

如果你已经设置了 Render API Token：

```bash
export RENDER_TOKEN=<your-render-api-token>
./.venv-1/bin/render-cli list
```

该 CLI 目前可用于检查 Render 服务、查看环境变量和设置环境变量，但不一定支持创建新服务。

你也可以运行：

```bash
./deploy_render.sh <your-repo-url>
```

该脚本会推送代码并给出下一步 Render 上线提示。
