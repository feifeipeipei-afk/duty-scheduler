"""页面路由：服务端渲染的 Jinja 页面（部分同时兼任 JSON API）。"""
from flask import Blueprint, jsonify, render_template, request

from ..db import query_db
from ..helpers import parse_int, validate_month, wants_json_request
from ..scheduling import get_active_semester

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    """前台首页（学生入口）"""
    return render_template('index.html')


@bp.route('/favicon.ico')
def favicon():
    return ('', 204)


@bp.route('/admin')
def admin_page():
    """后台管理首页"""
    return render_template('admin.html')


@bp.route('/admin/semesters')
def semesters_page():
    """学期管理页 / 学期列表API"""
    if wants_json_request():
        semesters = query_db('SELECT * FROM semesters ORDER BY start_date DESC')
        return jsonify([dict(s) for s in semesters])
    return render_template('admin_semesters.html')


@bp.route('/admin/classes')
def classes_page():
    """班级管理页 / 班级列表API"""
    # 前端AJAX请求返回JSON，直接访问返回HTML页面
    if wants_json_request():
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


@bp.route('/admin/students')
def students_page():
    """学生管理页 / 学生列表API"""
    if wants_json_request():
        class_id = request.args.get('class_id')
        if not class_id:
            return jsonify({'error': '缺少class_id参数'}), 400
        try:
            class_id = parse_int(class_id, '班级')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
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


@bp.route('/admin/records')
def records_page():
    """值日记录管理页 / 记录列表API"""
    if wants_json_request():
        class_id = request.args.get('class_id')
        month = request.args.get('month')  # 格式: YYYY-MM
        try:
            if class_id:
                class_id = parse_int(class_id, '班级')
            if month:
                month = validate_month(month)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        query = '''
            SELECT dr.*, s.name as student_name, s.group_name as student_group,
                  c.name as class_name
            FROM duty_records dr
            LEFT JOIN students s ON dr.student_id = s.id
            LEFT JOIN classes c ON dr.class_id = c.id
            WHERE 1=1
        '''
        params = []
        if class_id:
            query += ' AND dr.class_id = ?'
            params.append(class_id)
        if month:
            query += ' AND dr.date LIKE ?'
            params.append(f'{month}%')
        query += ' ORDER BY dr.date DESC, dr.id DESC'
        records = query_db(query, params)
        return jsonify([dict(r) for r in records])
    return render_template('admin_records.html')


@bp.route('/admin/stats')
def stats_page():
    """数据统计页"""
    return render_template('admin_stats.html')
