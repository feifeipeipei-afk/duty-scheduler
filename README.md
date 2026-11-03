# 值日记录管理系统

面向学校老师/班委的 Flask + SQLite 值日记录工具。系统重点是“学生自主、老师省心”：
老师只需维护班级名单（按 A/B 组标注值日时段），学生值日完成后自主提交记录，系统自动
汇总并显示还有哪些同学还没有值日。无需提前排班，天然规避请假、调班等复杂事项。

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
│   ├── scheduling.py       #   学期工具、审计日志、组别标签、健康检查
│   ├── xlsx.py             #   Excel/CSV 导入解析与导出（含上传加固）
│   ├── auth.py             #   登录/登出、失败限速、路由守卫
│   └── routes/             #   页面与 API 蓝图
│       ├── pages.py        #     页面路由（学生入口、工作台、记录、统计等）
│       ├── admin_api.py    #     学期、班级、学生与名单导入 API
│       ├── records_api.py  #     值日记录 API（老师代补录/删除/导出）
│       ├── stats_api.py    #     统计 API（值日次数、班级、学生详情）
│       └── student_api.py  #     学生公开 API（提交、汇总、个人记录）
├── templates/              # Jinja2 页面（base.html 共享侧边栏）
├── static/                 # CSS / JS（无构建步骤）
└── tests/                  # pytest 测试
```

## 运行

```bash
pip install -r requirements.txt
python init_db.py --force   # 可选：写入演示数据（会删除现有数据库！）
python app.py
```

> 不运行 `init_db.py` 也可以：`python app.py` 启动时会自动建表并执行老库迁移
> （旧版已完成排班会自动转为值日记录），已有数据不受影响。

回归测试（推荐提交前运行）：

```bash
pip install pytest ruff
python -m pytest tests/ -v
ruff check app.py init_db.py wsgi.py duty_scheduler tests
```

访问地址：

| 页面 | 地址 |
|------|------|
| 学生入口 | http://127.0.0.1:5050 |
| 老师后台 | http://127.0.0.1:5050/admin |

默认后台密码：`admin123`（仅限本机体验，生产环境必须修改，见下文安全配置）。

## Docker 部署（推荐的生产方式）

```bash
cp .env.example .env        # 编辑 ADMIN_PASSWORD 和 FLASK_SECRET_KEY
docker compose up -d --build
```

- 数据库持久化在 `duty-data` 卷中，重建容器不丢数据。
- 使用 gunicorn（2 worker × 4 线程）承载并发；SQLite 场景不宜再调高。
- 也可不用 Docker 直接跑 WSGI：`gunicorn --bind 0.0.0.0:5050 --workers 2 wsgi:app`。

## 环境变量与安全配置

| 变量 | 说明 |
|------|------|
| `ADMIN_PASSWORD` | 后台管理密码，默认 `admin123`。生产环境务必修改。 |
| `FLASK_SECRET_KEY` | 会话签名密钥。不设置则每次重启所有登录失效；多副本部署必须一致。生成：`python -c "import os; print(os.urandom(24).hex())"` |
| `FLASK_DEBUG` | 调试模式，生产保持 `0`。 |
| `DUTY_SCHEDULER_DB` | SQLite 文件路径，默认项目目录下 `duty_scheduler.db`（Docker 内为 `/data/duty_scheduler.db`）。 |
| `PORT` | 监听端口，默认 `5050`。 |

安全特性：登录失败按 IP 限速（5 次/分钟）、恒定时间密码比较、登出仅接受 POST、
上传 xlsx 的大小/条目/DOCTYPE 加固、`/admin` 路由统一登录守卫。启动时若检测到
默认密码或未设置密钥会在控制台打印醒目提示。

## 老师使用流程

1. 进入 `/admin` 老师工作台。
2. 在“学期设置”中确认当前学期已激活。
3. 在“班级学生”中创建班级、导入或维护学生名单，标注 A/B 组
   （A 组=上半学期值日，B 组=下半学期值日）。
4. 学生值日完成后，在学生入口 `/` 自主提交值日记录，无需老师操作。
5. 老师在“值日记录”页查看记录，可代补录、删除误提交、导出 Excel。
6. 在“记录与统计”页查看班级值日榜，确认还有哪些同学没有值日。

## 已支持功能

- 多学期、多班级管理（学期日期范围重叠校验）。
- 学生 A/B 值日段管理，页面显示为“上半学期/下半学期”。
- 学生自主提交值日记录：同一学生同一天防重复提交，日期须在学期内且不晚于今天。
- 班级值日榜与未值日名单，一眼看到还有哪些同学还没有值日。
- 老师代补录值日记录、删除误提交、按月导出 Excel。
- 老数据自动迁移：启动时把旧版已完成排班转换为值日记录，历史数据保留。
- Excel/CSV 学生名单导入预览，重复姓名默认跳过。
- 学生重复合并，自动迁移值日记录引用。
- 提交、补录、删除等操作的完整审计日志。
- 数据健康检查：无激活学期（阻止级）、无班级、同班重名、记录日期越学期等。
- 前端无障碍支持：模态框焦点捕获/Esc 关闭、键盘可操作的选择器、
  `prefers-reduced-motion`、WCAG AA 对比度。

## 主要页面

| 页面 | 路径 | 用途 |
|------|------|------|
| 学生入口 | `/` | 提交值日记录、查看个人记录和班级值日榜 |
| 老师工作台 | `/admin` | 快捷入口和问题提醒 |
| 值日记录 | `/admin/records` | 查看、代补录、删除误提交、导出 Excel |
| 班级学生 | `/admin/classes` | 班级、学生、导入、合并重复学生 |
| 记录与统计 | `/admin/stats` | 值日榜、未值日名单、学生详情 |
| 学期设置 | `/admin/semesters` | 创建、激活、删除学期 |

## 数据库表

| 表名 | 说明 |
|------|------|
| `semesters` | 学期 |
| `classes` | 班级（`duty_weekday` 为旧版遗留列，已不再使用） |
| `students` | 学生、组别（A/B）、启用状态 |
| `duty_records` | 值日记录：一条记录 = 一名学生的一次值日（`UNIQUE(student_id, date)` 防重复提交） |
| `duty_schedule` | 旧版排班模式遗留，不再使用，保留历史数据 |
| `leave_records` | 旧版排班模式遗留，不再使用，保留历史数据 |
| `holidays` | 旧版排班模式遗留，不再使用，保留历史数据 |
| `change_logs` | 提交、补录、删除等操作记录 |

## 常用 API

### 公开接口（学生端）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/classes` | 学生端班级列表 |
| POST | `/api/duty/submit` | 学生自主提交值日记录 |
| GET | `/api/duty/summary` | 班级值日榜：各组值日次数与未值日名单 |
| GET | `/api/student/records` | 学生查询自己的历史值日记录 |

