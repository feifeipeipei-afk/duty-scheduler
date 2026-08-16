# 值日排班管理系统

面向学校老师/班委的 Flask + SQLite 值日排班工具。系统重点是“少操作、少出错”：老师进入工作台后可以检查问题、导入学生名单、预览发布排班、打印/导出排班、处理请假换人和批量完成。

## 技术栈

| 组件 | 说明 |
|------|------|
| Python | 建议 Python 3.10+ |
| Flask 3.x | Web 框架（应用工厂 + Blueprint 模块化） |
| SQLite | 本地轻量数据库（含幂等迁移） |
| Jinja2 | 页面模板（共享 base 模板） |
| HTML/CSS/JS | 原生前端，无需构建 |

## 项目结构

```
├── app.py                  # 启动入口（python app.py）
├── wsgi.py                 # WSGI 入口（gunicorn 等生产服务器）
├── init_db.py              # 演示数据初始化（需 --force 确认，破坏性）
├── duty_scheduler/         # 核心包
│   ├── __init__.py         #   应用工厂 create_app()
│   ├── db.py               #   连接管理、Schema 单一定义、迁移
│   ├── helpers.py          #   输入校验与通用工具
│   ├── calendar_rules.py   #   节假日/调休规则（数据在 data/holidays.json）
│   ├── scheduling.py       #   排班核心业务（预览/发布/替补/健康检查）
│   ├── xlsx.py             #   Excel/CSV 导入解析与导出（含上传加固）
│   ├── auth.py             #   登录/登出、失败限速、路由守卫
│   └── routes/             #   页面与 API 蓝图
├── templates/              # Jinja2 页面（base.html 共享侧边栏）
├── static/                 # CSS / JS（无构建步骤）
└── tests/                  # pytest 测试（39 个用例）
```

## 运行

```bash
pip install -r requirements.txt
python init_db.py --force   # 可选：写入演示数据（会删除现有数据库！）
python app.py
```

> 不运行 `init_db.py` 也可以：`python app.py` 启动时会自动建表并执行老库迁移（含
> 重复排班清理和唯一索引补建），已有数据不受影响。

回归测试（推荐提交前运行）：

```bash
pip install pytest ruff
python -m pytest tests/ -v
ruff check app.py init_db.py wsgi.py duty_scheduler tests
```

访问地址：

| 页面 | 地址 |
|------|------|
| 学生入口 | http://127.0.0.1:5001 |
| 老师后台 | http://127.0.0.1:5001/admin |

默认后台密码：`admin123`（仅限本机体验，生产环境必须修改，见下文安全配置）。

## Docker 部署（推荐的生产方式）

```bash
cp .env.example .env        # 编辑 ADMIN_PASSWORD 和 FLASK_SECRET_KEY
docker compose up -d --build
```

- 数据库持久化在 `duty-data` 卷中，重建容器不丢数据。
- 使用 gunicorn（2 worker × 4 线程）承载并发；SQLite 场景不宜再调高。
- 也可不用 Docker 直接跑 WSGI：`gunicorn --bind 0.0.0.0:5001 --workers 2 wsgi:app`。

## 环境变量与安全配置

| 变量 | 说明 |
|------|------|
| `ADMIN_PASSWORD` | 后台管理密码，默认 `admin123`。生产环境务必修改。 |
| `FLASK_SECRET_KEY` | 会话签名密钥。不设置则每次重启所有登录失效；多副本部署必须一致。生成：`python -c "import os; print(os.urandom(24).hex())"` |
| `FLASK_DEBUG` | 调试模式，生产保持 `0`。 |
| `DUTY_SCHEDULER_DB` | SQLite 文件路径，默认项目目录下 `duty_scheduler.db`（Docker 内为 `/data/duty_scheduler.db`）。 |
| `PORT` | 监听端口，默认 `5001`。 |

安全特性：登录失败按 IP 限速（5 次/分钟）、恒定时间密码比较、登出仅接受 POST、
上传 xlsx 的大小/条目/DOCTYPE 加固、`/admin` 路由统一登录守卫。启动时若检测到
默认密码或未设置密钥会在控制台打印醒目提示。

## 老师使用流程

1. 进入 `/admin` 老师工作台。
2. 在“学期设置”中确认当前学期已激活。
3. 在“班级学生”中创建班级、导入或维护学生名单。
4. 在“排班”页选择班级和月份，点击“生成预览”。
5. 确认预览没有阻止项后点击“确认发布”。
6. 使用“打印本月”张贴排班表，或“导出 Excel”留档。
7. 日常可在排班页标记完成、批量完成、换人、请假自动找替补。

## 已支持功能

