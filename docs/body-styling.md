# 男装身材穿搭

本机入口：`/dashboard/body-styling`。用户可以在空衣橱状态下获得基于身材资料的款式和完整搭配建议。

## 2026-10-30：个人配色与面料升级

新增用户 `styling_profile`，与身体测量分开保存，所有新资料均选填：肤色深浅、底色冷暖倾向、当前发色、眼睛颜色、偏好对比、喜欢/避用色系、面料感受、避用材质、穿衣困扰。肤色与冷暖均按自述记录，不从身高、围度、肤色深浅或族群推断。另增加选填肩宽和大腿围。未知信息仍可生成比较方案，并说明信息不足。

保存仍用 `PATCH /api/v1/users/me`，新增 `styling_profile` 和 `expected_styling_profile_revision`。响应 `styling_profile_revision` 同时覆盖身材和偏好，服务端持行锁比较，防止偏好被其他页面的旧编辑覆盖。生成也可附带这个版本。原 `body_measurements_revision` 保持兼容，其他资料页不用改请求。

新生成的快照标记 `contract_version=2`，保存当时的偏好、身材与最近反馈。原历史字段仍可读取，新字段默认空；旧报告内容不会自动重写。

- 每件纺织服装必须包含面料组织、厚薄档位、垂坠/支撑感、光泽与弹性，并解释选择原因。皮革和非纺织鞋可无面料组织。特性为选款目标，不冒充某件商品的精确克重、混纺比例或性能保证。
- 每套搭配增加配色策略、个人配色理由与整套面料协调理由。支持同色层次、点缀、颜色呼应和对比；后端校验呼应单品确实同色、点缀指向实际单品、对比有颜色依据。
- 显式避用色系和材质为硬约束。避用棉/羊毛/亚麻时，也排除受控目录中相应的混纺。喜欢项和历史反馈是软偏好；不会把一套“不喜欢”扩大为所有单品都禁用。
- 本地 SVG 增加受控的简化组织纹理与配色条，不执行模型提供的 SVG 或 HTML。纹理不模拟真实面料手感。
- 每套可分别反馈整体、颜色和面料的喜欢/不喜欢，再点一次取消。`PATCH /api/v1/body-styling/recommendations/{id}/feedback` 接收 `outfit_index`（0–2）与 `overall/colors/fabrics`；只允许本人，独立保存，不修改原始结果。之后生成会参考最近五份报告中最多六套有效反馈。

目录在 `backend/app/data/body_styling_catalog.json`，浏览器镜像为 `frontend/lib/generated/body-styling-catalog.json`，两者由回归测试核对一致。迁移 `8b74c1a093e2` 仅为 users 增加 styling_profile、报告增加 feedback 两个可空 JSONB 列，已在数据库备份后应用。

## 资料与生成

使用现有 `PATCH /api/v1/users/me` 保存 `body_measurements`，保留其他已存的尺码等字段。生成必须提供有效的数值型 `height`、`chest`、`waist`、`hips`；`weight`、`inseam`、`shoulder_type` 为可选。长度统一为 cm，体重为 kg；内腿长必须小于身高。肩部特点只接受自述 `narrow`、`balanced`、`broad`。

服务端计算腰胸比、腰臀比；已提供内腿长时计算内腿长/身高。不推断缺失值。AI 必须在观察、版型建议和每套搭配中引用实际存在的依据 ID。

资料响应包含 `body_measurements_revision`（身材内容摘要）。身材穿搭页保存时传入 `expected_body_measurements_revision`；服务端持有行锁后比较版本，过期返回 409，不覆盖新资料。未修改的表单随资料刷新同步；有未保存修改时保留编辑，提供“载入最新资料（放弃当前修改）”。生成请求也附带保存返回的版本，拦截保存后至生成前的资料变化。其他资料接口客户端仍兼容原请求格式；语言等资料变化不会引发身材冲突。

只需启用文字模型。`configure-ai.command` 中文字模型必填、图片模型选填；跳过图片模型会关闭内部视觉功能。未启用或未配置文字模型时，资料保存和历史读取可用，推荐返回明确的不可用状态。

## API

所有接口均要求当前用户登录，历史只允许记录所属用户访问。

