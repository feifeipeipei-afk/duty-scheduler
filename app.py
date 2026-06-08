#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
值日排班管理系统 - 后端主程序
技术栈: Python 3.12 + Flask + SQLite
"""

from flask import Flask, render_template, request, jsonify, g, session, redirect, url_for
# Flask 3.x 不再需要单独导入 JSONEncoder
import sqlite3
import os
from datetime import datetime, timedelta
import random
import json

# ==================== 应用配置 ====================

app = Flask(__name__)
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'duty_scheduler.db')
app.config['JSON_AS_ASCII'] = False
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 中国2025-2026法定节假日数据
SYSTEM_HOLIDAYS = {
    '2025-09-15': '中秋节',
    '2025-10-01': '国庆节', '2025-10-02': '国庆节', '2025-10-03': '国庆节',
    '2025-10-04': '国庆节', '2025-10-05': '国庆节', '2025-10-06': '国庆节', '2025-10-07': '国庆节',
    '2026-01-01': '元旦', '2026-01-02': '元旦', '2026-01-03': '元旦',
    '2026-01-19': '春节', '2026-01-20': '春节', '2026-01-21': '春节', '2026-01-22': '春节',
    '2026-01-23': '春节', '2026-01-24': '春节', '2026-01-25': '春节', '2026-01-26': '春节',
    '2026-02-09': '春节调休',
    '2026-04-04': '清明节', '2026-04-05': '清明节', '2026-04-06': '清明节',
    '2026-05-01': '劳动节', '2026-05-02': '劳动节', '2026-05-03': '劳动节',
    '2026-05-31': '端午节', '2026-06-01': '端午节', '2026-06-02': '端午节',
    '2026-10-01': '国庆节', '2026-10-02': '国庆节', '2026-10-03': '国庆节',
    '2026-10-04': '国庆节', '2026-10-05': '国庆节', '2026-10-06': '国庆节', '2026-10-07': '国庆节',
    '2026-10-25': '中秋节',
}

# 中国调休工作日（周末调整为上班日）
SYSTEM_WORKDAYS = {
    '2026-02-07': '春节调休上班',   # 周六
    '2026-02-21': '春节调休上班',   # 周六（可按实际调整）
    '2026-04-26': '劳动节调休上班', # 周六
    '2026-10-10': '国庆节调休上班', # 周六
}

# ==================== 数据库初始化 ====================

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row  # 使结果可以通过列名访问
    return g.db

@app.teardown_appcontext
def close_db(error):
    """关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库表结构"""
    db = get_db()
    
    # 创建学期表
    db.execute('''
        CREATE TABLE IF NOT EXISTS semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 0
        )
    ''')
    
    # 创建班级表
    db.execute('''
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            semester_id INTEGER NOT NULL,
            duty_weekday INTEGER NOT NULL,
            current_group TEXT DEFAULT 'A',
            FOREIGN KEY (semester_id) REFERENCES semesters (id)
        )
    ''')
    
    # 创建学生表
    db.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        )
    ''')
    
    # 创建值日排班表
    db.execute('''
        CREATE TABLE IF NOT EXISTS duty_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            student1_id INTEGER,
            student2_id INTEGER,
            duty1_type TEXT,
            duty2_type TEXT,
            status TEXT DEFAULT 'pending',
            original_student1_id INTEGER,
            original_student2_id INTEGER,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (student1_id) REFERENCES students (id),
            FOREIGN KEY (student2_id) REFERENCES students (id)
        )
    ''')
    
    # 创建请假记录表
    db.execute('''
        CREATE TABLE IF NOT EXISTS leave_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reason TEXT,
            replacement_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (replacement_id) REFERENCES students (id)
        )
    ''')
    
    # 创建节假日表
    db.execute('''
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_system INTEGER DEFAULT 0,
            semester_id INTEGER,
            FOREIGN KEY (semester_id) REFERENCES semesters (id)
        )
    ''')
    
    db.commit()

# ==================== 辅助函数 ====================

def query_db(query, args=(), one=False):
    """执行数据库查询"""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def insert_db(query, args=()):
    """执行数据库插入"""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid

def update_db(query, args=()):
    """执行数据库更新"""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.rowcount

def get_active_semester():
    """获取当前激活的学期"""
    row = query_db('SELECT * FROM semesters WHERE is_active = 1 LIMIT 1', one=True)
    return dict(row) if row else None

def cleanup_invalid_schedules(class_id):
    """清理引用了已删除学生的排班记录"""
    db = get_db()
    db.execute('''
        DELETE FROM duty_schedule 
        WHERE class_id = ? 
        AND (student1_id NOT IN (SELECT id FROM students WHERE is_active = 1)
             OR student2_id NOT IN (SELECT id FROM students WHERE is_active = 1))
    ''', [class_id])
    db.commit()

def is_workday(date_str):
    """判断某天是否为工作日（非周末且非节假日，支持调休工作日）"""
    # 检查是否为调休工作日（周末调整为上班）
    if date_str in SYSTEM_WORKDAYS:
        return True

    # 检查是否为周末
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    if date_obj.weekday() >= 5:  # 5=周六, 6=周日
        return False

    # 检查是否为节假日
    row = query_db('SELECT * FROM holidays WHERE date = ?', [date_str], one=True)
    if row:
        return False

    return True

def get_duty_count_map(class_id, group_name):
    """获取某班级某组的学生值日次数统计"""
    db = get_db()
    students = query_db(
        'SELECT id, name FROM students WHERE class_id = ? AND group_name = ? AND is_active = 1',
        [class_id, group_name]
    )
    
    count_map = {}
    for student in students:
        student_id = student['id']
        # 统计该学生的值日次数
        count = query_db(
            '''SELECT COUNT(*) as cnt FROM duty_schedule 
               WHERE (student1_id = ? OR student2_id = ?) AND status != 'cancelled' ''',
            [student_id, student_id],
            one=True
        )
        count_map[student_id] = count['cnt'] if count else 0
    
    return count_map

def calculate_balance(count_map):
    """计算均衡度：1 - (标准差 / 均值)，越接近1越均衡"""
    if not count_map:
        return 0
    
    values = list(count_map.values())
    if not values:
        return 0
    
    mean = sum(values) / len(values)
    if mean == 0:
        return 1
    
    # 计算标准差
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = variance ** 0.5
    
    balance = 1 - (std_dev / mean)
    return max(0, min(1, balance))  # 限制在0-1之间

def init_system_holidays(semester_id):
    """初始化系统内置中国法定节假日"""
    db = get_db()

    # 先删除该学期的旧系统节假日
    db.execute('DELETE FROM holidays WHERE semester_id = ? AND is_system = 1', [semester_id])

    # 查询学期信息（提到循环外，避免 N+1 查询）
    semester = query_db('SELECT * FROM semesters WHERE id = ?', [semester_id], one=True)
    if not semester:
        db.commit()
        return

    start_date = semester['start_date']
    end_date = semester['end_date']

    # 插入系统节假日
    for date_str, name in SYSTEM_HOLIDAYS.items():
        if start_date <= date_str <= end_date:
            db.execute(
                'INSERT OR IGNORE INTO holidays (date, name, is_system, semester_id) VALUES (?, ?, 1, ?)',
                [date_str, name, semester_id]
            )

    db.commit()

# ==================== 后台登录 ====================

def is_admin_logged_in():
    return session.get('admin_logged_in', False)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html')
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({'message': '登录成功'})
    return jsonify({'error': '密码错误'}), 401

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')

@app.before_request
def require_admin_login():
    """所有 /admin 路由需要登录（登录页本身和学生API除外）"""
    path = request.path
    # 放行：登录页、登出、静态资源、前台学生API、公开班级API
    if path.startswith('/admin/login') or path.startswith('/admin/logout'):
        return
    if path.startswith('/static/') or path == '/' or path.startswith('/api/student') or path.startswith('/api/classes'):
        return
    # 所有 /admin 下的页面和API都需要登录
    if path.startswith('/admin'):
        if not is_admin_logged_in():
            content_type = request.headers.get('Content-Type', '')
            is_json = 'application/json' in content_type or request.args.get('format') == 'json'
            if is_json:
                return jsonify({'error': '未登录'}), 401
            return redirect('/admin/login')

# ==================== 页面路由 ====================

@app.route('/')
def index():
    """前台首页（学生入口）"""
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    """后台管理首页"""
    return render_template('admin.html')

@app.route('/admin/semesters')
def semesters_page():
    """学期管理页 / 学期列表API"""
    content_type = request.headers.get('Content-Type', '')
    is_json = 'application/json' in content_type or request.args.get('format') == 'json'
    if is_json:
        semesters = query_db('SELECT * FROM semesters ORDER BY start_date DESC')
        return jsonify([dict(s) for s in semesters])
    return render_template('admin_semesters.html')

@app.route('/admin/classes')
def classes_page():
    """班级管理页 / 班级列表API"""
    # 前端AJAX请求返回JSON，直接访问返回HTML页面
    content_type = request.headers.get('Content-Type', '')
    is_json = 'application/json' in content_type or request.args.get('format') == 'json'
    if is_json:
        semester_id = request.args.get('semester_id')
        if not semester_id:
            semester = get_active_semester()
            if semester:
                semester_id = semester['id']
        if semester_id:
            classes = query_db(
                '''SELECT c.*, s.name as semester_name 
                   FROM classes c 
                   LEFT JOIN semesters s ON c.semester_id = s.id 
                   WHERE c.semester_id = ? 
                   ORDER BY c.name''',
                [semester_id]
            )
            return jsonify([dict(c) for c in classes])
        return jsonify([])
    return render_template('admin_classes.html')

@app.route('/admin/students')
def students_page():
    """学生管理页 / 学生列表API"""
    content_type = request.headers.get('Content-Type', '')
    is_json = 'application/json' in content_type or request.args.get('format') == 'json'
    if is_json:
        class_id = request.args.get('class_id')
        if not class_id:
            return jsonify({'error': '缺少class_id参数'}), 400
        students = query_db(
            '''SELECT s.*, c.name as class_name 
               FROM students s 
               LEFT JOIN classes c ON s.class_id = c.id 
               WHERE s.class_id = ? 
               ORDER BY s.group_name, s.name''',
            [class_id]
        )
        return jsonify([dict(s) for s in students])
    return render_template('admin_classes.html')

@app.route('/admin/schedule')
def schedule_page():
    """排班管理页 / 排班列表API"""
    content_type = request.headers.get('Content-Type', '')
    is_json = 'application/json' in content_type or request.args.get('format') == 'json'
    if is_json:
        class_id = request.args.get('class_id')
        year = request.args.get('year')
        month = request.args.get('month')
        if not class_id:
            return jsonify({'error': '缺少class_id参数'}), 400
        query = '''
            SELECT ds.*, 
                   s1.name as student1_name,
                   s2.name as student2_name,
                   c.name as class_name
            FROM duty_schedule ds
            LEFT JOIN students s1 ON ds.student1_id = s1.id
            LEFT JOIN students s2 ON ds.student2_id = s2.id
            LEFT JOIN classes c ON ds.class_id = c.id
            WHERE ds.class_id = ?
        '''
        params = [class_id]
        if year and month:
            month_str = f'{int(year):04d}-{int(month):02d}'
            query += " AND ds.date LIKE ?"
            params.append(f'{month_str}%')
        elif month:
            query += " AND ds.date LIKE ?"
            params.append(f'{month}%')
        query += " ORDER BY ds.date"
        schedule = query_db(query, params)
        return jsonify([dict(s) for s in schedule])
    return render_template('admin_schedule.html')

@app.route('/admin/holidays')
def holidays_page():
    """节假日管理页 / 节假日列表API"""
    content_type = request.headers.get('Content-Type', '')
    is_json = 'application/json' in content_type or request.args.get('format') == 'json'
    if is_json:
        semester_id = request.args.get('semester_id')
        query = 'SELECT * FROM holidays'
        params = []
        if semester_id:
            query += ' WHERE semester_id = ? OR is_system = 1'
            params.append(semester_id)
        query += ' ORDER BY date'
        holidays = query_db(query, params)
        return jsonify([dict(h) for h in holidays])
    return render_template('admin_holidays.html')

@app.route('/admin/stats')
def stats_page():
    """数据统计页"""
    return render_template('admin_stats.html')

# ==================== 后台管理 API ====================

# ---------- 学期管理 ----------

@app.route('/admin/semesters', methods=['POST'])
def create_semester():
    """创建学期"""
    data = request.get_json()
    name = data.get('name')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    if not all([name, start_date, end_date]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    semester_id = insert_db(
        'INSERT INTO semesters (name, start_date, end_date) VALUES (?, ?, ?)',
        [name, start_date, end_date]
    )
    
    return jsonify({'id': semester_id, 'message': '学期创建成功'})

@app.route('/admin/semesters/<int:semester_id>', methods=['PUT'])
def update_semester(semester_id):
    """更新学期"""
    data = request.get_json()
    name = data.get('name')
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    update_db(
        'UPDATE semesters SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
        [name, start_date, end_date, semester_id]
    )
    
    return jsonify({'message': '学期更新成功'})

@app.route('/admin/semesters/<int:semester_id>', methods=['DELETE'])
def delete_semester(semester_id):
    """删除学期"""
    # 检查是否有关联的班级
    classes = query_db('SELECT COUNT(*) as cnt FROM classes WHERE semester_id = ?', [semester_id], one=True)
    if classes and classes['cnt'] > 0:
        return jsonify({'error': '该学期下还有班级，无法删除'}), 400
    
    update_db('DELETE FROM semesters WHERE id = ?', [semester_id])
    return jsonify({'message': '学期删除成功'})

@app.route('/admin/semesters/<int:semester_id>/activate', methods=['POST'])
def activate_semester(semester_id):
    """激活学期（同时将其他学期设为非激活）"""
    db = get_db()
    db.execute('UPDATE semesters SET is_active = 0')
    db.execute('UPDATE semesters SET is_active = 1 WHERE id = ?', [semester_id])
    db.commit()
    return jsonify({'message': '学期激活成功'})

# ---------- 班级管理 ----------

@app.route('/admin/classes', methods=['POST'])
def create_class():
    """创建班级"""
    data = request.get_json()
    name = data.get('name')
    semester_id = data.get('semester_id')
    duty_weekday = data.get('duty_weekday') or data.get('duty_day', 1)
    
    if not name:
        return jsonify({'error': '缺少班级名称'}), 400
    
    # 如果没有指定学期，使用当前激活的学期
    if not semester_id:
        semester = get_active_semester()
        if semester:
            semester_id = semester['id']
        else:
            return jsonify({'error': '没有激活的学期，请先创建并激活学期'}), 400
    
    class_id = insert_db(
        'INSERT INTO classes (name, semester_id, duty_weekday) VALUES (?, ?, ?)',
        [name, semester_id, duty_weekday]
    )
    
    return jsonify({'id': class_id, 'message': '班级创建成功'})

@app.route('/admin/classes/<int:class_id>', methods=['PUT'])
def update_class(class_id):
    """更新班级"""
    data = request.get_json()
    name = data.get('name')
    duty_weekday = data.get('duty_weekday')
    
    update_db(
        'UPDATE classes SET name = ?, duty_weekday = ? WHERE id = ?',
        [name, duty_weekday, class_id]
    )
    
    return jsonify({'message': '班级更新成功'})

@app.route('/admin/classes/<int:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """删除班级（级联删除学生、排班、请假记录）"""
    db = get_db()
    # 先删除该班级的排班记录
    db.execute('DELETE FROM duty_schedule WHERE class_id = ?', [class_id])
    # 删除该班级学生的请假记录
    db.execute('''DELETE FROM leave_records WHERE student_id IN 
                  (SELECT id FROM students WHERE class_id = ?)''', [class_id])
    # 删除该班级的学生
    db.execute('DELETE FROM students WHERE class_id = ?', [class_id])
    # 删除班级
    db.execute('DELETE FROM classes WHERE id = ?', [class_id])
    db.commit()
    return jsonify({'message': '班级及相关数据已全部删除'})

@app.route('/admin/classes/<int:class_id>/group', methods=['PUT'])
def switch_group(class_id):
    """切换当前值日组"""
    data = request.get_json()
    group_name = data.get('group_name')
    
    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400
    
    update_db(
        'UPDATE classes SET current_group = ? WHERE id = ?',
        [group_name, class_id]
    )
    
    return jsonify({'message': f'已切换到{group_name}组'})

@app.route('/admin/classes/<int:class_id>/students', methods=['GET'])
def get_class_students(class_id):
    """获取班级学生列表（前端兼容路由）"""
    students = query_db(
        '''SELECT s.*, c.name as class_name 
           FROM students s 
           LEFT JOIN classes c ON s.class_id = c.id 
           WHERE s.class_id = ? 
           ORDER BY s.group_name, s.name''',
        [class_id]
    )
    return jsonify([dict(s) for s in students])

@app.route('/admin/classes/<int:class_id>/switch-group', methods=['POST'])
def switch_group_post(class_id):
    """切换当前值日组（POST兼容，支持自动切换）"""
    data = request.get_json(silent=True) or {}
    group_name = data.get('group_name') or data.get('group')
    
    if not group_name:
        # 自动切换：A→B, B→A
        cls = query_db('SELECT current_group FROM classes WHERE id = ?', [class_id], one=True)
        if not cls:
            return jsonify({'error': '班级不存在'}), 404
        group_name = 'B' if cls['current_group'] == 'A' else 'A'
    
    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400
    
    update_db(
        'UPDATE classes SET current_group = ? WHERE id = ?',
        [group_name, class_id]
    )
    return jsonify({'message': f'已切换到{group_name}组'})

# ---------- 学生管理 ----------

@app.route('/admin/students', methods=['POST'])
def create_student():
    """添加学生"""
    data = request.get_json()
    name = data.get('name')
    class_id = data.get('class_id')
    group_name = data.get('group_name', 'A')
    
    if not all([name, class_id]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400
    
    student_id = insert_db(
        'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
        [name, class_id, group_name]
    )
    
    return jsonify({'id': student_id, 'message': '学生添加成功'})

@app.route('/admin/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    """删除学生（软删除：标记为非活跃，并清理引用该学生的排班记录）"""
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    # 软删除：标记为非活跃
    update_db('UPDATE students SET is_active = 0 WHERE id = ?', [student_id])
    # 清理引用了该学生的排班记录
    cleanup_invalid_schedules(student['class_id'])
    return jsonify({'message': '学生删除成功'})

@app.route('/admin/students/<int:student_id>/group', methods=['PUT'])
def change_student_group(student_id):
    """修改学生组别（后台手动调整）"""
    data = request.get_json()
    group_name = data.get('group_name')
    
    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400
    
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    update_db('UPDATE students SET group_name = ? WHERE id = ?', [group_name, student_id])
    label = '上半学期' if group_name == 'A' else '下半学期'
    return jsonify({'message': f'已将 {student["name"]} 调整到{label}值日'})

@app.route('/admin/students/batch', methods=['POST'])
def batch_create_students():
    """批量添加学生"""
    data = request.get_json()
    names = data.get('names', [])
    class_id = data.get('class_id')
    group_name = data.get('group_name', 'A')
    
    if not names or not class_id:
        return jsonify({'error': '缺少必要参数'}), 400
    
    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400
    
    db = get_db()
    count = 0
    for name in names:
        name = name.strip()
        if name:
            db.execute(
                'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
                [name, class_id, group_name]
            )
            count += 1
    
    db.commit()
    return jsonify({'message': f'成功添加{count}名学生'})

# ---------- 排班管理 ----------

@app.route('/admin/schedule/list', methods=['GET'])
def get_schedule():
    """获取排班表"""
    class_id = request.args.get('class_id')
    month = request.args.get('month')  # 格式: YYYY-MM
    
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    
    query = '''
        SELECT ds.*,
               s1.name as student1_name, s1.group_name as student1_group,
               s2.name as student2_name, s2.group_name as student2_group,
               c.name as class_name
        FROM duty_schedule ds
        LEFT JOIN students s1 ON ds.student1_id = s1.id
        LEFT JOIN students s2 ON ds.student2_id = s2.id
        LEFT JOIN classes c ON ds.class_id = c.id
        WHERE ds.class_id = ?
    '''
    params = [class_id]
    
    if month:
        query += " AND ds.date LIKE ?"
        params.append(f'{month}%')
    
    query += " ORDER BY ds.date"
    
    schedule = query_db(query, params)
    return jsonify([dict(s) for s in schedule])

@app.route('/admin/schedule/duty', methods=['GET'])
def get_schedule_duty():
    """获取某天某班的值日详情"""
    class_id = request.args.get('class_id')
    date = request.args.get('date')
    
    if not all([class_id, date]):
        return jsonify({'error': '缺少参数'}), 400
    
    schedule = query_db(
        '''SELECT ds.*, 
                  s1.name as student1_name,
                  s2.name as student2_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           WHERE ds.class_id = ? AND ds.date = ?''',
        [class_id, date],
        one=True
    )
    
    if schedule:
        return jsonify(dict(schedule))
    return jsonify(None)

@app.route('/admin/schedule/generate', methods=['POST'])
def generate_schedule_compat():
    """生成排班（前端兼容路由，支持year+month参数）"""
    data = request.get_json()
    class_id = data.get('class_id')
    
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    
    # 获取班级信息
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404
    
    # 获取学期信息
    semester = query_db('SELECT * FROM semesters WHERE id = ?', [class_info['semester_id']], one=True)
    if not semester:
        return jsonify({'error': '学期不存在'}), 404
    
    current_group = class_info['current_group']
    duty_weekday = class_info['duty_weekday']
    
    # 获取该组所有活跃学生
    students = query_db(
        'SELECT * FROM students WHERE class_id = ? AND group_name = ? AND is_active = 1',
        [class_id, current_group]
    )
    
    if len(students) < 2:
        return jsonify({'error': f'{current_group}组至少需要2名学生才能排班'}), 400
    
    # 确定日期范围
    year = data.get('year')
    month = data.get('month')
    sem_start = datetime.strptime(semester['start_date'], '%Y-%m-%d')
    sem_end = datetime.strptime(semester['end_date'], '%Y-%m-%d')
    
    if year and month:
        start_date = datetime(int(year), int(month), 1)
        if int(month) == 12:
            end_date = datetime(int(year), 12, 31)
        else:
            end_date = datetime(int(year), int(month) + 1, 1) - timedelta(days=1)
    else:
        start_date = sem_start
        end_date = sem_end
    
    # 封顶到学期范围
    if start_date < sem_start:
        start_date = sem_start
    if end_date > sem_end:
        end_date = sem_end
    
    # 清理无效排班记录（引用已删除学生 或 超出学期范围）
    db = get_db()
    db.execute('''
        DELETE FROM duty_schedule 
        WHERE class_id = ? AND (
            date < ? OR date > ?
            OR student1_id NOT IN (SELECT id FROM students WHERE is_active = 1)
            OR student2_id NOT IN (SELECT id FROM students WHERE is_active = 1)
        )
    ''', [class_id, sem_start.strftime('%Y-%m-%d'), sem_end.strftime('%Y-%m-%d')])
    db.commit()
    
    # 生成值日日
    duty_dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() == duty_weekday - 1:
            date_str = current.strftime('%Y-%m-%d')
            if is_workday(date_str):
                duty_dates.append(date_str)
        current += timedelta(days=1)
    
    if not duty_dates:
        return jsonify({'error': '该时间段内没有可用的值日日期'}), 400
    
    count_map = get_duty_count_map(class_id, current_group)
    db = get_db()
    student_list = [dict(s) for s in students]
    student_list.sort(key=lambda x: count_map.get(x['id'], 0))
    last_duty_type = '擦桌子'
    
    for date_str in duty_dates:
        existing = query_db(
            'SELECT * FROM duty_schedule WHERE class_id = ? AND date = ?',
            [class_id, date_str],
            one=True
        )
        if existing:
            continue
        
        min_count = min(count_map.get(s['id'], 0) for s in student_list)
        available = [s for s in student_list if count_map.get(s['id'], 0) == min_count]
        
        if len(available) < 2:
            student_list.sort(key=lambda x: count_map.get(x['id'], 0))
            selected = student_list[:2]
        else:
            selected = random.sample(available, 2)
        
        if last_duty_type == '擦桌子':
            duty1_type = '扫地'
            duty2_type = '擦桌子'
        else:
            duty1_type = '擦桌子'
            duty2_type = '扫地'
        
        last_duty_type = duty1_type
        
        db.execute(
            '''INSERT INTO duty_schedule 
               (class_id, date, student1_id, student2_id, duty1_type, duty2_type, status) 
               VALUES (?, ?, ?, ?, ?, ?, 'pending')''',
            [class_id, date_str, selected[0]['id'], selected[1]['id'], duty1_type, duty2_type]
        )
        
        count_map[selected[0]['id']] = count_map.get(selected[0]['id'], 0) + 1
        count_map[selected[1]['id']] = count_map.get(selected[1]['id'], 0) + 1
        student_list.sort(key=lambda x: count_map.get(x['id'], 0))
    
    db.commit()
    
    new_group = 'B' if current_group == 'A' else 'A'
    update_db('UPDATE classes SET current_group = ? WHERE id = ?', [new_group, class_id])
    
    return jsonify({'message': f'排班生成成功，共生成{len(duty_dates)}条记录'})

@app.route('/admin/schedule/swap', methods=['POST'])
def swap_schedule():
    """调班（换人）- 替换单个学生"""
    data = request.get_json()
    schedule_id = data.get('schedule_id')
    new_student1_id = data.get('new_student1_id')
    new_student2_id = data.get('new_student2_id')
    
    if not schedule_id:
        return jsonify({'error': '缺少schedule_id'}), 400
    
    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [schedule_id], one=True)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404
    
    if new_student1_id:
        update_db(
            'UPDATE duty_schedule SET student1_id = ?, original_student1_id = ? WHERE id = ?',
            [new_student1_id, schedule['student1_id'], schedule_id]
        )
    if new_student2_id:
        update_db(
            'UPDATE duty_schedule SET student2_id = ?, original_student2_id = ? WHERE id = ?',
            [new_student2_id, schedule['student2_id'], schedule_id]
        )
    
    return jsonify({'message': '调班成功'})

@app.route('/admin/schedule/swap-between', methods=['POST'])
def swap_between():
    """原子交换两个排班位置的学生"""
    data = request.get_json()
    s1_id = data.get('schedule1_id')
    s1_slot = data.get('slot1')  # 0=student1, 1=student2
    s2_id = data.get('schedule2_id')
    s2_slot = data.get('slot2')
    
    if not all([s1_id is not None, s1_slot is not None, s2_id is not None, s2_slot is not None]):
        return jsonify({'error': '缺少参数'}), 400
    
    s1 = query_db('SELECT * FROM duty_schedule WHERE id = ?', [s1_id], one=True)
    s2 = query_db('SELECT * FROM duty_schedule WHERE id = ?', [s2_id], one=True)
    if not s1 or not s2:
        return jsonify({'error': '排班记录不存在'}), 404
    
    # 使用安全的白名单列名（避免 f-string 拼接 SQL 列名）
    SAFE_FIELDS = {
        0: ('student1_id', 'original_student1_id'),
        1: ('student2_id', 'original_student2_id'),
    }
    if s1_slot not in SAFE_FIELDS or s2_slot not in SAFE_FIELDS:
        return jsonify({'error': 'slot 参数无效'}), 400

    stu_col1, orig_col1 = SAFE_FIELDS[s1_slot]
    stu_col2, orig_col2 = SAFE_FIELDS[s2_slot]
    val1 = s1[stu_col1]
    val2 = s2[stu_col2]

    if val1 == val2:
        return jsonify({'message': '同一个学生，无需调换'})

    db = get_db()
    # 仅在原始学生未被记录时才写入 original 字段，避免多次调班覆盖原始信息
    orig1_val = s1[orig_col1] if s1[orig_col1] else val1
    orig2_val = s2[orig_col2] if s2[orig_col2] else val2

    db.execute(
        f'UPDATE duty_schedule SET {stu_col1} = ?, {orig_col1} = ? WHERE id = ?',
        [val2, orig1_val, s1_id]
    )
    db.execute(
        f'UPDATE duty_schedule SET {stu_col2} = ?, {orig_col2} = ? WHERE id = ?',
        [val1, orig2_val, s2_id]
    )
    db.commit()

    return jsonify({'message': '调换成功'})

@app.route('/admin/schedule/swap-records', methods=['GET'])
def get_swap_records():
    """获取调班记录"""
    class_id = request.args.get('class_id')
    
    query = '''SELECT ds.date, ds.id as schedule_id, ds.class_id,
                  s1.name as student1_name, s2.name as student2_name,
                  os1.name as original_student1_name, os2.name as original_student2_name,
                  c.name as class_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           LEFT JOIN students os1 ON ds.original_student1_id = os1.id
           LEFT JOIN students os2 ON ds.original_student2_id = os2.id
           LEFT JOIN classes c ON ds.class_id = c.id
           WHERE (ds.original_student1_id IS NOT NULL OR ds.original_student2_id IS NOT NULL)'''
    params = []
    
    if class_id:
        query += ' AND ds.class_id = ?'
        params.append(class_id)
    
    query += ' ORDER BY ds.date DESC'
    
    records = query_db(query, params)
    return jsonify([dict(r) for r in records])

@app.route('/admin/schedule/swap-records/<int:record_id>', methods=['DELETE'])
def delete_swap_record(record_id):
    """撤销调班记录（恢复原始学生）"""
    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [record_id], one=True)
    if not schedule:
        return jsonify({'error': '记录不存在'}), 404
    
    if schedule['original_student1_id']:
        update_db(
            'UPDATE duty_schedule SET student1_id = original_student1_id, original_student1_id = NULL WHERE id = ?',
            [record_id]
        )
    if schedule['original_student2_id']:
        update_db(
            'UPDATE duty_schedule SET student2_id = original_student2_id, original_student2_id = NULL WHERE id = ?',
            [record_id]
        )
    
    return jsonify({'message': '调班已撤销'})

@app.route('/admin/schedule/<int:schedule_id>/swap-date', methods=['PUT'])
def swap_schedule_date(schedule_id):
    """换课（调整某天值日日期）"""
    data = request.get_json()
    new_date = data.get('new_date')
    
    if not new_date:
        return jsonify({'error': '缺少new_date参数'}), 400
    
    # 检查新日期是否已有排班
    existing = query_db(
        'SELECT * FROM duty_schedule WHERE class_id = (SELECT class_id FROM duty_schedule WHERE id = ?) AND date = ?',
        [schedule_id, new_date],
        one=True
    )
    if existing:
        return jsonify({'error': '该日期已有排班'}), 400
    
    # 检查新日期是否为工作日
    if not is_workday(new_date):
        return jsonify({'error': '该日期为非工作日或节假日'}), 400
    
    update_db(
        'UPDATE duty_schedule SET date = ? WHERE id = ?',
        [new_date, schedule_id]
    )
    
    return jsonify({'message': '日期调整成功'})

@app.route('/admin/leave', methods=['POST'])
def create_leave():
    """请假操作（自动从同组选人补上）"""
    data = request.get_json()
    student_id = data.get('student_id')
    date = data.get('date')
    reason = data.get('reason', '')
    
    if not all([student_id, date]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 获取请假学生信息
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    # 找到该日期对应的排班记录
    schedule = query_db(
        '''SELECT * FROM duty_schedule 
           WHERE class_id = ? AND date = ? AND (student1_id = ? OR student2_id = ?)''',
        [student['class_id'], date, student_id, student_id],
        one=True
    )
    
    if not schedule:
        return jsonify({'error': '该日期没有该学生的值日安排'}), 404
    
    if schedule['status'] == 'cancelled':
        return jsonify({'error': '该排班已取消'}), 400
    
    # 获取同组的所有活跃学生
    same_group_students = query_db(
        'SELECT * FROM students WHERE class_id = ? AND group_name = ? AND is_active = 1 AND id != ?',
        [student['class_id'], student['group_name'], student_id]
    )
    
    if not same_group_students:
        return jsonify({'error': '同组没有其他学生可以替补'}), 400
    
    # 找出值日次数最少且当天未排班的学生
    best_replacement = None
    min_duty_count = float('inf')
    
    for candidate in same_group_students:
        candidate_id = candidate['id']
        
        # 检查该候选人当天是否已有排班
        existing = query_db(
            '''SELECT * FROM duty_schedule 
               WHERE date = ? AND (student1_id = ? OR student2_id = ?) AND status != 'cancelled' ''',
            [date, candidate_id, candidate_id],
            one=True
        )
        
        if existing:
            continue  # 跳过当天已有排班的学生
        
        # 统计该候选人的值日次数
        count = query_db(
            '''SELECT COUNT(*) as cnt FROM duty_schedule 
               WHERE (student1_id = ? OR student2_id = ?) AND status != 'cancelled' ''',
            [candidate_id, candidate_id],
            one=True
        )
        duty_count = count['cnt'] if count else 0
        
        if duty_count < min_duty_count:
            min_duty_count = duty_count
            best_replacement = candidate
    
    if not best_replacement:
        return jsonify({'error': '没有合适的替补学生'}), 400
    
    # 更新排班记录
    replacement_id = best_replacement['id']
    
    if schedule['student1_id'] == student_id:
        # 请假学生是student1
        update_db(
            '''UPDATE duty_schedule 
               SET student1_id = ?, original_student1_id = ? 
               WHERE id = ?''',
            [replacement_id, student_id, schedule['id']]
        )
    else:
        # 请假学生是student2
        update_db(
            '''UPDATE duty_schedule 
               SET student2_id = ?, original_student2_id = ? 
               WHERE id = ?''',
            [replacement_id, student_id, schedule['id']]
        )
    
    # 创建请假记录
    insert_db(
        '''INSERT INTO leave_records (student_id, date, reason, replacement_id, created_at) 
           VALUES (?, ?, ?, ?, ?)''',
        [student_id, date, reason, replacement_id, datetime.now().isoformat()]
    )
    
    return jsonify({
        'message': '请假成功',
        'replacement': dict(best_replacement)
    })

@app.route('/admin/schedule/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """删除单条排班记录"""
    update_db('DELETE FROM duty_schedule WHERE id = ?', [schedule_id])
    return jsonify({'message': '已删除'})

@app.route('/admin/schedule/<int:schedule_id>/complete', methods=['PUT'])
def complete_schedule(schedule_id):
    """标记值日完成"""
    update_db(
        'UPDATE duty_schedule SET status = "completed" WHERE id = ?',
        [schedule_id]
    )
    return jsonify({'message': '值日已标记为完成'})

# ---------- 节假日管理 ----------

@app.route('/admin/holidays', methods=['POST'])
def create_holiday():
    """添加自定义假期"""
    data = request.get_json()
    date = data.get('date')
    name = data.get('name')
    semester_id = data.get('semester_id')
    
    if not all([date, name, semester_id]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        holiday_id = insert_db(
            'INSERT INTO holidays (date, name, is_system, semester_id) VALUES (?, ?, 0, ?)',
            [date, name, semester_id]
        )
        return jsonify({'id': holiday_id, 'message': '假期添加成功'})
    except sqlite3.IntegrityError:
        return jsonify({'error': '该日期已是假期'}), 400

@app.route('/admin/holidays/<int:holiday_id>', methods=['DELETE'])
def delete_holiday(holiday_id):
    """删除自定义假期"""
    # 只能删除自定义假期，不能删除系统假期
    holiday = query_db('SELECT * FROM holidays WHERE id = ?', [holiday_id], one=True)
    if not holiday:
        return jsonify({'error': '假期不存在'}), 404
    
    if holiday['is_system']:
        return jsonify({'error': '不能删除系统内置假期'}), 400
    
    update_db('DELETE FROM holidays WHERE id = ?', [holiday_id])
    return jsonify({'message': '假期删除成功'})

@app.route('/admin/holidays/init-system', methods=['POST'])
def init_holidays():
    """初始化系统内置中国法定节假日"""
    data = request.get_json()
    semester_id = data.get('semester_id')
    
    if not semester_id:
        return jsonify({'error': '缺少semester_id参数'}), 400
    
    init_system_holidays(semester_id)
    return jsonify({'message': '系统节假日初始化成功'})

# ---------- 数据统计 ----------

@app.route('/admin/stats/quick', methods=['GET'])
def get_quick_stats():
    """获取快速统计数据"""
    semester = get_active_semester()
    if not semester:
        return jsonify({'class_count': 0, 'student_count': 0, 'schedule_count': 0})
    
    class_count = query_db(
        'SELECT COUNT(*) as cnt FROM classes WHERE semester_id = ?',
        [semester['id']], one=True
    )
    student_count = query_db(
        '''SELECT COUNT(*) as cnt FROM students s 
           LEFT JOIN classes c ON s.class_id = c.id 
           WHERE c.semester_id = ? AND s.is_active = 1''',
        [semester['id']], one=True
    )
    
    # 本月排班数
    now = datetime.now()
    month_str = now.strftime('%Y-%m')
    schedule_count = query_db(
        '''SELECT COUNT(*) as cnt FROM duty_schedule ds
           LEFT JOIN classes c ON ds.class_id = c.id
           WHERE c.semester_id = ? AND ds.date LIKE ?''',
        [semester['id'], f'{month_str}%'], one=True
    )
    
    return jsonify({
        'class_count': class_count['cnt'] if class_count else 0,
        'student_count': student_count['cnt'] if student_count else 0,
        'schedule_count': schedule_count['cnt'] if schedule_count else 0
    })

@app.route('/admin/stats/summary', methods=['GET'])
def get_stats_summary():
    """获取班级统计摘要"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404
    
    # 学生数
    student_count = query_db(
        'SELECT COUNT(*) as cnt FROM students WHERE class_id = ? AND is_active = 1',
        [class_id], one=True
    )
    
    # 排班总数
    total_schedule = query_db(
        'SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status != "cancelled"',
        [class_id], one=True
    )
    
    # 已完成数
    completed = query_db(
        'SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status = "completed"',
        [class_id], one=True
    )
    
    # 均衡度
    students = query_db(
        '''SELECT s.id, s.group_name,
                  (SELECT COUNT(*) FROM duty_schedule 
                   WHERE (student1_id = s.id OR student2_id = s.id) AND status != 'cancelled') as duty_count
           FROM students s WHERE s.class_id = ? AND s.is_active = 1''',
        [class_id]
    )
    
    group_a = {s['id']: s['duty_count'] for s in students if s['group_name'] == 'A'}
    group_b = {s['id']: s['duty_count'] for s in students if s['group_name'] == 'B'}
    
    return jsonify({
        'class_name': class_info['name'],
        'student_count': student_count['cnt'] if student_count else 0,
        'total_schedule': total_schedule['cnt'] if total_schedule else 0,
        'completed_count': completed['cnt'] if completed else 0,
        'group_a_balance': round(calculate_balance(group_a), 2),
        'group_b_balance': round(calculate_balance(group_b), 2)
    })

