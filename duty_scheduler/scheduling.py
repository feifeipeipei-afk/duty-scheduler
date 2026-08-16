"""排班核心业务逻辑：预览生成、发布、替补查找、均衡度、健康检查。"""
from datetime import datetime, timedelta

from .calendar_rules import SYSTEM_HOLIDAYS, is_workday
from .db import get_db, query_db
from .helpers import now_iso, parse_int, validate_date, weekday_name


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


def get_duty_count_map(class_id, group_name):
    """获取某班级某组的学生值日次数统计"""
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


def find_best_replacement(class_id, group_name, date, exclude_ids=None):
    """找同组、当天未排班、值日次数少的替补学生。"""
    exclude_ids = set(exclude_ids or [])
    candidates = query_db(
        '''SELECT * FROM students
           WHERE class_id = ? AND group_name = ? AND is_active = 1
           ORDER BY name''',
        [class_id, group_name]
    )
    best = None
    best_count = float('inf')
    for candidate in candidates:
        candidate_id = candidate['id']
        if candidate_id in exclude_ids:
            continue
        existing = query_db(
            '''SELECT id FROM duty_schedule
               WHERE date = ? AND (student1_id = ? OR student2_id = ?) AND status != 'cancelled' ''',
            [date, candidate_id, candidate_id],
            one=True
        )
        if existing:
            continue
        count = query_db(
            '''SELECT COUNT(*) as cnt FROM duty_schedule
               WHERE (student1_id = ? OR student2_id = ?) AND status != 'cancelled' ''',
            [candidate_id, candidate_id],
            one=True
        )
        duty_count = count['cnt'] if count else 0
        if duty_count < best_count:
            best_count = duty_count
            best = candidate
    return best


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