- `GET /api/v1/body-styling/status`：返回 `enabled`、`configured`、`available`。此处表示开关和配置就绪，非实际网络连通性保证。
- `POST /api/v1/body-styling/recommendations`：创建成功返回 201。
- `GET /api/v1/body-styling/recommendations?limit=10&offset=0`：带总数的分页列表，limit 为 1–50。
- `GET /api/v1/body-styling/recommendations/{id}`：返回身材快照、事实、结构化报告和模型名称；不存在或越权均为 404。

生成请求示例：

```json
{"occasion":"daily","style":"minimal","goals":["balance","comfort"],"season":"all"}
```

可选场合：`daily/work/date/weekend/formal`。风格：`minimal/smart_casual/street/sporty/classic`。目标：`balance/elongate_legs/midsection/shoulders/comfort`。季节：`all/spring/summer/autumn/winter`。

响应包含 `id`、`created_at`、`input_snapshot`、`facts`、`result`、`model`。`result` 包含 summary、observations、四个领域的 fit_advice、unknowns、三套 outfits。完整字段及服装枚举以 Pydantic schema 和本机 `/docs` 的 OpenAPI 为准。

错误 detail 包含稳定的 `code` 和 `message`：

| HTTP | code | 行为 |
| --- | --- | --- |
| 409 | body_measurements_conflict | 载入最新资料后重新保存或生成 |
| 422 | invalid_measurements | 补全有效量体数据 |
| 503 | ai_unavailable | 配置并启用文字模型 |
| 504 | ai_timeout | 保留资料，允许重试 |
| 502 | invalid_ai_response | 修复尝试仍未得到完整有效结果 |
| 502 | ai_failed | 模型服务异常 |

新生成有每用户每分钟 5 次限制，完整生成和一次格式修复合计最多 180 秒。模型格式无效、缺少鞋/上衣/裤子、重复搭配、引用未提供依据或无法绘制的服装属性会被拒绝；只修复重试一次。失败不保存推荐记录。

生成内部使用独立的 `BodyStyleDraft` 合约。正文中的测量值和比值必须通过 `{{height}}`、`{{waist_chest_ratio}}` 等占位符引用，且每项引用必须在对应 evidence 中；服务端拒绝手写数值、缺失依据的占位符及缺失内腿长/体重的断言，再代入实际带标签的数值。信息不足提示由服务端按缺失字段生成。服装只允许模型选择颜色、材质及版型枚举；`color_name` 和 `description` 从这些字段生成，禁止模型另写相矛盾的说明。原历史格式及快照保持可读取。这些结构校验不能证明所有自然语言推理都正确，实际建议质量仍需真实模型验证。

离开页面时会取消浏览器的生成请求，并忽略晚到的保存/生成结果，避免后台完成后把用户强制导航回报告页。已在服务端完成并保存的报告仍可从历史查看。

## 示意卡与历史

服装 slot、kind、fit、length、rise 和六位十六进制配色由后端校验。前端用受控 SVG 路径绘制，不执行模型返回的 SVG/HTML，也不加载远程图片。版型宽窄、裤腰和裤长均使用与文字相同的属性；插图用于说明款式，非试穿或品牌尺码预测。

`body_style_recommendations` 独立于已有衣物和 Outfit，保存当时的输入、事实、结果和模型。迁移 `73c01bd9a104` 仅新增表和索引；用户删除时由外键级联清理报告。

部署前已在 `data/backups/` 保存数据库备份。回退应用时可保留新增表，避免删除已经生成的报告。

## 验证

- 199 个后端测试通过：新增肤色与偏好校验、颜色/材质避用、面料完整性、配色呼应、偏好冲突、反馈隔离与旧报告兼容回归。
- 45 个前端测试通过：新增偏好保存、颜色互斥选择、目录一致性、本地纹理与偏好版本冲突。
- 类型检查、Python lint、前端 lint、多语言检查和生产构建通过。前端 lint 仅有原有品牌 logo 的 img 提示。
- 无头浏览器在独立测试数据库、Redis DB 14 和随机临时账号中验证：量体复用与保存、三套示意卡、改变身材、历史回看、超时/无效结果提示及 390px 手机布局。
- 使用已配置的 gpt-6.1-sol（low）与合成资料完成两组真实调用：有肤色/偏好并避用红色和羊毛，以及所有外观资料未知。均生成三套完整搭配、具体面料属性和协调理由，遵守避用项，未知时不作个人肤色匹配结论。未将真实用户资料用于测试，也未写入真实用户历史。
- 模拟模型仅在独立浏览器测试进程中注入，正式应用没有模拟生成入口。模型自然语言建议仍应结合实际试色、标签和试穿反馈评估。