- 多学期、多班级管理（学期日期范围重叠校验）。
- 学生 A/B 值日段管理，页面显示为“上半学期/下半学期”。
- 排班预览与确认发布，避免误生成后直接写入；发布冲突返回 409。
- 排班冲突提示：已有排班、节假日/非工作日、人数不足、重复数据等。
- 法定节假日和调休工作日内置识别（数据文件 `duty_scheduler/data/holidays.json`，
  每年国务院办公厅公布新安排后更新该文件即可，无需改代码）。
- Excel/CSV 学生名单导入预览，重复姓名默认跳过。
- 学生重复合并，迁移排班、请假和调班引用。
- 排班 Excel 导出和 A4 打印页。
- 请假自动从同组选择替补；停用学生后自动补位或置空岗位。
- 调班、请假、发布、批量完成等操作记录（完整审计日志）。
- 数据健康检查：无激活学期、A/B 组人数不足、非法日期、停用学生引用、重复排班等。
- 前端无障碍支持：模态框焦点捕获/Esc 关闭、键盘可操作的选择器、
  `prefers-reduced-motion`、WCAG AA 对比度。

## 主要页面

| 页面 | 路径 | 用途 |
|------|------|------|
| 学生入口 | `/` | 学生查询自己的值日安排 |
| 老师工作台 | `/admin` | 快捷入口和问题提醒 |
| 排班 | `/admin/schedule` | 预览发布、打印导出、完成、换人、请假 |
| 班级学生 | `/admin/classes` | 班级、学生、导入、合并重复学生 |
| 假期设置 | `/admin/holidays` | 自定义假期和系统节假日导入 |
| 记录与统计 | `/admin/stats` | 值日次数和学生详情 |
| 学期设置 | `/admin/semesters` | 创建、激活、删除学期 |

## 数据库表

| 表名 | 说明 |
|------|------|
| `semesters` | 学期 |
| `classes` | 班级和值日星期 |
| `students` | 学生、组别、启用状态 |
| `duty_schedule` | 正式排班（`UNIQUE(class_id, date)` 防重复） |
| `leave_records` | 请假记录 |
| `holidays` | 系统/自定义假期 |
| `change_logs` | 发布、调班、请假、批量完成、合并等操作记录 |

## 常用 API

### 公开接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/classes` | 学生端班级列表 |
| GET | `/api/student/schedule` | 查询老师名单中已有学生的值日记录 |

### 排班接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/schedule/preview` | 生成排班预览，不写数据库 |
| POST | `/admin/schedule/publish` | 确认发布预览（冲突返回 409） |
| POST | `/admin/schedule/generate` | 兼容旧接口：预览后直接发布 |
| GET | `/admin/schedule/list` | 获取排班列表 |
| POST | `/admin/schedule/bulk-status` | 批量标记完成/待完成 |
| POST | `/admin/schedule/swap-between` | 交换两个排班位置的学生 |
| POST | `/admin/schedule/swap` | 替换单个学生（带完整校验与审计） |
| PUT | `/admin/schedule/<id>/swap-date` | 调整值日日期（校验工作日与冲突） |
| POST | `/admin/leave` | 请假并自动选替补 |
| DELETE | `/admin/schedule/<id>` | 删除单条排班 |
| GET | `/admin/schedule/export` | 导出当月排班 Excel |
| GET | `/admin/schedule/print` | 打印版排班页 |

### 学生导入与检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/students/import-template` | 下载学生名单模板 |
| POST | `/admin/students/import-preview` | 预览导入名单 |
| POST | `/admin/students/import-confirm` | 确认导入名单 |
| POST | `/admin/students/merge` | 合并重复学生 |
| GET | `/admin/health` | 数据健康检查 |
| GET | `/admin/change-logs` | 操作记录 |

> 说明：部分接口（如 `PUT /admin/semesters/<id>`、统计类接口）当前页面未直接
> 调用，作为开放 API 保留，均有登录校验与测试覆盖。

## 排班规则

1. 使用班级当前值日段：A=上半学期，B=下半学期。
2. 每个值日日期安排 2 名学生。
3. 优先选择当前组中值日次数少的学生。
4. 职责在“扫地”和“擦桌子”之间交替。
5. 自动跳过周末、法定节假日和自定义假期；调休工作日会视为可排班。
6. 发布成功后自动切换到另一组。

## 注意

- `init_db.py` 会删除现有数据库并写入演示数据，必须加 `--force` 参数才会执行。
- 当前是单管理员密码模式，不区分多个老师账号。
- Flask 开发服务器仅适合本地或内网试用，正式部署请使用 Docker/gunicorn。
- 每年年底记得按国务院办公厅通知更新 `duty_scheduler/data/holidays.json`
  （文件内含 holidays 与调休 workdays 两个部分），否则次年节假日识别会失效。
