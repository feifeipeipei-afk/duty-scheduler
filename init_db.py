#!/usr/bin/env python3
"""
值日排班管理系统 - 数据库初始化和演示数据脚本

⚠️ 本脚本会删除现有数据库并重建演示数据，仅用于首次体验或开发环境。
   正式使用的数据请勿运行；如需执行请加 --force 参数确认。

用法：
    python init_db.py --force
"""

import os
import sqlite3
import sys

from duty_scheduler.calendar_rules import SYSTEM_HOLIDAYS
from duty_scheduler.db import SCHEMA_STATEMENTS

DB_PATH = os.environ.get(
    'DUTY_SCHEDULER_DB',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'duty_scheduler.db'),
)


def init_test_data():
    """初始化演示数据（破坏性：删除旧库后重建）。"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print('已删除旧数据库')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    cur = conn.cursor()

    # 表结构与 duty_scheduler.db.SCHEMA_STATEMENTS 单一来源保持一致
    for statement in SCHEMA_STATEMENTS:
        cur.execute(statement)
    cur.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_duty_schedule_class_date
        ON duty_schedule (class_id, date)
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

    # 插入系统节假日（来自 duty_scheduler/data/holidays.json）
    inserted = 0
    for date_str, name in SYSTEM_HOLIDAYS.items():
        cur.execute(
            'INSERT OR IGNORE INTO holidays (date, name, is_system, semester_id) VALUES (?, ?, 1, ?)',
            [date_str, name, semester_id]
        )
        inserted += 1
    print(f'添加系统节假日: {inserted}天')

    conn.commit()
    conn.close()
    print('\n[OK] 演示数据初始化完成！')
    print('运行 python app.py 启动服务')


if __name__ == '__main__':
    if '--force' not in sys.argv:
        print('本脚本会删除现有数据库并写入演示数据！')
        print('确认执行请运行: python init_db.py --force')
        sys.exit(1)
    init_test_data()
