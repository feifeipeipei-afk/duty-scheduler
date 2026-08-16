"""前台学生公开 API（无需登录）。"""
from flask import Blueprint, jsonify, request

from ..db import query_db
from ..helpers import normalize_name, parse_int
from ..scheduling import get_active_semester

bp = Blueprint('student_api', __name__)


@bp.route('/api/classes', methods=['GET'])
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


@bp.route('/api/student/schedule', methods=['GET'])
def get_student_schedule():
    """学生查看自己的值日安排。名单以老师后台维护为准。"""
    class_id = request.args.get('class_id')
    name = request.args.get('name')
    group = request.args.get('group', 'A')  # A=上半学期, B=下半学期

    if not all([class_id, name]):
        return jsonify({'error': '缺少必要参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # 基本输入验证
    name = normalize_name(name)
    if not name or len(name) > 20:
        return jsonify({'error': '姓名长度应为1-20个字符'}), 400

    if group not in ['A', 'B']:
        group = 'A'

    # 验证班级是否存在
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info:
        return jsonify({'error': '班级不存在'}), 404

    # 查找学生：名单必须先由老师导入或维护，避免输错姓名自动污染名单。
    student = query_db(
        'SELECT * FROM students WHERE class_id = ? AND name = ? AND is_active = 1',
        [class_id, name],
        one=True
    )

    if not student:
        return jsonify({'error': '名单中没有找到该学生，请核对姓名或联系老师导入名单'}), 404

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
