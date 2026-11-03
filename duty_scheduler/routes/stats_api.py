"""数据统计 API：以学生自主提交的 duty_records 为唯一数据源。"""
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..db import query_db
from ..helpers import parse_int
from ..scheduling import get_active_semester

bp = Blueprint('stats_api', __name__, url_prefix='/admin/stats')


@bp.route('/quick', methods=['GET'])
def get_quick_stats():
    """工作台快速统计：班级数、学生数、累计记录、本月记录、未值日人数"""
    semester = get_active_semester()
    if not semester:
        return jsonify({
            'class_count': 0,
            'student_count': 0,
            'record_count': 0,
            'month_record_count': 0,
            'not_duty_count': 0,
        })

    class_count = query_db(
        'SELECT COUNT(*) as cnt FROM classes WHERE semester_id = ?',
        [semester['id']], one=True
    )
    student_count = query_db(
        '''SELECT COUNT(*) as cnt FROM students s
           JOIN classes c ON s.class_id = c.id
           WHERE c.semester_id = ? AND s.is_active = 1''',
        [semester['id']], one=True
    )
    record_count = query_db(
        '''SELECT COUNT(*) as cnt FROM duty_records dr
           JOIN classes c ON dr.class_id = c.id
           WHERE c.semester_id = ?''',
        [semester['id']], one=True
    )
    month_str = datetime.now().strftime('%Y-%m')
    month_record_count = query_db(
        '''SELECT COUNT(*) as cnt FROM duty_records dr
           JOIN classes c ON dr.class_id = c.id
           WHERE c.semester_id = ? AND dr.date LIKE ?''',
        [semester['id'], f'{month_str}%'], one=True
    )
    not_duty_count = query_db(
        '''SELECT COUNT(*) as cnt FROM students s
           JOIN classes c ON s.class_id = c.id
           WHERE c.semester_id = ? AND s.is_active = 1
             AND NOT EXISTS (SELECT 1 FROM duty_records dr WHERE dr.student_id = s.id)''',
        [semester['id']], one=True
    )

    return jsonify({
        'class_count': class_count['cnt'] if class_count else 0,
        'student_count': student_count['cnt'] if student_count else 0,
        'record_count': record_count['cnt'] if record_count else 0,
        'month_record_count': month_record_count['cnt'] if month_record_count else 0,
        'not_duty_count': not_duty_count['cnt'] if not_duty_count else 0,
    })


@bp.route('/summary', methods=['GET'])
def get_stats_summary():
    """班级统计摘要：记录总数与 A/B 组未值日人数"""
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

    student_count = query_db(
        'SELECT COUNT(*) as cnt FROM students WHERE class_id = ? AND is_active = 1',
        [class_id], one=True
    )
    record_count = query_db(
        'SELECT COUNT(*) as cnt FROM duty_records WHERE class_id = ?',
        [class_id], one=True
    )
    not_duty_rows = query_db(
        '''SELECT s.group_name, COUNT(*) as cnt FROM students s
           WHERE s.class_id = ? AND s.is_active = 1
             AND NOT EXISTS (SELECT 1 FROM duty_records dr WHERE dr.student_id = s.id)
           GROUP BY s.group_name''',
        [class_id]
    )
    group_counts = {row['group_name']: row['cnt'] for row in not_duty_rows}

    return jsonify({
        'class_name': class_info['name'],
        'student_count': student_count['cnt'] if student_count else 0,
        'record_count': record_count['cnt'] if record_count else 0,
        'not_duty_count': sum(row['cnt'] for row in not_duty_rows),
        'group_a_not_duty': group_counts.get('A', 0),
        'group_b_not_duty': group_counts.get('B', 0),
    })


@bp.route('/duty-count', methods=['GET'])
def get_duty_count():
    """每人值日次数（全部启用学生，含 0 次）"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    students = query_db(
        '''SELECT s.id, s.name, s.group_name,
                  (SELECT COUNT(*) FROM duty_records dr WHERE dr.student_id = s.id) as duty_count
           FROM students s
           WHERE s.class_id = ? AND s.is_active = 1
           ORDER BY s.group_name, duty_count DESC''',
        [class_id]
    )

    return jsonify([dict(s) for s in students])


@bp.route('/heatmap', methods=['GET'])
def get_heatmap():
    """按日期统计值日记录，用于热力图"""
    class_id = request.args.get('class_id')
    year = request.args.get('year', datetime.now().year)

    if not class_id:
        return jsonify({'error': '缺少class_id参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
        year = parse_int(year, '年份', 1900, 2100)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    records = query_db(
        '''SELECT dr.date, s.name as student_name
           FROM duty_records dr
           LEFT JOIN students s ON dr.student_id = s.id
           WHERE dr.class_id = ? AND dr.date LIKE ?
           ORDER BY dr.date''',
        [class_id, f'{year}%']
    )

    months = {}
    days = {}
    for r in records:
        month = r['date'][:7]  # YYYY-MM
        months[month] = months.get(month, 0) + 1
        days.setdefault(r['date'], []).append(r['student_name'] or '未知学生')

    return jsonify({
        'year': year,
        'months': [{'month': m, 'count': c} for m, c in sorted(months.items())],
        'days': [
            {'date': d, 'count': len(names), 'names': names}
            for d, names in sorted(days.items())
        ],
    })


@bp.route('/class/<int:class_id>', methods=['GET'])
def get_class_stats(class_id):
    """班级统计：每人值日次数与未值日人数"""
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404

    students = query_db(
        '''SELECT s.id, s.name, s.group_name,
                  (SELECT COUNT(*) FROM duty_records dr WHERE dr.student_id = s.id) as duty_count
           FROM students s
           WHERE s.class_id = ? AND s.is_active = 1
           ORDER BY s.group_name, duty_count''',
        [class_id]
    )
    student_stats = [dict(s) for s in students]
    not_duty_count = sum(1 for s in student_stats if not s['duty_count'])
    total_records = query_db(
        'SELECT COUNT(*) as cnt FROM duty_records WHERE class_id = ?',
        [class_id], one=True
    )

    return jsonify({
        'class_name': class_info['name'],
        'student_stats': student_stats,
        'not_duty_count': not_duty_count,
        'total_records': total_records['cnt'] if total_records else 0,
    })


@bp.route('/student/<int:student_id>', methods=['GET'])
def get_student_stats(student_id):
    """学生值日明细：记录列表与职责统计"""
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    records = query_db(
        'SELECT * FROM duty_records WHERE student_id = ? ORDER BY date DESC, id DESC',
        [student_id]
    )
    record_list = [dict(r) for r in records]

    return jsonify({
        'student': dict(student),
        'records': record_list,
        'stats': {
            'total_count': len(record_list),
            'sweep_floor_count': sum(1 for r in record_list if r['duty_type'] == '扫地'),
            'wipe_table_count': sum(1 for r in record_list if r['duty_type'] == '擦桌子'),
        },
    })