### 值日记录接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/records` | 值日记录页面与列表 |
| POST | `/admin/records` | 老师代补录值日记录 |
| DELETE | `/admin/records/<id>` | 删除误提交的记录 |
| GET | `/admin/records/export` | 导出某班当月值日记录 Excel |

### 学生导入与检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/students/import-template` | 下载学生名单模板 |
| POST | `/admin/students/import-preview` | 预览导入名单 |
| POST | `/admin/students/import-confirm` | 确认导入名单 |
| POST | `/admin/students/merge` | 合并重复学生 |
| GET | `/admin/health` | 数据健康检查 |
| GET | `/admin/change-logs` | 操作记录 |

### 统计接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/stats/quick` | 工作台快速统计 |
| GET | `/admin/stats/summary` | 班级统计摘要 |
| GET | `/admin/stats/duty-count` | 学生值日次数 |
| GET | `/admin/stats/heatmap` | 值日热力图 |
| GET | `/admin/stats/class/<id>` | 班级统计详情 |
| GET | `/admin/stats/student/<id>` | 学生值日详情 |

> 说明：部分接口（如 `PUT /admin/semesters/<id>`）当前页面未直接调用，
> 作为开放 API 保留，均有登录校验与测试覆盖。

## 值日规则

1. 组别：A 组=上半学期值日，B 组=下半学期值日。
2. 学生值日完成后自主提交记录：日期须在学期范围内，且不能晚于今天。
3. 同一学生同一天只能提交一条记录，重复提交返回 409。
4. 未提交即视为未值日，系统据此统计未值日名单。

## 注意

- `init_db.py` 会删除现有数据库并写入演示数据，必须加 `--force` 参数才会执行。
- 老库无需手动处理：启动时自动迁移，旧版已完成排班会转为值日记录，历史数据保留。
- 当前是单管理员密码模式，不区分多个老师账号。
- Flask 开发服务器仅适合本地或内网试用，正式部署请使用 Docker/gunicorn。
