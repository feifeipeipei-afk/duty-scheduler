"""数据统计 API。"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..db import query_db
from ..helpers import parse_int
from ..scheduling import calculate_balance, get_active_semester

bp = Blueprint('stats_api', __name__, url_prefix='/admin/stats')


@bp.route('/quick', methods=['GET'])
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


@bp.route('/summary', methods=['GET'])
def get_stats_summary():
    """获取班级统计摘要"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

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
        "SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status != 'cancelled'",
        [class_id], one=True
    )

    # 已完成数
    completed = query_db(
        "SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status = 'completed'",
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


@bp.route('/duty-count', methods=['GET'])
def get_duty_count():
    """获取每人值日次数统计"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    students = query_db(
        '''SELECT s.id, s.name, s.group_name,
                  (SELECT COUNT(*) FROM duty_schedule
                   WHERE (student1_id = s.id OR student2_id = s.id) AND status != 'cancelled') as duty_count
           FROM students s WHERE s.class_id = ? AND s.is_active = 1
           ORDER BY s.group_name, duty_count DESC''',
        [class_id]
    )

    return jsonify([dict(s) for s in students])


@bp.route('/heatmap', methods=['GET'])
def get_heatmap():
    """获取日历热力图数据"""
    class_id = request.args.get('class_id')
    year = request.args.get('year', datetime.now().year)

    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
        year = parse_int(year, '年份', 1900, 2100)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

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
        'year': year,
        'months': [{'month': m, 'count': c} for m, c in sorted(months.items())],
        'days': [{'date': s['date'], 'student1': s['student1_name'], 'student2': s['student2_name'], 'status': s['status']} for s in schedules]
    })


@bp.route('/class/<int:class_id>', methods=['GET'])
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
        "SELECT COUNT(*) as cnt FROM duty_schedule WHERE class_id = ? AND status != 'cancelled'",
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


@bp.route('/student/<int:student_id>', methods=['GET'])
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
