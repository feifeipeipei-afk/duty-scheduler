# 值日记录管理系统

[![CI](https://github.com/feifeipeipei-afk/duty-scheduler/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/feifeipeipei-afk/duty-scheduler/actions/workflows/ci.yml)

面向学校老师与班委的轻量值日管理工具，Flask + SQLite + 原生前端，零构建、单文件数据库、一条命令启动。

## 设计思路：不排班，只记录

传统值日表的问题在于「排班」：一旦遇到请假、调班、临时换人，整张表就得重排，老师和班委要反复维护。

本系统换了个思路——**不提前排班，谁来值日谁自己登记**：

1. 老师只维护一份班级名单，给每个学生标上 A / B 组（A 组上学期值日，B 组下学期值日）。
2. 学生值完日，在手机上打开学生端，选班级、填姓名、点提交，一条记录就完成了。
3. 系统按组统计每人值日次数，并列出**还有谁一次都没值过**。

因为不存在「预定给谁」，请假和调班自然就不需要处理；老师要做的只有一件事：看还有谁没干。

## 功能特性

**学生端（无需登录）**

- 选班级 → 填姓名 → 选择职责（扫地 / 擦桌子）→ 提交，四步完成
- 可补交学期内的往日记录，但不能填写未来日期
- 查看自己的历史值日记录与所属组别
- 查看班级值日榜：各组每人值日次数、未值日名单

**老师后台**

- 多学期管理，同一时间只允许一个激活学期，学期日期范围有重叠校验
- 班级与学生名单管理，Excel / CSV 批量导入（带预览），重复姓名可合并
- 值日记录查看、老师代补录、删除误提交、按月导出 Excel
- 统计看板：值日次数柱状图、均衡度、热力图、班级与学生明细
- 数据健康检查：无激活学期、学期内无班级、同班重名、记录日期越界
- 完整操作审计日志（提交、补录、删除等）

**工程化**

- 应用工厂 + Blueprint 模块化，路由按职责拆分
- 数据库启动时自动建表与幂等迁移，无需手工执行 SQL
- Docker Compose 一键部署，数据落卷持久化
- GitHub Actions：ruff 静态检查 + pytest 回归测试（Python 3.10 / 3.12）

## 技术栈

| 组件 | 说明 |
|------|------|
| Python | 3.10+ |
| Flask 3.x | 应用工厂 + Blueprint 模块化路由 |
| SQLite | 单文件数据库，无需独立服务；含幂等迁移与唯一索引约束 |
| Jinja2 | 服务端渲染模板，共享 `base.html` 布局 |
| HTML / CSS / JS | 原生实现，无打包、无 Node 依赖 |
| Gunicorn | 生产环境 WSGI 服务器 |
| Docker | 镜像构建与 Compose 编排 |

## 快速开始

环境要求：Python 3.10 及以上。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 直接启动（首次启动会自动建表）
python app.py
```

打开浏览器：

| 入口 | 地址 |
|------|------|
| 学生端 | http://127.0.0.1:5050 |
| 老师后台 | http://127.0.0.1:5050/admin |

默认后台密码 `admin123`，**仅用于本机体验**，正式使用前请通过环境变量修改（见下文）。

想先看效果、需要一批演示数据：

```bash
python init_db.py --force
```

> `init_db.py` 会**清空并重建数据库**，因此必须显式带上 `--force` 才会执行。不带参数时它会拒绝运行。

## Docker 部署（推荐用于正式环境）

```bash
cp .env.example .env        # 至少修改 ADMIN_PASSWORD 和 FLASK_SECRET_KEY
docker compose up -d --build
```

访问 http://服务器地址:5001

- 数据库保存在 `duty-data` 卷中，重建容器不丢数据。
- 容器内使用 gunicorn（2 worker × 4 线程）；SQLite 写并发能力有限，不建议继续调高。
- 不用 Docker 也可直接跑 WSGI：
  `gunicorn --bind 0.0.0.0:5050 --workers 2 --threads 4 wsgi:app`

> **端口说明**：`python app.py` 默认 5050（可用 `PORT` 覆盖）；Docker 镜像固定监听 5001，Compose 映射 `5001:5001`。两处端口不一致是历史原因，部署时以实际入口为准。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ADMIN_PASSWORD` | `admin123` | 后台登录密码。生产环境必须修改，否则启动时控制台会打印警告 |
| `FLASK_SECRET_KEY` | 无 | 会话签名密钥。不设置则进程重启后所有登录态失效；多副本部署必须保持一致 |
| `FLASK_DEBUG` | `0` | 调试模式，配合自动重载；生产环境保持 `0` |
| `DUTY_SCHEDULER_DB` | 项目下 `duty_scheduler.db` | SQLite 文件路径；容器内为 `/data/duty_scheduler.db` |
| `PORT` | `5050` | `python app.py` 的监听端口（不影响 Docker） |

生成一个随机密钥：

```bash
python -c "import os; print(os.urandom(24).hex())"
```

## 使用流程

**老师**

1. 访问 `/admin`，用后台密码登录。
2. 在「学期设置」中创建学期并将其激活。
3. 在「班级学生」中新建班级，录入或导入学生名单，为每人标注 A / B 组。
4. 学生自行提交值日记录，老师无需操作。
5. 在「值日记录」中查看提交情况，必要时代补录、删除误提交、按月导出 Excel。
6. 在「记录与统计」中查看值日榜，确认还有哪些学生没有值日。

**学生**

1. 打开学生端首页，选择自己的班级。
2. 输入姓名；若班上有同名学生，需额外选择组别。
3. 选择职责（扫地 / 擦桌子），默认当天，也可补选学期内的往日。
4. 提交成功即计入统计。

## 值日规则

1. **组别**：A 组=上半学期值日，B 组=下半学期值日（页面上显示为中文，接口内为 `A` / `B`）。
2. **日期**：必须落在当前激活学期的起止范围内，且不可晚于今天；允许补交往日。
3. **唯一性**：同一学生同一天只能有一条记录，重复提交返回 `409`，数据库唯一索引兜底并发。
4. **名单为准**：提交时姓名必须与老师维护的名单一致（含启用状态），系统不会自动创建学生。
5. **未提交即未值日**：系统据此生成未值日名单。

## 页面一览

| 页面 | 路径 | 说明 |
|------|------|------|
| 学生入口 | `/` | 提交值日记录、查看个人记录与班级值日榜 |
| 老师登录 | `/admin/login` | 后台登录（GET 显示表单，POST 提交） |
| 老师工作台 | `/admin` | 功能入口与待办提醒 |
| 学期设置 | `/admin/semesters` | 学期创建、编辑、激活、删除 |
| 班级学生 | `/admin/classes` | 班级与学生名单管理、导入、合并重名 |
| 值日记录 | `/admin/records` | 记录列表、代补录、删除、导出 Excel |
| 记录与统计 | `/admin/stats` | 值日榜、未值日名单、图表与明细 |

> `/admin/students` 是学生名单的数据端点，前端复用班级页；直接访问同样需要登录。

## API

所有 `/admin/**` 接口都经过登录守卫，未登录会被重定向到登录页或返回 401。以下省略 `/admin` 前缀的接口都在该前缀下。

### 学生端公开接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/classes` | 当前激活学期的班级列表 |
| POST | `/api/duty/submit` | 提交值日记录，参数 `class_id`、`name`、`group`(可选)、`duty_type`、`date`(可选，默认今天) |
| GET | `/api/duty/summary` | 班级值日榜，参数 `class_id`；返回各组次数与未值日名单 |
| GET | `/api/student/records` | 学生个人记录，参数 `class_id`、`name`、`group`(可选) |

提交成功响应示例：

```json
{
  "message": "值日记录提交成功",
  "student": { "id": 12, "name": "张三", "group_name": "A" },
  "group_label": "上半学期",
  "record": { "id": 88, "date": "2026-11-03", "duty_type": "扫地" }
}
```

### 学期与班级

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/semesters` | 学期列表（JSON 探测） |
| POST | `/admin/semesters` | 新建学期 |
| PUT | `/admin/semesters/<id>` | 修改学期 |
| DELETE | `/admin/semesters/<id>` | 删除学期 |
| POST | `/admin/semesters/<id>/activate` | 激活学期（其余自动置为非激活） |
| GET | `/admin/classes` | 班级列表，参数 `semester_id`（缺省取激活学期） |
| POST | `/admin/classes` | 新建班级 |
| PUT | `/admin/classes/<id>` | 修改班级 |
| DELETE | `/admin/classes/<id>` | 删除班级 |

### 学生名单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/classes/<id>/students` | 班级学生列表 |
| POST | `/admin/students` | 新增学生 |
| PUT | `/admin/students/<id>/group` | 调整学生组别 |
| DELETE | `/admin/students/<id>` | 删除学生 |
| POST | `/admin/students/batch` | 批量添加学生 |
| POST | `/admin/students/merge` | 合并同名学生，记录引用自动迁移 |
| GET | `/admin/students/import-template` | 下载导入模板 |
| POST | `/admin/students/import-preview` | 解析上传文件并预览（不落库） |
| POST | `/admin/students/import-confirm` | 确认导入 |

### 值日记录

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/records` | 记录列表，参数 `class_id`、`month`(`YYYY-MM`) |
| POST | `/admin/records` | 老师代补录 |
| DELETE | `/admin/records/<id>` | 删除记录 |
| GET | `/admin/records/export` | 导出，参数 `class_id`、`month`，返回 xlsx |

导出列：日期、星期、姓名、组别、职责、提交时间。

### 统计与运维

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/stats/quick` | 工作台概览 |
| GET | `/admin/stats/summary` | 班级统计摘要 |
| GET | `/admin/stats/duty-count` | 学生值日次数分布 |
| GET | `/admin/stats/heatmap` | 值日热力图 |
| GET | `/admin/stats/class/<id>` | 班级统计详情 |
| GET | `/admin/stats/student/<id>` | 学生值日详情 |
| GET | `/admin/health` | 数据健康检查 |
| GET | `/admin/change-logs` | 操作日志，可按 `class_id` 过滤 |

## 名单导入格式

支持 `.xlsx` 与 `.csv`，两列即可，首行表头可写可不写：

| 姓名 | 组别 |
|------|------|
| 张三 | A |
| 李四 | B |

- 组别接受 `A` / `B`，也接受 `上半学期` / `下半学期`、`上` / `下`；缺省按 A 组处理。
- 导入分两步：先 `import-preview` 预览解析结果，确认后再 `import-confirm` 落库。
- 同班同名学生默认跳过，导入后可在界面上手动合并。
- 上传做了大小、条目数与 DOCTYPE 加固，避免 XML 实体注入类问题。

## 数据健康检查

`GET /admin/health` 会返回两类问题：

| 级别 | 触发条件 | 处理建议 |
|------|----------|----------|
| `block` | 没有激活学期 | 到学期设置中激活一个 |
| `warn` | 激活学期下没有任何班级 | 新建班级 |
| `warn` | 同一班级存在同名学生 | 在班级页合并，避免学生端提交歧义 |
| `warn` | 值日记录日期不在所属学期范围内 | 到值日记录页核对并修正 |

## 数据库结构

| 表 | 说明 |
|----|------|
| `semesters` | 学期：名称、起止日期、是否激活 |
| `classes` | 班级：名称、所属学期（`duty_weekday` 为旧版遗留列，现已不使用） |
| `students` | 学生：姓名、班级、组别（`A`/`B`）、是否启用 |
| `duty_records` | 值日记录：一条记录 = 一名学生的一次值日，`UNIQUE(student_id, date)` 防重复 |
| `change_logs` | 审计日志：动作类型、班级、学生、日期、原因、时间 |

旧版排班模式遗留的表仍保留，仅用于承载历史数据，当前代码不再写入：

| 表 | 说明 |
|----|------|
| `duty_schedule` | 旧版排班结果 |
| `leave_records` | 旧版请假与替补 |
| `holidays` | 旧版节假日 |

从旧版本升级不需要手工操作：`init_db()` 在启动时执行幂等迁移，会把旧版中已完成的排班转换为值日记录，原有数据保持不变。

## 安全设计

- 后台单管理员密码模式，比较使用 `hmac.compare_digest`，抗时序攻击。
- 登录失败按 IP 限速：60 秒内连续失败 5 次即临时拒绝。
- 登出仅接受 POST，避免被 GET 链接或图片跨站触发。
- `/admin/**` 统一登录守卫（`before_request` 精确匹配，避免前缀绕过）；白名单仅放行登录/登出、静态资源和学生端公开 API。
- 启动时若检测到默认密码或空密钥，会在控制台打印醒目提示。
- 所有写操作经参数化 SQL；提交路径有唯一索引兜底并发重复。

## 测试

```bash
pip install pytest ruff

python -m pytest tests/ -v
ruff check app.py init_db.py wsgi.py duty_scheduler/ tests/
```

测试覆盖提交与查询主流程、删除路径、安全相关分支（鉴权、限速、上传加固）、参数校验与冒烟用例。CI 会在 Python 3.10 与 3.12 上各跑一遍。

## 目录结构

```
├── app.py                      # 启动入口：python app.py
├── wsgi.py                     # WSGI 入口：gunicorn wsgi:app
├── init_db.py                  # 演示数据初始化（必须 --force）
├── duty_scheduler/
│   ├── __init__.py             # 应用工厂 create_app()
│   ├── db.py                   # 连接管理、Schema 定义、幂等迁移
│   ├── auth.py                 # 登录/登出、失败限速、路由守卫
│   ├── helpers.py              # 输入规范化与校验
│   ├── scheduling.py           # 学期工具、组别标签、审计日志、健康检查
│   ├── xlsx.py                 # xlsx/csv 解析与生成（含上传加固）
│   └── routes/
│       ├── pages.py            # 页面路由（兼作列表 JSON 端点）
│       ├── admin_api.py        # 学期、班级、学生、导入 API
│       ├── records_api.py      # 值日记录 API 与导出
│       ├── stats_api.py        # 统计 API
│       └── student_api.py      # 学生端公开 API
├── templates/                  # Jinja2 模板
├── static/                     # CSS 与原生 JS
├── tests/                      # pytest 用例
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/ci.yml
```

## 常见问题

**学生提交时提示「名单中没有找到该学生」**
提交以老师维护的名单为准，系统不会自动建学生。请老师在「班级学生」中核对姓名是否一致，或确认该学生为启用状态。

**提示「该班级存在同名学生，请选择组别后重试」**
班上有重名。让学生补选组别即可提交；若确实是重复录入，建议老师在班级页合并。

**提示「值日日期不能晚于今天」**
不允许预先填写未来日期。补交往日可以，只需把日期改到今天或更早，且不早于学期起始日。

**换个学期后学生端看不到班级了**
学生端只显示当前激活学期下的班级。请到「学期设置」激活新学期。

**Docker 起来后访问 5050 打不开**
容器监听的是 5001，Compose 映射的也是 5001，请访问 `http://服务器:5001`。

**重启后后台登录态丢失**
没有设置 `FLASK_SECRET_KEY`。设置固定密钥后，重启不会再踢人。

## 已知限制

- 单管理员密码，不区分多位老师账号，也无权限分级。
- 学生身份靠「班级 + 姓名」识别，无独立账号体系；同名情况依赖组别区分。
- SQLite 面向单机中小规模使用，不适合高并发写入或多实例共享同一数据库文件。
- 前端为原生实现，未做 PWA / 离线缓存。

## 许可

未指定开源许可证。如需在公开场景复用，建议先联系仓库所有者确认授权方式。
