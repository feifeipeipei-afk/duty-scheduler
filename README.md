# 值日排班管理系统

面向学校老师/班委的 Flask + SQLite 值日排班工具。系统重点是“少操作、少出错”：老师进入工作台后可以检查问题、导入学生名单、预览发布排班、打印/导出排班、处理请假换人和批量完成。

## 技术栈

| 组件 | 说明 |
|------|------|
| Python | 建议 Python 3.9+ |
| Flask | Web 框架 |
| SQLite | 本地轻量数据库 |
| Jinja2 | 页面模板 |
| HTML/CSS/JS | 原生前端，无需构建 |

## 运行

```bash
pip install -r requirements.txt
python3 init_db.py   # 首次运行或重置测试数据
python3 app.py
```

快速回归测试：

```bash
python3 tests/test_smoke.py
```

访问地址：

| 页面 | 地址 |
|------|------|
| 学生入口 | http://127.0.0.1:5001 |
| 老师后台 | http://127.0.0.1:5001/admin |

默认后台密码：`admin123`

可选环境变量：

```bash
export ADMIN_PASSWORD="your-password"
export FLASK_SECRET_KEY="your-secret-key"
```

## 老师使用流程

1. 进入 `/admin` 老师工作台。
2. 在“学期设置”中确认当前学期已激活。
3. 在“班级学生”中创建班级、导入或维护学生名单。
4. 在“排班”页选择班级和月份，点击“生成预览”。
5. 确认预览没有阻止项后点击“确认发布”。
6. 使用“打印本月”张贴排班表，或“导出 Excel”留档。
7. 日常可在排班页标记完成、批量完成、换人、请假自动找替补。

## 已支持功能

- 多学期、多班级管理。
- 学生 A/B 值日段管理，页面显示为“上半学期/下半学期”。
- 排班预览与确认发布，避免误生成后直接写入。
- 排班冲突提示：已有排班、节假日/非工作日、人数不足、重复数据等。
- 2026 法定节假日和调休工作日内置识别，即使未手动导入也会跳过。
- Excel/CSV 学生名单导入预览，重复姓名默认跳过。
- 学生重复合并，迁移排班、请假和调班引用。
- 排班 Excel 导出和 A4 打印页。
- 请假自动从同组选择替补。
- 调班、请假、发布、批量完成等操作记录。
- 数据健康检查：无激活学期、A/B 组人数不足、非法日期、停用学生引用、重复排班等。
- 轻动效：页面淡入、列表更新、弹窗进入；支持 `prefers-reduced-motion`。

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
| `duty_schedule` | 正式排班 |
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
| POST | `/admin/schedule/publish` | 确认发布预览 |
| POST | `/admin/schedule/generate` | 兼容旧接口：预览后直接发布 |
| GET | `/admin/schedule/list` | 获取排班列表 |
| POST | `/admin/schedule/bulk-status` | 批量标记完成/待完成 |
| POST | `/admin/schedule/swap-between` | 交换两个排班位置的学生 |
| POST | `/admin/leave` | 请假并自动选替补 |
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

## 排班规则

1. 使用班级当前值日段：A=上半学期，B=下半学期。
2. 每个值日日期安排 2 名学生。
3. 优先选择当前组中值日次数少的学生。
4. 职责在“扫地”和“擦桌子”之间交替。
5. 自动跳过周末、法定节假日和自定义假期；调休工作日会视为可排班。
6. 发布成功后自动切换到另一组。

## 注意

- `init_db.py` 会删除现有 `duty_scheduler.db` 并重建测试数据，真实使用前不要随意运行。
- 当前是单管理员密码模式，不区分多个老师账号。
- Flask 开发服务器仅适合本地或内网试用，正式部署建议使用 WSGI 服务。
