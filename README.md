# Wardrowbe · 个人男装穿搭顾问

基于 [Anyesh/wardrowbe](https://github.com/Anyesh/wardrowbe) 的个人扩展版本，保留衣橱管理功能，新增不依赖衣橱的身材、个人配色和面料穿搭推荐。

## 本版本新增

- **身材资料**：身高、胸围、腰围、臀围；体重、内腿长、肩宽、大腿围等选填，复用已有资料。
- **个人颜色与偏好**：肤色深浅、底色冷暖倾向、发色、颜色喜恶、面料偏好与穿衣困扰均选填；不确定可留空。
- **三套完整搭配**：上衣、裤子、鞋，以及按需增加的外套和配饰；说明版型、个人配色、单品面料和整套协调的依据。
- **面料细节**：组织、厚薄、垂坠、光泽与弹性；显式避用色系和材质会被校验过滤。
- **本地 SVG 示意卡**：受控颜色、版型和简化纹理，不执行模型生成的 SVG/HTML。
- **历史与反馈**：保存输入快照和模型信息，支持整体、颜色、面料反馈；资料更新有版本冲突保护。
- **文字模型即可使用**：兼容 OpenAI 风格的 Chat Completions 接口；不依赖视觉模型或生图服务。AI 未启用时仍能保存资料和查看历史。

功能入口：`/dashboard/body-styling`。API、输出校验与迁移说明见 [docs/body-styling.md](docs/body-styling.md)。

## 从源码启动

需要 Git、Docker 和 Docker Compose。首次构建会安装依赖并下载本地抠图模型，耗时取决于网络。

```sh
git clone https://github.com/wozwdaqian/wardrowbe.git
cd wardrowbe
cp .env.example .env
```

编辑 `.env`，为 `POSTGRES_PASSWORD`、`SECRET_KEY`、`NEXTAUTH_SECRET` 分别设置自己的随机值。可用 `openssl rand -hex 32` 生成随机值。

个人本机使用可以设置 `DEBUG=true`，以启用开发登录；该登录方式只适合可信的本机环境。对外部署请配置 OIDC 或 forward-auth，参阅上游部署文档。

```sh
docker compose -f docker-compose.yml -f docker-compose.source.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.source.yml exec backend alembic upgrade head
```

打开 <http://localhost:3000>。端口可在 `.env` 中调整；首次使用完成登录和个人资料设置即可。

**本分支的新增功能需要上述 `docker-compose.source.yml`。** 原 `docker-compose.yml` 默认拉取上游预构建镜像，单独运行它不会包含本分支的定制功能。

## 配置文字 AI

在 `.env` 中填写自己的服务信息，例如：

```dotenv
AI_INTERNAL_ENABLED=true
AI_TEXT_ENABLED=true
AI_VISION_ENABLED=false
AI_BASE_URL=https://your-provider.example/v1
AI_API_KEY=replace-with-your-own-key
AI_TEXT_MODEL=your-text-model
AI_REASONING_EFFORT=low
AI_TIMEOUT=180
```

`AI_REASONING_EFFORT` 按服务支持的档位设置；`gpt-6.1-sol` 可用 `low`，不支持 `none`。图片识别为另一项能力，需自行配置视觉模型后启用。

更新配置后重新创建使用后端镜像的服务：

```sh
docker compose -f docker-compose.yml -f docker-compose.source.yml up -d --force-recreate backend worker image-worker
```

## 开发与验证

前端：

```sh
cd frontend
npm ci
npm test
npm run i18n:check
npm run build
```

后端使用独立 PostgreSQL 测试数据库和 Redis 测试库：

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export TEST_DATABASE_URL='postgresql+asyncpg://test:test@localhost:5432/wardrowbe_test'
export REDIS_URL='redis://localhost:6379/14'
pytest tests/test_body_styling.py tests/test_users.py tests/test_ai_service.py
```

本机扩展开发阶段已验证 199 项相关后端测试、45 项相关前端测试、前端构建、手机布局，并用合成资料验证两组真实文字模型调用。以上不代表所有平台或所有模型均已验证。面料属性为选款目标，具体商品仍需核对标签、试色和试穿。

原生 macOS 运行脚本保留在仓库中；它们依赖安装时准备的私有 `runtime/`、虚拟环境和服务管理器，首次克隆推荐使用上述 Docker 源码构建方式。已有本机部署说明见 [README.local.md](README.local.md)，通用功能和部署细节见 [README.upstream.md](README.upstream.md)。

## 仓库内容与来源

仓库包含源码、测试、迁移、依赖锁定文件及配置示例。API 密钥、个人身材资料、衣物图片、数据库、备份、日志、构建产物和本机运行时不入库。

保留 CI 和 PR 标题检查；上游自动发布、包发布和社区机器人流程存放于 `.github/upstream-workflows/`，不会自动运行。

上游源码快照：`Anyesh/wardrowbe`，`0bbca3a`。保留原作者版权，沿用 [MIT License](LICENSE)。Inter 字体许可证见 [OFL.txt](frontend/app/fonts/OFL.txt)。
