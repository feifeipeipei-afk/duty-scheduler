#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
值日排班管理系统 - 数据库初始化和测试数据脚本
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'duty_scheduler.db')


def init_test_data():
    """初始化测试数据"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print('已删除旧数据库')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 创建表结构
    cur.executescript('''
        CREATE TABLE semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 0
        );

        CREATE TABLE classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            semester_id INTEGER NOT NULL,
            duty_weekday INTEGER NOT NULL,
            current_group TEXT DEFAULT 'A',
            FOREIGN KEY (semester_id) REFERENCES semesters (id)
        );

        CREATE TABLE students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            class_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (class_id) REFERENCES classes (id)
        );

        CREATE TABLE duty_schedule (
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
            published_at TEXT,
            updated_at TEXT,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (student1_id) REFERENCES students (id),
            FOREIGN KEY (student2_id) REFERENCES students (id)
        );

        CREATE TABLE leave_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            reason TEXT,
            replacement_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students (id),
            FOREIGN KEY (replacement_id) REFERENCES students (id)
        );

        CREATE TABLE holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_system INTEGER DEFAULT 0,
            semester_id INTEGER,
            FOREIGN KEY (semester_id) REFERENCES semesters (id)
        );

        CREATE TABLE change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_type TEXT NOT NULL,
            class_id INTEGER,
            schedule_id INTEGER,
            date TEXT,
            old_student1_id INTEGER,
            old_student2_id INTEGER,
            new_student1_id INTEGER,
            new_student2_id INTEGER,
            reason TEXT,
            created_at TEXT NOT NULL,
            is_reverted INTEGER DEFAULT 0,
            FOREIGN KEY (class_id) REFERENCES classes (id),
            FOREIGN KEY (schedule_id) REFERENCES duty_schedule (id)
        );
    ''')

    # 插入测试学期
    cur.execute(
        'INSERT INTO semesters (name, start_date, end_date, is_active) VALUES (?, ?, ?, ?)',
        ['2025-2026学年第二学期', '2026-02-16', '2026-07-10', 1]
    )
    semester_id = cur.lastrowid
    print(f'创建学期: 2025-2026学年第二学期 (ID: {semester_id})')

    # 插入测试班级
    cur.execute(
        'INSERT INTO classes (name, semester_id, duty_weekday, current_group) VALUES (?, ?, ?, ?)',
        ['高一三班', semester_id, 1, 'A']
    )
    class1_id = cur.lastrowid
    print(f'创建班级: 高一三班 (ID: {class1_id})')

    cur.execute(
        'INSERT INTO classes (name, semester_id, duty_weekday, current_group) VALUES (?, ?, ?, ?)',
        ['高二一班', semester_id, 3, 'A']
    )
    class2_id = cur.lastrowid
    print(f'创建班级: 高二一班 (ID: {class2_id})')

    # 插入测试学生 - 高一三班A组
    a_names = ['张三', '李四', '王五', '赵六', '孙七', '周八', '吴九', '郑十']
    for name in a_names:
        cur.execute(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, class1_id, 'A']
        )
    print(f'添加A组学生: {", ".join(a_names)}')

    # 插入测试学生 - 高一三班B组
    b_names = ['钱十一', '陈十二', '林十三', '黄十四', '杨十五', '刘十六', '何十七', '马十八']
    for name in b_names:
        cur.execute(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, class1_id, 'B']
        )
    print(f'添加B组学生: {", ".join(b_names)}')

    # 插入测试学生 - 高二一班
    c_a_names = ['甲一', '乙二', '丙三', '丁四', '戊五', '己六']
    for name in c_a_names:
        cur.execute(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, class2_id, 'A']
        )

    c_b_names = ['庚七', '辛八', '壬九', '癸十', '子一', '丑二']
    for name in c_b_names:
        cur.execute(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, class2_id, 'B']
        )
    print(f'添加高二一班学生: A组{len(c_a_names)}人, B组{len(c_b_names)}人')

    # 插入系统节假日
    SYSTEM_HOLIDAYS = {
        '2026-04-04': '清明节', '2026-04-05': '清明节', '2026-04-06': '清明节',
        '2026-05-01': '劳动节', '2026-05-02': '劳动节', '2026-05-03': '劳动节',
        '2026-05-04': '劳动节', '2026-05-05': '劳动节',
        '2026-06-19': '端午节', '2026-06-20': '端午节', '2026-06-21': '端午节',
    }
    for date_str, name in SYSTEM_HOLIDAYS.items():
        cur.execute(
            'INSERT INTO holidays (date, name, is_system, semester_id) VALUES (?, ?, 1, ?)',
            [date_str, name, semester_id]
        )
    print(f'添加系统节假日: {len(SYSTEM_HOLIDAYS)}天')

    conn.commit()
    conn.close()
    print('\n[OK] 测试数据初始化完成！')
    print('运行 python app.py 启动服务')


if __name__ == '__main__':
    init_test_data()
