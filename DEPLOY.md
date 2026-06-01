# 免费部署说明

推荐组合：

- Render Free：部署前端 Next.js 和后端 FastAPI。
- Neon Free Postgres：保存用户、会话、中间事件和最终报告。

Render 免费实例会在一段时间无访问后休眠，首次访问会慢一些。不要把 SQLite 用作线上持久化数据库，免费 Web Service 的本地文件系统不适合保存长期数据。

## 1. 准备数据库

1. 注册 Neon。
2. 创建一个免费 Postgres 项目。
3. 复制连接串，形如：

```text
postgresql://USER:PASSWORD@HOST/dbname?sslmode=require
```
postgresql://neondb_owner:npg_JL6imN9KtHCn@ep-delicate-voice-apk74n9b.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require

这个值稍后填到 Render 的 `DATABASE_URL`。

## 2. 推送代码

把当前项目推到 GitHub 仓库。确认根目录包含：

- `render.yaml`
- `backend/`
- `frontend/`

## 3. Render Blueprint 部署

1. 打开 Render Dashboard。
2. 选择 `New` -> `Blueprint`。
3. 连接 GitHub 仓库。
4. Render 会读取根目录的 `render.yaml`，创建两个服务：
   - `interview-api`
   - `interview-web`
5. 在 `interview-api` 的环境变量里填写：
   - `ZHIPUAI_API_KEY`
   - `DATABASE_URL`
6. 部署完成后访问：

```text
https://interview-web.onrender.com
```

## 4. 如果修改服务名

如果你在 Render 里改了服务名，记得同步改环境变量：

- `interview-web` 服务：
  - `BACKEND_URL=https://你的后端服务.onrender.com`
- `interview-api` 服务：
  - `CORS_ORIGINS=https://你的前端服务.onrender.com`

## 5. 本地仍然这样运行

本地不设置 `DATABASE_URL` 时会继续使用：

```text
backend/data/interview.db
```

线上设置 `DATABASE_URL` 后会自动切到 Postgres。
