"""前台学生公开 API（无需登录）：提交值日记录、班级值日榜、个人记录查询。"""
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..db import get_db, query_db
from ..helpers import normalize_name, now_iso, parse_int, validate_date
from ..scheduling import get_active_semester, group_label, log_change

bp = Blueprint('student_api', __name__)


def _resolve_student(class_id, name, group):
    """解析学生（提交与个人记录查询共用）。

    覆盖 submit 的第 1、2、4、5、6 步：基础参数校验、组别校验、
    激活学期/班级校验、名单匹配（含同名歧义处理）。
    返回 (student, error_response)：成功时 error_response 为 None、
    student 为学生 dict；失败时 student 为 None。
    """
    # 第 1 步：班级与姓名必填
    if not class_id or not name:
        return None, (jsonify({'error': '缺少班级或姓名参数'}), 400)
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return None, (jsonify({'error': str(exc)}), 400)
    name = normalize_name(name)
    if not name or len(name) > 20:
        return None, (jsonify({'error': '姓名长度应为1-20个字符'}), 400)

    # 第 2 步：组别可选，提供时只能是 A/B
    if group and group not in ['A', 'B']:
        return None, (jsonify({'error': '组别只能是 A 或 B'}), 400)

    # 第 4 步：必须有激活学期
    semester = get_active_semester()
    if not semester:
        return None, (jsonify({'error': '还没有激活学期，请联系老师'}), 400)

    # 第 5 步：班级必须存在于当前学期
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info or class_info['semester_id'] != semester['id']:
        return None, (jsonify({'error': '班级不存在或不在当前学期'}), 404)

    # 第 6 步：名单以老师后台维护为准，避免输错姓名污染名单
    sql = 'SELECT * FROM students WHERE class_id = ? AND name = ? AND is_active = 1'
    args = [class_id, name]
    if group:
        sql += ' AND group_name = ?'
        args.append(group)
    students = query_db(sql, args)
    if not students:
        if group:
            message = f'{group} 组名单中没有找到该学生，请核对组别'
        else:
            message = '名单中没有找到该学生，请核对姓名或联系老师'
        return None, (jsonify({'error': message}), 404)
    if len(students) > 1:
        if group:
            return None, (jsonify({'error': '同名学生过多，请联系老师处理重复名单'}), 400)
        # 同名歧义：提示前端补选组别后重试
        return None, (jsonify({'error': '该班级存在同名学生，请选择组别后重试', 'need_group': True}), 400)

    return dict(students[0]), None


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


