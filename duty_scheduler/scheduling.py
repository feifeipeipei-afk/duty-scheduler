"""核心业务逻辑：学期工具、审计日志、组别标签、数据健康检查。"""

from .db import get_db, query_db
from .helpers import now_iso


def get_active_semester():
    """获取当前激活的学期"""
    row = query_db('SELECT * FROM semesters WHERE is_active = 1 LIMIT 1', one=True)
    return dict(row) if row else None


def check_semester_overlap(start_date, end_date, exclude_id=None):
    """校验学期日期范围不与其他学期重叠，避免激活/排班时数据串学期。"""
    rows = query_db('SELECT id, name, start_date, end_date FROM semesters')
    for row in rows:
        if exclude_id is not None and row['id'] == exclude_id:
            continue
        if not (end_date < row['start_date'] or start_date > row['end_date']):
            raise ValueError(f'与学期“{row["name"]}”（{row["start_date"]} ~ {row["end_date"]}）的日期范围重叠')


def log_change(action_type, class_id=None, schedule_id=None, date=None,
               old_student1_id=None, old_student2_id=None,
               new_student1_id=None, new_student2_id=None, reason='',
               student_id=None, commit=True):
    """记录关键操作审计日志，方便追溯。事务内批量写入时传 commit=False。"""
    db = get_db()
    cur = db.execute(
        '''INSERT INTO change_logs
           (action_type, class_id, schedule_id, date, old_student1_id, old_student2_id,
            new_student1_id, new_student2_id, reason, student_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        [action_type, class_id, schedule_id, date, old_student1_id, old_student2_id,
         new_student1_id, new_student2_id, reason or '', student_id, now_iso()]
    )
    if commit:
        db.commit()
    return cur.lastrowid


def group_label(group_name):
    """组别显示标签：A=上半学期值日，B=下半学期值日。"""
    if group_name == 'A':
        return 'A 组（上半学期值日）'
    if group_name == 'B':
        return 'B 组（下半学期值日）'
    return str(group_name) if group_name else ''


def run_health_checks():
    issues = []
    active = get_active_semester()
    if not active:
        issues.append({'level': 'block', 'message': '还没有激活学期，请先激活一个学期', 'target': '/admin/semesters'})
    else:
        classes = query_db('SELECT * FROM classes WHERE semester_id = ?', [active['id']])
        if not classes:
            issues.append({'level': 'warn', 'message': '当前学期还没有班级', 'target': '/admin/classes'})
        for cls in classes:
            duplicates = query_db(
                '''SELECT name, COUNT(*) as cnt FROM students
                   WHERE class_id = ? AND is_active = 1
                   GROUP BY name HAVING cnt > 1''',
                [cls['id']]
            )
            for dup in duplicates:
                issues.append({'level': 'warn', 'class_id': cls['id'], 'message': f'{cls["name"]} 有 {dup["cnt"]} 个同名学生“{dup["name"]}”，学生端查询和提交会产生歧义，建议合并', 'target': '/admin/classes'})
        bad_records = query_db('''
            SELECT dr.id, c.name as class_name, dr.date FROM duty_records dr
            LEFT JOIN classes c ON dr.class_id = c.id
            LEFT JOIN semesters s ON c.semester_id = s.id
            WHERE s.id IS NULL OR dr.date < s.start_date OR dr.date > s.end_date
        ''')
        for row in bad_records:
            issues.append({'level': 'warn', 'record_id': row['id'], 'message': f'{row["class_name"] or "某班级"} 的值日记录 {row["date"]} 不在所属学期范围内', 'target': '/admin/records'})
    return issues
