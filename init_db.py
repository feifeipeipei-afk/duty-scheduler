#!/usr/bin/env python3
"""
值日记录管理系统 - 数据库初始化和演示数据脚本

⚠️ 本脚本会删除现有数据库并重建演示数据，仅用于首次体验或开发环境。
   正式使用的数据请勿运行；如需执行请加 --force 参数确认。

用法：
    python init_db.py --force
"""

import os
import sqlite3
import sys

from duty_scheduler.db import SCHEMA_STATEMENTS

DB_PATH = os.environ.get(
    'DUTY_SCHEDULER_DB',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'duty_scheduler.db'),
)

# 演示班级与学生：A 组=上半学期值日，B 组=下半学期值日
DEMO_CLASSES = [
    {
        'name': '高一一班',
        'groups': {
            'A': ['张伟', '李娜', '王芳', '刘洋', '陈静', '杨光'],
            'B': ['赵磊', '孙悦', '周涛', '吴佳'],
        },
    },
    {
        'name': '高一二班',
        'groups': {
            'A': ['王浩', '李想', '张倩', '刘畅', '黄敏', '徐静'],
            'B': ['杨帆', '朱琳', '胡斌', '林悦'],
        },
    },
]

# 演示值日记录：日期取学期内、不晚于今天的最近几个工作日（周一~周五），
# 部分学生已有记录、其余 0 次，便于查看"未值日名单"的演示效果
DEMO_RECORDS = [
    # (班级, 学生, 日期, 职责, 提交时间)
    ('高一一班', '张伟', '2026-09-07', '扫地', '2026-09-07T17:35:00'),
    ('高一一班', '王芳', '2026-09-07', '擦桌子', '2026-09-07T17:42:00'),
    ('高一一班', '李娜', '2026-09-09', '扫地', '2026-09-09T17:30:00'),
    ('高一一班', '刘洋', '2026-09-10', '扫地', '2026-09-10T17:38:00'),
    ('高一一班', '陈静', '2026-09-11', '擦桌子', '2026-09-11T17:25:00'),
    ('高一二班', '王浩', '2026-09-07', '扫地', '2026-09-07T17:40:00'),
    ('高一二班', '李想', '2026-09-08', '扫地', '2026-09-08T17:45:00'),
    ('高一二班', '张倩', '2026-09-08', '擦桌子', '2026-09-08T17:32:00'),
    ('高一二班', '黄敏', '2026-09-10', '擦桌子', '2026-09-10T17:28:00'),
    ('高一二班', '刘畅', '2026-09-11', '扫地', '2026-09-11T17:36:00'),
]


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
    cur.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_duty_records_student_date
        ON duty_records (student_id, date)
    ''')

    # 插入演示学期（日期覆盖"今天"附近，便于体验学生自主提交）
    cur.execute(
        'INSERT INTO semesters (name, start_date, end_date, is_active) VALUES (?, ?, ?, ?)',
        ['2026-2027 学年第一学期', '2026-09-01', '2027-01-31', 1]
    )
    semester_id = cur.lastrowid
    print(f'创建学期: 2026-2027 学年第一学期 (ID: {semester_id})')

    # 插入演示班级与学生，收集 id 供值日记录引用
    class_ids = {}
    student_ids = {}
    for demo_class in DEMO_CLASSES:
        # duty_weekday 已废弃不用，插入 1 兜底满足非空约束
        cur.execute(
            'INSERT INTO classes (name, semester_id, duty_weekday, current_group) VALUES (?, ?, ?, ?)',
            [demo_class['name'], semester_id, 1, 'A']
        )
        class_id = cur.lastrowid
        class_ids[demo_class['name']] = class_id
        print(f"创建班级: {demo_class['name']} (ID: {class_id})")

        for group_name in ('A', 'B'):
            names = demo_class['groups'][group_name]
            for name in names:
                cur.execute(
                    'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
                    [name, class_id, group_name]
                )
                student_ids[name] = cur.lastrowid
            print(f"添加{demo_class['name']}{group_name}组学生: {', '.join(names)}")

    # 插入演示值日记录
    for class_name, student_name, date, duty_type, submitted_at in DEMO_RECORDS:
        cur.execute(
            '''INSERT INTO duty_records (class_id, student_id, date, duty_type, submitted_at)
               VALUES (?, ?, ?, ?, ?)''',
            [class_ids[class_name], student_ids[student_name], date, duty_type, submitted_at]
        )
    print(f'添加值日记录: {len(DEMO_RECORDS)}条（其余学生未值日，可查看未值日名单）')

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