@app.route('/admin/stats/duty-count', methods=['GET'])
def get_duty_count():
    """获取每人值日次数统计"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    
    students = query_db(
        '''SELECT s.id, s.name, s.group_name,
                  (SELECT COUNT(*) FROM duty_schedule 
                   WHERE (student1_id = s.id OR student2_id = s.id) AND status != 'cancelled') as duty_count
           FROM students s WHERE s.class_id = ? AND s.is_active = 1
           ORDER BY s.group_name, duty_count DESC''',
        [class_id]
    )
    
    return jsonify([dict(s) for s in students])

@app.route('/admin/stats/heatmap', methods=['GET'])
def get_heatmap():
    """获取日历热力图数据"""
    class_id = request.args.get('class_id')
    year = request.args.get('year', datetime.now().year)
    
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    
    # 获取该年所有排班
    schedules = query_db(
        '''SELECT ds.date, ds.status,
                  s1.name as student1_name, s2.name as student2_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           WHERE ds.class_id = ? AND ds.date LIKE ?
           ORDER BY ds.date''',
        [class_id, f'{year}%']
    )
    
    # 构建按月统计
    months = {}
    for s in schedules:
        month = s['date'][:7]  # YYYY-MM
        if month not in months:
            months[month] = 0
        months[month] += 1
    
    return jsonify({
        'year': int(year),
        'months': [{'month': m, 'count': c} for m, c in sorted(months.items())],
        'days': [{'date': s['date'], 'student1': s['student1_name'], 'student2': s['student2_name'], 'status': s['status']} for s in schedules]
    })

@app.route('/admin/stats/class/<int:class_id>', methods=['GET'])
def get_class_stats(class_id):
    """获取班级统计（每人值日次数，均衡度等）"""
    # 获取班级信息
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404
    
    # 获取所有学生的值日次数
    students = query_db(
        '''SELECT s.*, 
                  (SELECT COUNT(*) FROM duty_schedule 
                   WHERE (student1_id = s.id OR student2_id = s.id) AND status != 'cancelled') as duty_count
           FROM students s
           WHERE s.class_id = ? AND s.is_active = 1
           ORDER BY s.group_name, duty_count''',
        [class_id]
    )
    
    student_stats = [dict(s) for s in students]
    
    # 计算A组和B组的均衡度
    group_a_students = [s for s in student_stats if s['group_name'] == 'A']
    group_b_students = [s for s in student_stats if s['group_name'] == 'B']
    
    group_a_balance = calculate_balance({s['id']: s['duty_count'] for s in group_a_students})
    group_b_balance = calculate_balance({s['id']: s['duty_count'] for s in group_b_students})
    
    # 统计总排班数
    total_schedule = query_db(
        'SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status != "cancelled"',
        [class_id],
        one=True
    )
    
    return jsonify({
        'class_name': class_info['name'],
        'student_stats': student_stats,
        'group_a_balance': round(group_a_balance, 2),
        'group_b_balance': round(group_b_balance, 2),
        'total_schedule': total_schedule['cnt'] if total_schedule else 0
    })

@app.route('/admin/stats/student/<int:student_id>', methods=['GET'])
def get_student_stats(student_id):
    """获取学生详细值日记录"""
    # 获取学生信息
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    
    # 获取该学生的值日记录
    records = query_db(
        '''SELECT ds.*, 
                  c.name as class_name
           FROM duty_schedule ds
           LEFT JOIN classes c ON ds.class_id = c.id
           WHERE (ds.student1_id = ? OR ds.student2_id = ?) AND ds.status != 'cancelled'
           ORDER BY ds.date DESC''',
        [student_id, student_id]
    )
    
    # 统计各类数据
    total_count = len(records)
    completed_count = sum(1 for r in records if r['status'] == 'completed')
    pending_count = sum(1 for r in records if r['status'] == 'pending')
    
    # 统计各类职责次数
    wipe_table_count = sum(1 for r in records if 
                          (r['student1_id'] == student_id and r['duty1_type'] == '擦桌子') or
                          (r['student2_id'] == student_id and r['duty2_type'] == '擦桌子'))
    sweep_floor_count = sum(1 for r in records if 
                           (r['student1_id'] == student_id and r['duty1_type'] == '扫地') or
                           (r['student2_id'] == student_id and r['duty2_type'] == '扫地'))
    
    return jsonify({
        'student': dict(student),
        'records': [dict(r) for r in records],
        'stats': {
            'total_count': total_count,
            'completed_count': completed_count,
            'pending_count': pending_count,
            'wipe_table_count': wipe_table_count,
            'sweep_floor_count': sweep_floor_count
        }
    })

# ==================== 前台学生 API ====================

@app.route('/api/classes', methods=['GET'])
def get_public_classes():
    """获取班级列表（公开接口，供学生端使用）"""
    semester = get_active_semester()
    if not semester:
        return jsonify([])
    classes = query_db(
        'SELECT id, name FROM classes WHERE semester_id = ? ORDER BY name',
        [semester['id']]
    )
    return jsonify([dict(c) for c in classes])

@app.route('/api/student/schedule', methods=['GET'])
def get_student_schedule():
    """学生查看自己的值日安排（支持首次自动注册）"""
    class_id = request.args.get('class_id')
    name = request.args.get('name')
    group = request.args.get('group', 'A')  # A=上半学期, B=下半学期
    
    if not all([class_id, name]):
        return jsonify({'error': '缺少必要参数'}), 400

    # 基本输入验证
    name = name.strip()
    if not name or len(name) > 20:
        return jsonify({'error': '姓名长度应为1-20个字符'}), 400

    if group not in ['A', 'B']:
        group = 'A'

    # 验证班级是否存在
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [int(class_id)], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404

    # 查找学生
    student = query_db(
        'SELECT * FROM students WHERE class_id = ? AND name = ? AND is_active = 1',
        [int(class_id), name],
        one=True
    )

    # 首次查询：自动注册
    if not student:
        student_id = insert_db(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, int(class_id), group]
        )
        student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    
    # 获取该学生的值日安排
    records = query_db(
        '''SELECT ds.*, 
                  s1.name as student1_name,
                  s2.name as student2_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           WHERE (ds.student1_id = ? OR ds.student2_id = ?) AND ds.status != 'cancelled'
           ORDER BY ds.date''',
        [student['id'], student['id']]
    )
    
    # 分离已完成和未完成
    completed = [dict(r) for r in records if r['status'] == 'completed']
    pending = [dict(r) for r in records if r['status'] == 'pending']
    
    return jsonify({
        'student': dict(student),
        'completed': completed,
        'pending': pending
    })

# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '资源不存在'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': '服务器内部错误'}), 500

# ==================== 主程序入口 ====================

if __name__ == '__main__':
    # 初始化数据库
    with app.app_context():
        init_db()
    
    # 启动Flask应用
    app.run(host='0.0.0.0', port=5001, debug=True)
