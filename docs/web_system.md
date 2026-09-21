# 律所内网 Web 系统说明

## 使用边界

系统按单一律所、单数据库设计，不包含租户隔离、客户门户、公开注册、在线支付或外部文件共享。部署目标是律所自有服务器或受控内网，不应直接暴露到公网。

## 角色与数据范围

| 角色 | 案件范围 | 主要权限 |
| --- | --- | --- |
| 管理员 | 全部案件 | 用户维护、案件分配、来源确认、计算批准、审计查看 |
| 律师 | 负责或加入的案件 | 业务录入、试算、完成复核、批准他人创建的计算 |
| 助理 | 加入的案件 | 业务录入和试算；不能完成律师复核或批准计算 |

案件成员角色必须与账号系统角色一致。账号角色创建后暂不支持直接修改；需要调整岗位时，由管理员停用旧账号并按新角色建立账号，避免历史审计语义变化。

管理员可以重置密码和停用账号。停用责任律师前，必须先把其 `open` 或 `review` 案件移交给其他在职律师；重置密码或停用账号会注销该用户的现有会话。

## 计算和复核

1. 录入案件事实日期、辖区、统计地区、证据和赔偿项目。
2. 发起试算时，系统独立解析法律评估时点与统计标准年度。
3. 计算快照保存算法版本、规则版本、法律适用上下文、输入、原始金额、责任比例后金额、统计标准及风险提示。
4. 有证据缺口或风险标记的正金额项目会生成复核任务。
5. 创建者不能批准自己的快照；管理员紧急自批必须记录原因。
6. 存在开放复核任务时，律师只有填写保留意见原因后才能批准。
7. 使用演示标准或缺少正式标准的快照不能批准。

`standard_year` 只表示统计口径，不决定法律规则。法律规则由 `rule_as_of`、`incident_date` 和必要时的 `final_judgment_date` 共同判断。未显式传 `standard_year` 时，系统用一审法庭辩论终结年份减一；日期缺失时正式试算会因缺少对应标准而关闭失败。

## 主要接口

| 能力 | 接口 |
| --- | --- |
| 初始化、登录、注销 | `POST /api/auth/bootstrap`、`POST /api/auth/login`、`POST /api/auth/logout` |
| 当前用户 | `GET /api/auth/me` |
| 用户维护 | `GET/POST /api/users`、`PATCH /api/users/{id}` |
| 案件与成员 | `GET/POST /api/cases`、`PATCH /api/cases/{id}`、`POST/DELETE /api/cases/{id}/members...` |
| 案件详情 | `GET /api/cases/{id}` |
| 当事人、证据、赔偿项 | `POST /api/cases/{id}/parties|evidence|claims` |
| 试算与批准 | `POST /api/cases/{id}/calculations`、`POST /api/cases/{id}/calculations/{snapshot}/approve` |
| 复核任务 | `GET /api/cases/{id}/review-tasks`、`POST /api/cases/{id}/review-tasks/{task}/complete` |
| 法律来源、统计标准 | `GET /api/legal-sources`、`GET /api/statistical-standards` 及对应确认接口 |
| 审计与导出 | `GET /api/audit-logs`、`GET /api/cases/{id}/export?format=markdown` |

登录凭证只通过 HttpOnly、SameSite=Strict Cookie 返回，不出现在 JSON 响应中。生产环境还要求 Secure Cookie、HTTPS 来源和明确可信主机。

## 数据迁移

生产环境不调用 ORM `create_all`，必须执行 Alembic：

```powershell
alembic upgrade head
alembic check
```

初始迁移显式创建每张表、索引和外键，可在空数据库升级并确定性降级。早期由原型代码直接生成的 SQLite 数据库不保证可原地迁移；先备份并导出业务数据，再在新库执行迁移和导入。

## 当前不做的功能

- 多律所租户和跨机构协作。
- 案件文件上传、OCR、病毒扫描和对象存储。
- 完整的保险赔付顺序、重复受偿和历史规则引擎。
- 自动给出最终法律结论或自动批准计算。
- 用户自行改密、找回密码和外部身份提供商登录；当前由管理员重置。
