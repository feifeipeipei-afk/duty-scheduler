# 值日排班管理系统

基于 Python Flask + SQLite 的学校值日排班管理系统，支持多学期、多班级的值日自动排班、调班、请假、统计等功能。

---

## 目录

- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [运行步骤](#运行步骤)
- [功能说明](#功能说明)
- [数据库设计](#数据库设计)
- [API 接口一览](#api-接口一览)
- [排班算法说明](#排班算法说明)

---

## 技术栈

| 组件 | 版本/说明 |
|------|-----------|
| Python | 3.12+ |
| Flask | Web 框架 |
| SQLite | 轻量数据库 |
| Jinja2 | HTML 模板引擎 |
| Chart.js | 前端图表（柱状图） |
| CSS | Apple/WeChat 风格极简设计 |

---

## 项目结构

```
duty-scheduler/
├── app.py                        # 后端主程序（Flask 路由 + 业务逻辑）
├── init_db.py                    # 数据库初始化 + 测试数据脚本
├── requirements.txt              # Python 依赖（flask, requests）
├── duty_scheduler.db             # SQLite 数据库文件（运行后生成）
├── README.md                     # 本文档
│
├── templates/                    # Jinja2 页面模板
│   ├── index.html                # 学生入口页
│   ├── admin.html                # 后台管理首页（仪表盘）
│   ├── admin_login.html          # 后台登录页
│   ├── admin_semesters.html      # 学期管理
│   ├── admin_classes.html        # 班级管理（含学生列表）
│   ├── admin_schedule.html       # 排班管理（日历视图 + 调班面板）
│   ├── admin_holidays.html       # 节假日管理
│   └── admin_stats.html          # 数据统计（图表 + 均衡度）
│
└── static/
    ├── css/
    │   └── style.css             # 全局样式（CSS 变量 + 响应式）
    └── js/
        ├── admin.js              # 后台通用脚本（API 封装、Toast、导航）
        ├── charts.js             # 图表渲染（柱状图、热力图、统计表格）
        └── student.js            # 学生端脚本（查询、自动注册、记录展示）
```

---

## 运行步骤

### 1. 环境准备

确保已安装 Python 3.12+，然后安装依赖：

```bash
pip install flask requests
```

### 2. 初始化数据库（首次运行）

```bash
python init_db.py
```

此操作会：
- 删除已有的 `duty_scheduler.db`
- 创建 6 张数据表（semesters, classes, students, duty_schedule, leave_records, holidays）
- 插入测试数据：1 个学期、2 个班级、28 名学生、9 天节假日

### 3. 启动服务

```bash
python app.py
```

服务将在 `http://0.0.0.0:5000` 启动（调试模式）。

可通过环境变量配置：
```bash
export FLASK_SECRET_KEY="your-secret-key"   # Flask session 密钥（默认自动生成随机值）
export ADMIN_PASSWORD="your-password"        # 后台管理员密码（默认 admin123）
```

### 4. 访问地址

| 页面 | 地址 | 说明 |
|------|------|------|
| 学生入口 | http://127.0.0.1:5000 | 学生查询值日安排 |
| 管理后台 | http://127.0.0.1:5000/admin | 管理员登录后使用 |

**默认后台密码：** `admin123`

---

## 功能说明

### 学生端

- 选择班级 → 选择值日时间段（上半学期 A / 下半学期 B）→ 输入姓名 → 查询
- **首次查询自动注册**：系统自动将学生添加到对应班级和组别
- 查看值日日期、星期、职责类型（擦桌子/扫地）、完成状态
- 支持按 全部/已完成/未完成 筛选

### 管理后台

#### 📅 学期管理
- 创建学期（名称、起止日期）
- 激活当前学期（唯一激活）
- 删除学期（有关联班级时禁止删除）

#### 🏫 班级管理
- 创建班级（名称、值日星期几）
- 展开查看学生列表
- 切换当前值日组（A↔B）
- 调整学生组别、移除学生
- 删除班级（级联删除关联数据）

#### 📝 排班管理
- 选择班级 + 年月 → 生成排班
- 日历视图展示当月排班
- 标记值日完成
- **调班功能**：选择要替换的学生 → 从其他日期选择替换人选 → 确认调换

#### 🎌 节假日管理
- 一键导入国家法定节假日（2025-2026）
- 手动添加自定义假期（如运动会、校庆）
- 支持中国调休工作日（周末调整为上班日）
- 删除自定义假期（系统假期不可删）

#### 📊 数据统计
- 班级总览：排班总数、学生数、A/B 组均衡度
- 柱状图：每人值日次数对比
- 学生卡片：点击查看详情（日期、职责、状态）

---

## 数据库设计

### ER 图（简化）

```
semesters 1──N classes 1──N students
                  │
                  └──1──N duty_schedule
                              │
                              └── original_student1_id / original_student2_id（调班记录）

students 1──N leave_records ──N students (replacement)

semesters 1──N holidays
```

### 表结构

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `semesters` | 学期 | name, start_date, end_date, is_active |
| `classes` | 班级 | name, semester_id, duty_weekday (1-5), current_group (A/B) |
| `students` | 学生 | name, class_id, group_name (A/B), is_active |
| `duty_schedule` | 排班 | class_id, date, student1_id, student2_id, duty1_type, duty2_type, status, original_student1_id, original_student2_id |
| `leave_records` | 请假 | student_id, date, reason, replacement_id |
| `holidays` | 节假日 | date (UNIQUE), name, is_system, semester_id |

---

## API 接口一览

### 页面路由（返回 HTML）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 学生入口页 |
| GET | `/admin` | 后台首页 |
| GET | `/admin/login` | 登录页 |
| GET | `/admin/semesters` | 学期管理页 |
| GET | `/admin/classes` | 班级管理页 |
| GET | `/admin/schedule` | 排班管理页 |
| GET | `/admin/holidays` | 节假日管理页 |
| GET | `/admin/stats` | 数据统计页 |

### 公开 API（无需登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/classes` | 获取班级列表（供学生端使用） |
| GET | `/api/student/schedule` | 查询/自动注册 + 获取值日安排 |

### 管理 API（需登录，返回 JSON）

> 以下 API 通过 `?format=json` 或 `Content-Type: application/json` 触发 JSON 响应。

**学期管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/semesters` | 创建学期 |
| PUT | `/admin/semesters/<id>` | 更新学期 |
| DELETE | `/admin/semesters/<id>` | 删除学期 |
| POST | `/admin/semesters/<id>/activate` | 激活学期 |

**班级管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/classes` | 创建班级 |
| PUT | `/admin/classes/<id>` | 更新班级 |
| DELETE | `/admin/classes/<id>` | 删除班级（级联） |
| GET | `/admin/classes/<id>/students` | 获取班级学生 |
| POST | `/admin/classes/<id>/switch-group` | 切换值日组 |

**学生管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/students` | 添加学生 |
| DELETE | `/admin/students/<id>` | 删除学生（软删除） |
| PUT | `/admin/students/<id>/group` | 修改学生组别 |
| POST | `/admin/students/batch` | 批量添加学生 |

**排班管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/schedule/generate` | 生成排班（支持按月） |
| GET | `/admin/schedule/list` | 获取排班列表 |
| GET | `/admin/schedule/duty` | 获取某天值日详情 |
| POST | `/admin/schedule/swap` | 替换单个学生 |
| POST | `/admin/schedule/swap-between` | 交换两个排班位置的学生 |
| GET | `/admin/schedule/swap-records` | 获取调班记录 |
| DELETE | `/admin/schedule/swap-records/<id>` | 撤销调班 |
| DELETE | `/admin/schedule/<id>` | 删除排班记录 |
| PUT | `/admin/schedule/<id>/complete` | 标记完成 |
| PUT | `/admin/schedule/<id>/swap-date` | 调整日期 |

**请假管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/leave` | 请假（自动选替补） |

**节假日管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/holidays` | 添加自定义假期 |
| DELETE | `/admin/holidays/<id>` | 删除假期 |
| POST | `/admin/holidays/init-system` | 初始化系统节假日 |

**数据统计**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/stats/quick` | 快速统计（班级数/学生数/本月排班） |
| GET | `/admin/stats/summary` | 班级统计摘要 |
| GET | `/admin/stats/duty-count` | 每人值日次数 |
| GET | `/admin/stats/heatmap` | 热力图数据 |
| GET | `/admin/stats/class/<id>` | 班级详细统计 |
| GET | `/admin/stats/student/<id>` | 学生详细记录 |

---

## 排班算法说明

### 核心逻辑

1. **选人**：从当前值日组（A 或 B）中，选择值日次数最少的 2 名学生
2. **分配职责**：交替分配「擦桌子」和「扫地」
3. **跳过非工作日**：自动跳过周末和节假日，支持调休工作日
4. **自动切换组**：排班完成后自动切换到另一组（A→B 或 B→A）

### 均衡度计算

```
均衡度 = 1 - (标准差 / 均值)
```

- 值域 [0, 1]，越接近 1 越均衡
- 分别计算 A 组和 B 组的均衡度

---

## 许可证

本项目仅供学习使用。
