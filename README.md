# 库存管理收银系统

这是一个基于 Flask 的库存管理与收银系统，支持扫码、商品管理、会员折扣等功能。

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
5. 部署后访问 Render 提供的 HTTPS 域名即可。

> 如果你已经添加 `render.yaml`，Render 也会自动识别该配置并按定义创建服务。
