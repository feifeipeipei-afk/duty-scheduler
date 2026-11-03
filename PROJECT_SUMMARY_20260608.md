# 值日排班管理系统 - 改进总结

> 本文件原为 2026-06-08 的开发日志，内容已过时（旧端口 5000、旧文件结构、
> 已不存在的模板等）。2026-08-16 全面改进后重写为变更记录；
> 当前的使用说明以 [README.md](README.md) 为准。

## 时间: 2026-08-16

## 本次改进内容

### 1. 高危 Bug 修复
- **删除路径 500**：`change_logs` 外键无 ON DELETE 动作导致删排班/删学生/删班级/
  删学期在发布过排班后必然 500。现改为事务内先解除审计引用再删除。
- **停用学生不再连带删除搭档值日**：原 `cleanup_invalid_schedules` 整行删除；
  现在优先自动找同组替补，找不到则只置空该岗位并写审计。
- **重复排班**：`duty_schedule` 增加 `UNIQUE(class_id, date)` 唯一索引，
  并提供幂等迁移（自动清理老库重复数据），发布冲突统一返回 409。
- **输入校验补齐**：`validate_date` 往返格式化拒绝 `2026-2-3` 类非规范日期；
  调班/换日期/请假/导入确认接口补齐数字解析、存在性、同班、同岗、
  同日冲突校验；调班补写审计日志。
- **其他**：SQL 双引号字面量改单引号；请假时间戳统一；学期日期重叠校验；
  404/500 错误页区分浏览器（HTML）与 API（JSON）。

### 2. 安全加固
- 登录密码恒定时间比较（`hmac.compare_digest`）+ 按 IP 限速（5 次失败/分钟 → 429）。
- 登出从 GET 改为 POST（侧边栏新增退出按钮）。
- `/admin` 路由守卫改为精确路径白名单。
- xlsx 上传加固：5MB 大小上限、zip 条目数/解压大小上限、拒绝 DOCTYPE/实体声明。
- 启动时对默认密码 / 未设置 `FLASK_SECRET_KEY` 打印醒目警告。

### 3. 模块化重构（app.py 2378 行 → 包结构）
```
duty_scheduler/
├── __init__.py        # create_app() 应用工厂
├── db.py              # Schema 单一定义 + init/migrate + 查询助手
├── helpers.py         # 输入校验与通用工具
├── calendar_rules.py  # 节假日数据（data/holidays.json）与 is_workday
├── scheduling.py      # 预览/发布/替补/均衡度/健康检查
├── xlsx.py            # 名单导入解析与导出
├── auth.py            # 登录/登出/限速/路由守卫
└── routes/            # pages / admin_api / schedule_api / stats_api / student_api
```
- 路由路径与响应格式完全不变（59 条路由一致，前端零破坏）。
- Schema 收敛为 `db.py` 单一来源，`init_db.py` 引用同一份定义。
- `change_logs` 写入统一走 `log_change()`；页面路由的 content-type 嗅探抽成
  `wants_json_request()`。
- 节假日移入 `data/holidays.json` 数据文件，年度更新无需改代码。
- `init_db.py` 破坏性重建需 `--force` 参数确认。

### 4. 前端改善
- 新增 `base.html` 共享侧边栏（消除 6 处复制），active 状态由服务端判断。
- 无障碍：模态框 `role="dialog"`/焦点捕获/Esc 关闭/点击遮罩关闭；
  学生端组选择器与标签页改为可键盘操作的按钮；emoji 图标 `aria-hidden`；
  灰阶对比度提升至 WCAG AA。
- 移除被墙的 Google Fonts `@import`，改系统字体栈。
- Excel 导出改 fetch→blob 下载（错误可 toast，不再渲染裸 JSON）。
- 删除死代码：整个 `charts.js`（含未转义 XSS 隐患）、死 CSS 规则、`renderList`。

### 5. 测试与基础设施
- pytest 测试体系：39 个用例覆盖删除路径、调班校验、发布冲突、限速、
  xlsx 加固、登录守卫、迁移幂等等此前完全未覆盖的高危区域。
- CI（GitHub Actions）：ruff lint + pytest（Python 3.10/3.12 矩阵）。
- Docker 部署：Dockerfile（gunicorn 2×4）+ docker-compose.yml（数据卷）+
  wsgi.py + .env.example + .dockerignore。
- `requirements.txt` 锁定 `flask>=3.0,<4`，移除未使用的 `requests`；
  新增 `pyproject.toml`（ruff/pytest 配置）。
- README 全面同步（端口、结构、部署方式、安全配置、节假日年度更新说明）。

## 验证结果
- `pytest tests/`：39 passed
- `ruff check`：All checks passed
- 全部 9 个页面渲染 200；59 条路由与重构前一致
- 手动冒烟：登录 → 建学期 → 建班 → 导名单 → 预览 → 发布 → 调班 → 请假 →
  删除排班/学生/班级/学期 全部正常（不再 500）