def log_change(action_type, class_id=None, schedule_id=None, date=None,
               old_student1_id=None, old_student2_id=None,
               new_student1_id=None, new_student2_id=None, reason='', commit=True):
    """记录老师侧关键操作，方便追溯。事务内批量写入时传 commit=False。"""
    db = get_db()
    cur = db.execute(
        '''INSERT INTO change_logs
           (action_type, class_id, schedule_id, date, old_student1_id, old_student2_id,
            new_student1_id, new_student2_id, reason, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        [action_type, class_id, schedule_id, date, old_student1_id, old_student2_id,
         new_student1_id, new_student2_id, reason or '', now_iso()]
    )
    if commit:
        db.commit()
    return cur.lastrowid


def cleanup_invalid_schedules(class_id):
    """清理引用了已停用学生的排班：优先自动补位，否则把该岗位置空（保留搭档的值日）。"""
    db = get_db()
    rows = db.execute(
        '''SELECT * FROM duty_schedule WHERE class_id = ?
           AND ((student1_id IS NOT NULL AND student1_id NOT IN
                 (SELECT id FROM students WHERE is_active = 1))
             OR (student2_id IS NOT NULL AND student2_id NOT IN
                 (SELECT id FROM students WHERE is_active = 1)))''',
        [class_id]
    ).fetchall()
    active_ids = {
        row['id'] for row in db.execute(
            'SELECT id FROM students WHERE class_id = ? AND is_active = 1', [class_id]
        ).fetchall()
    }
    for row in rows:
        invalid1 = row['student1_id'] is not None and row['student1_id'] not in active_ids
        invalid2 = row['student2_id'] is not None and row['student2_id'] not in active_ids
        exclude = [sid for sid in (row['student1_id'], row['student2_id']) if sid is not None]
        # 用仍有效的一位学生确定替补查找的组别
        group_hint = None
        for sid in (row['student1_id'], row['student2_id']):
            if sid is not None and sid in active_ids:
                owner = query_db('SELECT group_name FROM students WHERE id = ?', [sid], one=True)
                group_hint = owner['group_name'] if owner else None
                break
        replacement = None
        if group_hint:
            replacement = find_best_replacement(class_id, group_hint, row['date'], exclude_ids=exclude)
        new1 = row['student1_id'] if not invalid1 else (replacement['id'] if replacement else None)
        if invalid1 and replacement:
            exclude.append(replacement['id'])
            replacement = None
        new2 = row['student2_id'] if not invalid2 else (replacement['id'] if replacement else None)
        if (new1, new2) == (row['student1_id'], row['student2_id']):
            continue
        db.execute(
            'UPDATE duty_schedule SET student1_id = ?, student2_id = ?, updated_at = ? WHERE id = ?',
            [new1, new2, now_iso(), row['id']]
        )
        log_change(
            'cleanup_student',
            class_id=class_id,
            schedule_id=row['id'],
            date=row['date'],
            old_student1_id=row['student1_id'],
            old_student2_id=row['student2_id'],
            new_student1_id=new1,
            new_student2_id=new2,
            reason='学生停用后自动清理排班引用',
            commit=False,
        )
    db.commit()


def build_schedule_preview(class_id, year, month):
    """生成排班预览，不写入数据库。"""
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        raise ValueError('班级不存在')

    duty_weekday = parse_int(class_info['duty_weekday'], '值日星期', 1, 5)
    semester = query_db('SELECT * FROM semesters WHERE id = ?', [class_info['semester_id']], one=True)
    if not semester:
        raise ValueError('学期不存在')

    sem_start = datetime.strptime(semester['start_date'], '%Y-%m-%d')
    sem_end = datetime.strptime(semester['end_date'], '%Y-%m-%d')
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year, 12, 31)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)

    if start_date < sem_start:
        start_date = sem_start
    if end_date > sem_end:
        end_date = sem_end

    if start_date > end_date:
        raise ValueError('所选月份不在当前学期范围内')

    current_group = class_info['current_group'] or 'A'
    students = query_db(
        '''SELECT * FROM students
           WHERE class_id = ? AND group_name = ? AND is_active = 1
           ORDER BY name''',
        [class_id, current_group]
    )
    if len(students) < 2:
        label = '上半学期' if current_group == 'A' else '下半学期'
        raise ValueError(f'{label}名单至少需要2名学生才能排班')

    count_map = get_duty_count_map(class_id, current_group)
    student_list = [dict(s) for s in students]
    last_duty_type = '擦桌子'
    preview = []
    conflicts = []
    warnings = []
    skipped = []
    planned_count = dict(count_map)

    current = start_date
    while current <= end_date:
        date_str = current.strftime('%Y-%m-%d')
        if current.weekday() != duty_weekday - 1:
            current += timedelta(days=1)
            continue

        if not is_workday(date_str):
            skipped.append({'date': date_str, 'reason': '节假日或非工作日'})
            current += timedelta(days=1)
            continue

        existing = query_db(
            'SELECT * FROM duty_schedule WHERE class_id = ? AND date = ?',
            [class_id, date_str],
            one=True
        )
        if existing:
            conflicts.append({
                'type': 'existing_schedule',
                'level': 'block',
                'date': date_str,
                'message': f'{date_str} 已有排班，发布前需要先删除或换月'
            })
            current += timedelta(days=1)
            continue

        student_list.sort(key=lambda x: (planned_count.get(x['id'], 0), x['name'], x['id']))
        min_count = min(planned_count.get(s['id'], 0) for s in student_list)
        available = [s for s in student_list if planned_count.get(s['id'], 0) == min_count]
        # 保持预览和发布完全一致，不使用随机抽样。
        selected = sorted(available, key=lambda x: (x['name'], x['id']))[:2] if len(available) >= 2 else student_list[:2]

        if last_duty_type == '擦桌子':
            duty1_type, duty2_type = '扫地', '擦桌子'
        else:
            duty1_type, duty2_type = '擦桌子', '扫地'
        last_duty_type = duty1_type

        for stu in selected:
            recent = query_db(
                '''SELECT date FROM duty_schedule
                   WHERE class_id = ? AND (student1_id = ? OR student2_id = ?)
                   AND status != 'cancelled'
                   ORDER BY date DESC LIMIT 1''',
                [class_id, stu['id'], stu['id']],
                one=True
            )
            if recent:
                delta = abs((datetime.strptime(date_str, '%Y-%m-%d') -
                             datetime.strptime(recent['date'], '%Y-%m-%d')).days)
                if delta <= 7:
                    warnings.append({
                        'type': 'recent_duty',
                        'level': 'warn',
                        'date': date_str,
                        'student_name': stu['name'],
                        'message': f'{stu["name"]} 距上次值日只有 {delta} 天'
                    })

        preview.append({
            'date': date_str,
            'weekday': weekday_name(duty_weekday),
            'student1_id': selected[0]['id'],
            'student1_name': selected[0]['name'],
            'student2_id': selected[1]['id'],
            'student2_name': selected[1]['name'],
            'duty1_type': duty1_type,
            'duty2_type': duty2_type,
        })
        planned_count[selected[0]['id']] = planned_count.get(selected[0]['id'], 0) + 1
        planned_count[selected[1]['id']] = planned_count.get(selected[1]['id'], 0) + 1
        current += timedelta(days=1)

    if not preview and not conflicts:
        raise ValueError('该时间段内没有可用的值日日期')

    return {
        'class': dict(class_info),
        'semester': dict(semester),
        'year': year,
        'month': month,
        'group': current_group,
        'group_label': '上半学期' if current_group == 'A' else '下半学期',
        'next_group': 'B' if current_group == 'A' else 'A',
        'preview': preview,
        'conflicts': conflicts,
        'warnings': warnings,
        'skipped': skipped,
        'can_publish': bool(preview) and not any(c.get('level') == 'block' for c in conflicts)
    }


def publish_schedule_preview(preview_data, reason=''):
    """把预览结果写入正式排班，并切换下一组。"""
    if not preview_data.get('can_publish'):
        raise ValueError('当前预览存在必须处理的问题，不能发布')

    class_info = preview_data['class']
    class_id = class_info['id']
    rows = preview_data.get('preview') or []
    if not rows:
        raise ValueError('没有可发布的排班')

    db = get_db()
    created = 0
    published_at = now_iso()
    for row in rows:
        # 并发防线由 UNIQUE(class_id, date) 索引保证，冲突时抛 IntegrityError 由路由返回 409
        cur = db.execute(
            '''INSERT INTO duty_schedule
               (class_id, date, student1_id, student2_id, duty1_type, duty2_type,
                status, published_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)''',
            [class_id, row['date'], row['student1_id'], row['student2_id'],
             row['duty1_type'], row['duty2_type'], published_at, published_at]
        )
        created += 1
        log_change(
            'publish_schedule',
            class_id=class_id,
            schedule_id=cur.lastrowid,
            date=row['date'],
            new_student1_id=row['student1_id'],
            new_student2_id=row['student2_id'],
            reason=reason or '发布排班',
            commit=False,
        )

    db.execute('UPDATE classes SET current_group = ? WHERE id = ?', [preview_data['next_group'], class_id])
    db.commit()
    return created


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
            try:
                parse_int(cls['duty_weekday'], '值日星期', 1, 5)
            except ValueError:
                issues.append({'level': 'block', 'class_id': cls['id'], 'message': f'{cls["name"]} 的值日星期设置不正确', 'target': '/admin/classes'})
            for group in ['A', 'B']:
                count = query_db(
                    'SELECT COUNT(*) as cnt FROM students WHERE class_id = ? AND group_name = ? AND is_active = 1',
                    [cls['id'], group],
                    one=True
                )['cnt']
                if count < 2:
                    label = '上半学期' if group == 'A' else '下半学期'
                    issues.append({'level': 'block', 'class_id': cls['id'], 'message': f'{cls["name"]}{label}名单只有 {count} 人，不能生成排班', 'target': '/admin/classes'})
            duplicates = query_db(
                '''SELECT name, COUNT(*) as cnt FROM students
                   WHERE class_id = ? AND is_active = 1
                   GROUP BY name HAVING cnt > 1''',
                [cls['id']]
            )
            for dup in duplicates:
                issues.append({'level': 'warn', 'class_id': cls['id'], 'message': f'{cls["name"]} 有 {dup["cnt"]} 个同名学生“{dup["name"]}”，建议合并', 'target': '/admin/classes'})

    holidays = query_db('SELECT * FROM holidays')
    for h in holidays:
        try:
            validate_date(h['date'], '假期日期')
        except ValueError:
            issues.append({'level': 'block', 'message': f'假期“{h["name"]}”的日期格式不正确：{h["date"]}', 'target': '/admin/holidays'})

    bad_refs = query_db('''
        SELECT ds.*, c.name as class_name FROM duty_schedule ds
        LEFT JOIN classes c ON ds.class_id = c.id
        LEFT JOIN students s1 ON ds.student1_id = s1.id AND s1.is_active = 1
        LEFT JOIN students s2 ON ds.student2_id = s2.id AND s2.is_active = 1
        WHERE s1.id IS NULL OR s2.id IS NULL
    ''')
    for row in bad_refs:
        issues.append({'level': 'block', 'schedule_id': row['id'], 'message': f'{row["class_name"] or "某班级"} {row["date"]} 的排班引用了已停用或不存在的学生', 'target': '/admin/schedule'})

    schedules = query_db('SELECT ds.*, c.name as class_name FROM duty_schedule ds LEFT JOIN classes c ON ds.class_id = c.id')
    seen = {}
    for row in schedules:
        key = (row['class_id'], row['date'])
        seen[key] = seen.get(key, 0) + 1
        if row['student1_id'] and row['student1_id'] == row['student2_id']:
            issues.append({'level': 'block', 'schedule_id': row['id'], 'message': f'{row["class_name"] or "某班级"} {row["date"]} 同一个学生被安排了两个职责', 'target': '/admin/schedule'})
        try:
            validate_date(row['date'], '排班日期')
            if not is_workday(row['date']):
                issues.append({'level': 'warn', 'schedule_id': row['id'], 'message': f'{row["class_name"] or "某班级"} {row["date"]} 排在了节假日或非工作日', 'target': '/admin/schedule'})
        except ValueError:
            issues.append({'level': 'block', 'schedule_id': row['id'], 'message': f'排班记录 {row["id"]} 日期格式不正确', 'target': '/admin/schedule'})
    for (class_id, date), count in seen.items():
        if count > 1:
            cls = query_db('SELECT name FROM classes WHERE id = ?', [class_id], one=True)
            issues.append({'level': 'block', 'class_id': class_id, 'message': f'{cls["name"] if cls else "某班级"} {date} 有重复排班', 'target': '/admin/schedule'})
    return issues


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
