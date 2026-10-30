# Wardrowbe 本机部署

部署日期：2026-10-29。上游：<https://github.com/Anyesh/wardrowbe>，源码快照 `0bbca3a`，MIT。

## 访问与登录

- 应用：<http://127.0.0.1:18083>
- 项目管理面板：<http://127.0.0.1:3120/projects/wardrowbe>
- 后端就绪检查：<http://127.0.0.1:18084/api/v1/health/ready>

这是只监听本机的个人部署，采用上游的本地开发登录方式：输入邮箱和显示名称即可登录，不需要密码。每次使用相同邮箱会进入同一个衣橱。首次登录按页面引导创建资料；在“设置 → 身体测量”填写身高、体重和胸腰臀围。浏览器语言为中文时自动使用简体中文，也可以在设置中切换。

## AI 服务

2026-10-30 已接入用户提供的文字服务，模型为 `gpt-6.1-sol`，使用 `AI_REASONING_EFFORT=low`（该模型不支持 `none`），身材穿搭推荐已启用。密钥仅保存在本机 `.env`。需要衣物自动识别时，再填写 `AI_VISION_MODEL` 并将 `AI_VISION_ENABLED` 设为 `true`。

双击项目里的 `configure-ai.command`，填写兼容 OpenAI 的 API 地址、文字模型和密钥；图片模型选填，身材穿搭只需要文字模型。密钥输入时不回显，仅保存在权限为 `0600` 的本机 `.env` 中；脚本会重启 API 与后台任务。

也可以编辑 `.env` 中以下配置，再在面板重启 backend、worker、image-worker：

```dotenv
AI_INTERNAL_ENABLED=true
AI_TEXT_ENABLED=true
AI_VISION_ENABLED=false
AI_BASE_URL=https://你的服务地址/v1
AI_API_KEY=你的密钥
AI_TEXT_MODEL=用于穿搭推荐的模型
```

本机已有 Sub2API 网关，若选择它，地址为 `http://127.0.0.1:18082/v1`；仍需要该网关签发的 API 密钥和实际可用的模型。本部署没有复制其他项目的凭证。

## 启停

推荐通过管理面板的 Wardrowbe 项目分组一起启停六个服务。终端操作：

```sh
cd /path/to/wardrowbe
./start-all.sh
./stop.sh
```

单独的 `start.sh` 是管理面板调用的前台网页入口，需要先启动 PostgreSQL、Redis、backend。关闭终端不会停止已由管理面板启动的服务。电脑重启后先启动 `projects/manager/start.sh`，再启动 Wardrowbe 项目。

| 服务 | 本机端口 | 用途 |
| --- | --- | --- |
| web | 18083 | 页面和 API 转发 |
| backend | 18084 | 业务 API，启动时自动运行数据库迁移 |
| postgres | 15433 | 独立数据库 |
| redis | 16380 | 独立任务队列 |
| worker | 无 | 自动识别及穿搭后台任务 |
| image-worker | 无 | 本地图片处理队列 |

## 文件和数据

- `.env`：本机配置及随机生成的密钥。
- `config/postgres-password`：本项目数据库密码。
- `data/postgres/`、`data/redis/`：独立持久化数据。
- `data/wardrobe/`：衣物图片。
- `data/rembg/`：已下载的抠图模型；使用时不需重新下载。
- `runtime/`、`.venv/`：项目自己的 Node.js、Python、PostgreSQL、Redis 和依赖，不需要 Docker，也不依赖其他业务项目运行。
- `logs/`：安装和构建日志；运行日志在管理面板查看。
- `config/requirements-local.lock`：实际安装的 Python 包版本。
- `INSTALLATION.json`：本机部署记录（不上传；上游来源见仓库 README）。

本机调整包括运行方式、下述身材穿搭功能和字体加载：Inter 改为项目内的同款字体，避免构建时访问 Google Fonts；字体许可证在 `frontend/app/fonts/OFL.txt`。原有 Docker 部署文件保留。

备份时保存 `.env`、`config/postgres-password`、数据库备份及 `data/wardrobe/`。运行中的 PostgreSQL 应使用 pg_dump 备份，或先停止整个 Wardrowbe 项目再复制数据目录。


## 新增：男装身材穿搭

入口：<http://127.0.0.1:18083/dashboard/body-styling>，首页和桌面/手机导航均已接入。

- 不依赖衣橱。必填身高、胸围、腰围、臀围；体重、内腿长、肩部特点选填。与原设置页共享身材数据。
- 可选择场合、风格、季节及穿着目标。推荐包括比例分析、四类版型建议、三套完整男装搭配及本地 SVG 示意卡。
- 2026-10-30 增加个人配色与面料资料：肤色深浅、冷暖、发色、颜色喜恶、面料感受和穿衣困扰均选填。推荐逐件解释组织、厚薄、垂坠、光泽、弹性，并展示整套配色与面料如何协调。
- 显式避用色系和材质会被过滤。可对每套的整体、颜色、面料分别反馈喜欢/不喜欢，用于后续生成参考。
- 历史报告保存当时的身材快照与模型信息，之后修改资料不影响旧报告。
- 文字 AI 未配置时可以保存资料、查看历史，生成按钮暂不可用。双击 `configure-ai.command` 配置文字模型即可启用。
- 当前中文简体、英文界面文案齐全，其他界面语言的新模块回退为英文。

开发接口、校验与验证结果见 `docs/body-styling.md`。模拟模型仅用于独立测试站点；正式服务没有模拟生成入口。
