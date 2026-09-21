# 人身损害赔偿办案辅助系统

这是一个面向**单一律所内网**的办案辅助系统，用于案件协作、赔偿试算、统计标准审核、复核任务和审计留痕。它不是面向公众的 SaaS，也不替代承办律师对责任主体、保险顺序、因果关系、鉴定争议和最终诉请金额的判断。

当前架构采用模块化单体：一套 FastAPI 应用、一套 PostgreSQL 数据库和一套可复用领域计算核心。SQLite 仅用于本地开发和自动化测试。旧命令行入口仍可使用，但计算规则只维护一份。

## 已实现能力

- 管理员、律师、助理三类账号；管理员可查看全部案件，律师和助理只可查看已分配案件。
- 案件、成员、当事人、证据元数据、赔偿项目、计算快照和审计日志。
- 按案件类型和法律适用时点选择规则，并把算法版本、规则上下文及统计标准完整固化到快照。
- 统计数据先进入待审核状态，只有已批准标准才能进入正式计算。
- 计算创建人与批准人分离；管理员紧急自批必须填写原因。
- 自动生成证据缺口/风险复核任务；助理不能批准计算或完成律师复核任务。
- 管理员可重置密码、停用账号；责任律师有进行中案件时必须先移交再停用。
- 全国统计数据采集、字段级来源证据、冲突检测、Excel/CSV 导出和数据库导入。

## 关键业务约束

法律适用时点和统计口径是两套独立概念，不能用一个“年份”代替：

- `incident_date`：侵权行为日期；2022 年 5 月 1 日前案件当前版本会关闭失败，交由律师选择历史规则。
- `rule_as_of`：本次法律评估日期；未提供时使用当天。
- `final_judgment_date`：判断 2026 年 6 月 30 日交通事故司法解释（二）的过渡适用。
- `first_instance_debate_end_date`：未手工指定统计年度时，默认使用其上一统计年度。
- `standard_year`：统计标准年度的明确覆盖值，不参与法律规则版本选择。

正式环境缺少所需的已审核统计标准时不会生成可批准结果。开发环境可以使用演示标准形成草稿，但该快照带有阻断标记，不能批准。

## 本地开发

需要 Python 3.12+。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[collector,test]"
$env:AUTO_CREATE_SCHEMA="false"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe personal_injury.web.app:app --reload
```

打开 `http://127.0.0.1:8000/workspace`。开发接口文档位于 `http://127.0.0.1:8000/docs`。

首次初始化管理员：

```powershell
$body = @{username="admin"; password="请替换为强密码"; display_name="系统管理员"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/bootstrap -ContentType application/json -Body $body
```

## 律所内网部署

1. 复制 `.env.example` 为 `.env`，替换数据库密码和初始化令牌。
2. 将 `APP_ENV` 设为 `production`，同时设置 `COOKIE_SECURE=true`、`ALLOW_DEMO_STANDARDS=false`、`ALLOW_OPEN_BOOTSTRAP=false`。
3. 将 `TRUSTED_HOSTS` 和 `PUBLIC_ORIGIN` 改为律所内网域名；`PUBLIC_ORIGIN` 必须是 HTTPS。
4. 由同机反向代理终止 TLS。Compose 只把应用暴露到 `127.0.0.1:8000`，数据库不映射主机端口。
5. 启动服务；容器会先执行确定性的 Alembic 迁移，再启动应用。

```powershell
Copy-Item .env.example .env
# 编辑 .env 后执行
docker compose up --build -d
```

服务通过内网 HTTPS 可访问后，使用 `.env` 中的初始化令牌创建首个管理员：

```powershell
$headers = @{"X-Bootstrap-Token"="与.env中相同的初始化令牌"}
$body = @{username="admin"; password="请替换为强密码"; display_name="系统管理员"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "https://你的内网域名/api/auth/bootstrap" -Headers $headers -ContentType application/json -Body $body
```

初始化成功后清空 `BOOTSTRAP_TOKEN` 并重启应用，初始化接口将保持关闭。