@bp.route('/api/duty/submit', methods=['POST'])
def submit_duty():
    """学生自主提交值日记录（可补交学期内往日，不能预填未来）。"""
    data = request.get_json(silent=True) or {}
    class_id = data.get('class_id')
    name = data.get('name')
    group = data.get('group')
    duty_type = data.get('duty_type') or '扫地'

    # 第 3 步：职责只能是扫地或擦桌子（缺省扫地）
    if duty_type not in ['扫地', '擦桌子']:
        return jsonify({'error': '职责只能是"扫地"或"擦桌子"'}), 400

    # 第 1、2、4、5、6 步：公共参数校验与名单解析
    student, error = _resolve_student(class_id, name, group)
    if error:
        return error

    # 第 7 步：日期缺省今天，须为规范格式、不晚于今天且在学期范围内
    semester = get_active_semester()
    today = datetime.now().strftime('%Y-%m-%d')
    date = data.get('date') or today
    try:
        date = validate_date(date, '值日日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if date > today:
        return jsonify({'error': '值日日期不能晚于今天'}), 400
    if not (semester['start_date'] <= date <= semester['end_date']):
        return jsonify({'error': f'值日日期须在学期范围内（{semester["start_date"]} ~ {semester["end_date"]}）'}), 400

    # 第 8 步：同一学生同一天只能提交一次
    existing = query_db(
        'SELECT id FROM duty_records WHERE student_id = ? AND date = ?',
        [student['id'], date], one=True
    )
    if existing:
        return jsonify({'error': '该学生当天已提交过值日记录'}), 409

    # 第 9、10 步：写入值日记录并记审计日志（同一事务），唯一索引兜底并发重复提交
    db = get_db()
    try:
        cur = db.execute(
            '''INSERT INTO duty_records (class_id, student_id, date, duty_type, submitted_at)
               VALUES (?, ?, ?, ?, ?)''',
            [student['class_id'], student['id'], date, duty_type, now_iso()]
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({'error': '该学生当天已提交过值日记录'}), 409
    record_id = cur.lastrowid
    log_change(
        'submit_duty',
        class_id=student['class_id'],
        student_id=student['id'],
        date=date,
        reason=f'学生自主提交（{duty_type}）',
        commit=False,
    )
    db.commit()

    # 第 11 步：成功响应
    return jsonify({
        'message': '值日记录提交成功',
        'student': {
            'id': student['id'],
            'name': student['name'],
            'group_name': student['group_name']
        },
        'group_label': group_label(student['group_name']),
        'record': {'id': record_id, 'date': date, 'duty_type': duty_type}
    })


@bp.route('/api/duty/summary', methods=['GET'])
def get_duty_summary():
    """班级值日榜：各组值日次数与未值日名单。"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': '缺少班级参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    semester = get_active_semester()
    if not semester:
        return jsonify({'error': '还没有激活学期，请联系老师'}), 400
    class_info = query_db('SELECT * FROM classes WHERE id = ?', [class_id], one=True)
    if not class_info or class_info['semester_id'] != semester['id']:
        return jsonify({'error': '班级不存在或不在当前学期'}), 404

    students = query_db(
        'SELECT id, name, group_name FROM students WHERE class_id = ? AND is_active = 1 ORDER BY name',
        [class_id]
    )
    stats = query_db(
        '''SELECT student_id, COUNT(*) as cnt, MAX(date) as last_date
           FROM duty_records WHERE class_id = ? GROUP BY student_id''',
        [class_id]
    )
    stat_map = {row['student_id']: row for row in stats}

    # 按 A/B 组聚合：组内按值日次数升序、同次数按姓名排序，并统计未值日人数
    groups = {}
    for group_name in ['A', 'B']:
        entries = []
        not_duty_count = 0
        for student in students:
            if student['group_name'] != group_name:
                continue
            stat = stat_map.get(student['id'])
            duty_count = stat['cnt'] if stat else 0
            if duty_count == 0:
                not_duty_count += 1
            entries.append({
                'id': student['id'],
                'name': student['name'],
                'duty_count': duty_count,
                'last_duty_date': stat['last_date'] if stat else None
            })
        entries.sort(key=lambda s: (s['duty_count'], s['name']))
        groups[group_name] = {
            'label': group_label(group_name),
            'not_duty_count': not_duty_count,
            'students': entries
        }

    return jsonify({
        'class_name': class_info['name'],
        'student_count': len(students),
        'record_count': sum(row['cnt'] for row in stats),
        'not_duty_count': groups['A']['not_duty_count'] + groups['B']['not_duty_count'],
        'groups': groups
    })


@bp.route('/api/student/records', methods=['GET'])
def get_student_records():
    """学生查询自己的历史值日记录。"""
    student, error = _resolve_student(
        request.args.get('class_id'),
        request.args.get('name'),
        request.args.get('group')
    )
    if error:
        return error

    records = query_db(
        '''SELECT id, date, duty_type, submitted_at FROM duty_records
           WHERE student_id = ? ORDER BY date DESC, id DESC''',
        [student['id']]
    )

    return jsonify({
        'student': {
            'id': student['id'],
            'name': student['name'],
            'group_name': student['group_name']
        },
        'group_label': group_label(student['group_name']),
        'records': [dict(r) for r in records]
    })
