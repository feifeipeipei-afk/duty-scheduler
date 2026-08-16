"""数据库层：连接管理、Schema 单一定义、初始化与迁移、查询助手。"""
import sqlite3

from flask import current_app, g

SCHEMA_STATEMENTS = (
    # 学期表
    '''CREATE TABLE IF NOT EXISTS semesters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        is_active INTEGER DEFAULT 0
    )''',
    # 班级表
    '''CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        semester_id INTEGER NOT NULL,
        duty_weekday INTEGER NOT NULL,
        current_group TEXT DEFAULT 'A',
        FOREIGN KEY (semester_id) REFERENCES semesters (id)
    )''',
    # 学生表
    '''CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        group_name TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (class_id) REFERENCES classes (id)
    )''',
    # 值日排班表
    '''CREATE TABLE IF NOT EXISTS duty_schedule (
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
    )''',
    # 请假记录表
    '''CREATE TABLE IF NOT EXISTS leave_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        reason TEXT,
        replacement_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students (id),
        FOREIGN KEY (replacement_id) REFERENCES students (id)
    )''',
    # 节假日表
    '''CREATE TABLE IF NOT EXISTS holidays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        is_system INTEGER DEFAULT 0,
        semester_id INTEGER,
        FOREIGN KEY (semester_id) REFERENCES semesters (id)
    )''',
    # 操作记录表：调班、请假、撤销、批量完成等都写入这里
    '''CREATE TABLE IF NOT EXISTS change_logs (
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
    )''',
)


def get_db():
    """获取当前请求的数据库连接。"""
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(error=None):
    """关闭数据库连接。"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """初始化数据库表结构（幂等）。"""
    db = get_db()
    for statement in SCHEMA_STATEMENTS:
        db.execute(statement)

    # 旧数据库平滑升级：补齐后续版本需要的列
    existing_cols = {
        row['name'] for row in db.execute('PRAGMA table_info(duty_schedule)').fetchall()
    }
    if 'published_at' not in existing_cols:
        db.execute('ALTER TABLE duty_schedule ADD COLUMN published_at TEXT')
    if 'updated_at' not in existing_cols:
        db.execute('ALTER TABLE duty_schedule ADD COLUMN updated_at TEXT')

    db.commit()
    migrate_db()


def migrate_db():
    """幂等迁移老数据库：清理重复排班并补齐唯一索引。"""
    db = get_db()
    # 同班级同日期的重复排班：保留最早一条，先解除其审计引用再删除
    db.execute('''
        DELETE FROM change_logs WHERE schedule_id IN (
            SELECT ds.id FROM duty_schedule ds
            WHERE ds.id NOT IN (SELECT MIN(id) FROM duty_schedule GROUP BY class_id, date)
        )
    ''')
    db.execute('''
        DELETE FROM duty_schedule
        WHERE id NOT IN (SELECT MIN(id) FROM duty_schedule GROUP BY class_id, date)
    ''')
    # 唯一索引防止并发发布/换日期产生重复排班
    db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_duty_schedule_class_date
        ON duty_schedule (class_id, date)
    ''')
    db.commit()


def query_db(query, args=(), one=False):
    """执行数据库查询。"""
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def insert_db(query, args=()):
    """执行数据库插入。"""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.lastrowid


def update_db(query, args=()):
    """执行数据库更新。"""
    db = get_db()
    cur = db.execute(query, args)
    db.commit()
    return cur.rowcount