生产模式会拒绝演示统计标准、自动建表、不安全 Cookie、通配可信主机和非 HTTPS 公共来源。

> 当事人姓名、证件号和联系方式目前由数据库明文列保存，应用层未做字段级加密。考虑到单所部署的密钥维护成本，本版本选择“主机/数据库卷全盘加密 + 加密备份 + 最小权限”方案。完成磁盘加密、备份加密和恢复演练之前，不要录入真实委托人数据。

完整部署边界和维护说明见 [架构与安全说明](docs/architecture.md)，接口说明见 [Web 系统说明](docs/web_system.md)。

## 计算器与旧命令行

```powershell
.\.venv\Scripts\python.exe compensation_calculator.py
.\.venv\Scripts\python.exe case_manager.py
.\.venv\Scripts\python.exe document_generator.py
```

根目录的 `compensation_calculator.py` 与 `adjudication_guidance.py` 是兼容入口，实际实现位于 `src/personal_injury/domain/`，避免 Web 与 CLI 出现两套结果。

裁判依据和证据提示见 [裁判思路说明](docs/adjudication_guidance.md)。新手助理处理交通事故案件时，应先按 [办案工作流](docs/junior_assistant_workflow.md) 建立事实表、证据目录和人工审核清单。

## 统计数据采集

```powershell
.\.venv\Scripts\python.exe data_collector.py --start-year 2022 --end-year 2025
.\.venv\Scripts\python.exe data_collector.py --region "江苏省"
.\.venv\Scripts\python.exe data_collector.py --help
```

采集器具备以下保护：

- 只访问配置的官方域名及其子域；每次重定向前重新校验，拒绝跨域跳转。
- 单个响应最大 20 MiB，PDF 最大 500 页。
- HTTP 来源和来源冲突自动标记为“需人工复核”。
- 导出的外部网页文本会转义，防止 Excel/CSV 公式注入。
- 每个字段保留来源链接、标题、发布时间、采集时间、内容 SHA-256、传输安全状态和命中片段。
- 优先查询国家统计局分省年度城镇收入/消费数据，再核对地方公报；使用 `--source nbs` 可只采这两项。
- HTML、XLSX、文字 PDF 按表头、年份、地区和单位抽取；原始文件按 SHA-256 留存，候选值、单位换算与页码/单元格位置随结果保存。
- 就业人员与在岗职工、私营与非私营口径分开；同一口径出现不同数值时保留候选，不自动取首值。
- Excel 新增“候选复核”工作表。缺口径、缺单位、扫描件及冲突不会自动补值。

采集结果导入数据库后仍为 `pending`，须由律师或管理员核验并批准后才能用于正式计算：

```powershell
personal-injury-import-collector --file data_collection_status.json
```

工作台的“统计标准复核”可查看证据、下载留存原文并批准。采集器与 Web 必须使用同一原文目录（默认当前工作目录的 `data/source_archive`，可通过 `STATISTICAL_ARCHIVE_DIR` 指定）。Compose 将主机的该目录以只读方式挂载给 Web。地区或统计年度明确错配时不能批准；缺少旧版证据或存在告警时必须填写人工核验说明。

结构化查询、候选复核及验证边界见 [数据抽取与复核说明](docs/data_extraction.md)。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

测试覆盖计算规则边界、包安装边界、角色权限、双人复核、会话安全、采集器网络边界以及 Alembic 升级/降级。

## 法律与产品边界

- 当前只完整支持 2022 年 5 月 1 日起的内置规则；更早案件必须由律师另行核对。
- “责任比例后金额”不处理交强险、商业险、垫付款、道路救助基金和工伤待遇的具体抵扣顺序。
- 精神损害抚慰金没有全国统一固定档位，默认不自动计入。
- 当前只保存证据目录和文件元数据，不上传、解析或托管案件文件。
- 系统输出是办案辅助材料，不构成法律意见，也不能直接作为最终诉请或结案依据。
