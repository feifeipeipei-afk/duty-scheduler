"""值日记录 API：老师代补录、删除误提交、导出 Excel。"""
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, make_response, request

from ..db import get_db, query_db
from ..helpers import now_iso, parse_int, validate_date, validate_month
from ..scheduling import get_active_semester, group_label, log_change
from ..xlsx import create_simple_xlsx

bp = Blueprint('records_api', __name__, url_prefix='/admin/records')


@bp.route('', methods=['POST'])
def create_record():
    """老师代补录值日记录（duty_type 缺省扫地）。"""
    data = request.get_json(silent=True) or {}
    duty_type = data.get('duty_type') or '扫地'

    try:
        student_id = parse_int(data.get('student_id'), '学生')
        date = validate_date(data.get('date'), '值日日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if duty_type not in ['扫地', '擦桌子']:
        return jsonify({'error': '职责只能是 扫地 或 擦桌子'}), 400

    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student or not student['is_active']:
        return jsonify({'error': '学生不存在或已停用'}), 404

    semester = get_active_semester()
    if not semester:
        return jsonify({'error': '还没有激活学期，请先激活一个学期'}), 400
    if not (semester['start_date'] <= date <= semester['end_date']):
        return jsonify({'error': f'值日日期须在学期范围内（{semester["start_date"]} ~ {semester["end_date"]}）'}), 400
    if date > datetime.now().strftime('%Y-%m-%d'):
        return jsonify({'error': '值日日期不能晚于今天'}), 400

    existing = query_db(
        'SELECT id FROM duty_records WHERE student_id = ? AND date = ?',
        [student_id, date], one=True
    )
    if existing:
        return jsonify({'error': '该学生当天已有值日记录'}), 409

    db = get_db()
    try:
        db.execute(
            '''INSERT INTO duty_records (class_id, student_id, date, duty_type, submitted_at)
               VALUES (?, ?, ?, ?, ?)''',
            [student['class_id'], student_id, date, duty_type, now_iso()]
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return jsonify({'error': '该学生当天已有值日记录'}), 409
    log_change(
        'add_record',
        class_id=student['class_id'],
        student_id=student_id,
        date=date,
        reason=f'老师代补录（{duty_type}）',
        commit=False,
    )
    db.commit()
    return jsonify({'message': '补录成功'})


@bp.route('/<int:record_id>', methods=['DELETE'])
def delete_record(record_id):
    """删除误提交的值日记录。"""
    record = query_db('SELECT * FROM duty_records WHERE id = ?', [record_id], one=True)
    if not record:
        return jsonify({'error': '记录不存在'}), 404
    db = get_db()
    db.execute('DELETE FROM duty_records WHERE id = ?', [record_id])
    log_change(
        'delete_record',
        class_id=record['class_id'],
        student_id=record['student_id'],
        date=record['date'],
        reason='删除误提交记录',
        commit=False,
    )
    db.commit()
    return jsonify({'message': '已删除'})


@bp.route('/export', methods=['GET'])
def export_records():
    """导出某班当月值日记录 Excel。"""
    try:
        class_id = parse_int(request.args.get('class_id'), '班级')
        month = validate_month(request.args.get('month') or datetime.now().strftime('%Y-%m'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    rows = query_db(
        '''SELECT dr.date, dr.duty_type, dr.submitted_at,
                  s.name as student_name, s.group_name as student_group,
                  c.name as class_name
           FROM duty_records dr
           LEFT JOIN students s ON dr.student_id = s.id
           LEFT JOIN classes c ON dr.class_id = c.id
           WHERE dr.class_id = ? AND dr.date LIKE ?
           ORDER BY dr.date''',
        [class_id, f'{month}%']
    )
    export_rows = []
    for r in rows:
        weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][datetime.strptime(r['date'], '%Y-%m-%d').weekday()]
        export_rows.append([
            r['date'], weekday, r['student_name'] or '', group_label(r['student_group']),
            r['duty_type'] or '', r['submitted_at'] or ''
        ])
    data = create_simple_xlsx(['日期', '星期', '姓名', '组别', '职责', '提交时间'], export_rows, '值日记录')
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = f'attachment; filename=duty-records-{month}.xlsx'
    return resp
