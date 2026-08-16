"""排班 API：预览/发布/调班/换日期/请假/批量状态/导出。"""
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, make_response, request

from ..calendar_rules import is_workday
from ..db import get_db, insert_db, query_db, update_db
from ..helpers import now_iso, parse_int, parse_month_parts, validate_date, validate_month
from ..scheduling import (build_schedule_preview, find_best_replacement,
                          log_change, publish_schedule_preview)
from ..xlsx import create_simple_xlsx

bp = Blueprint('schedule_api', __name__, url_prefix='/admin/schedule')

_leave_bp = Blueprint('leave_api', __name__)


# ---------- 请假（路径在 /admin/leave，不在 /admin/schedule 下） ----------

@_leave_bp.route('/admin/leave', methods=['POST'])
def create_leave():
    """请假操作（自动从同组选人补上）"""
    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    date = data.get('date')
    reason = data.get('reason', '')

    try:
        student_id = parse_int(student_id, '学生')
        date = validate_date(date, '请假日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # 获取请假学生信息
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    # 找到该日期对应的排班记录
    schedule = query_db(
        '''SELECT * FROM duty_schedule
           WHERE class_id = ? AND date = ? AND (student1_id = ? OR student2_id = ?)''',
        [student['class_id'], date, student_id, student_id],
        one=True
    )

    if not schedule:
        return jsonify({'error': '该日期没有该学生的值日安排'}), 404

    if schedule['status'] == 'cancelled':
        return jsonify({'error': '该排班已取消'}), 400

    best_replacement = find_best_replacement(
        student['class_id'],
        student['group_name'],
        date,
        exclude_ids=[student_id, schedule['student1_id'], schedule['student2_id']]
    )

    if not best_replacement:
        return jsonify({'error': '没有合适的替补学生'}), 400

    # 更新排班记录
    replacement_id = best_replacement['id']

    if schedule['student1_id'] == student_id:
        # 请假学生是student1
        update_db(
            '''UPDATE duty_schedule
               SET student1_id = ?, original_student1_id = ?, updated_at = ?
               WHERE id = ?''',
            [replacement_id, student_id, now_iso(), schedule['id']]
        )
    else:
        # 请假学生是student2
        update_db(
            '''UPDATE duty_schedule
               SET student2_id = ?, original_student2_id = ?, updated_at = ?
               WHERE id = ?''',
            [replacement_id, student_id, now_iso(), schedule['id']]
        )

    # 创建请假记录
    insert_db(
        '''INSERT INTO leave_records (student_id, date, reason, replacement_id, created_at)
           VALUES (?, ?, ?, ?, ?)''',
        [student_id, date, reason, replacement_id, now_iso()]
    )
    log_change(
        'leave',
        class_id=student['class_id'],
        schedule_id=schedule['id'],
        date=date,
        old_student1_id=schedule['student1_id'],
        old_student2_id=schedule['student2_id'],
        new_student1_id=replacement_id if schedule['student1_id'] == student_id else schedule['student1_id'],
        new_student2_id=replacement_id if schedule['student2_id'] == student_id else schedule['student2_id'],
        reason=reason or '请假换人'
    )

    return jsonify({
        'message': '请假成功',
        'replacement': dict(best_replacement)
    })


# ---------- 排班查询与生成 ----------

@bp.route('/list', methods=['GET'])
def get_schedule():
    """获取排班表"""
    try:
        class_id = parse_int(request.args.get('class_id'), '班级')
        month = request.args.get('month')  # 格式: YYYY-MM
        if month:
            month = validate_month(month)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    query = '''
        SELECT ds.*,
               s1.name as student1_name, s1.group_name as student1_group,
               s2.name as student2_name, s2.group_name as student2_group,
               c.name as class_name
        FROM duty_schedule ds
        LEFT JOIN students s1 ON ds.student1_id = s1.id
        LEFT JOIN students s2 ON ds.student2_id = s2.id
        LEFT JOIN classes c ON ds.class_id = c.id
        WHERE ds.class_id = ?
    '''
    params = [class_id]

    if month:
        query += " AND ds.date LIKE ?"
        params.append(f'{month}%')

    query += " ORDER BY ds.date"

    schedule = query_db(query, params)
    return jsonify([dict(s) for s in schedule])


@bp.route('/duty', methods=['GET'])
def get_schedule_duty():
    """获取某天某班的值日详情"""
    class_id = request.args.get('class_id')
    date = request.args.get('date')

    if not all([class_id, date]):
        return jsonify({'error': '缺少参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
        date = validate_date(date, '值日日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    schedule = query_db(
        '''SELECT ds.*,
                  s1.name as student1_name,
                  s2.name as student2_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           WHERE ds.class_id = ? AND ds.date = ?''',
        [class_id, date],
        one=True
    )

    if schedule:
        return jsonify(dict(schedule))
    return jsonify({'error': '该日期没有排班'}), 404


@bp.route('/generate', methods=['POST'])
def generate_schedule_compat():
    """兼容旧前端：生成预览后直接发布。新页面应使用 preview + publish。"""
    data = request.get_json(silent=True) or {}
    try:
        class_id = parse_int(data.get('class_id'), '班级')
        year, month = parse_month_parts(data.get('year'), data.get('month'))
        preview = build_schedule_preview(class_id, year, month)
        if not preview['can_publish']:
            return jsonify({'error': '存在排班冲突，请先查看预览', 'preview': preview}), 400
        created = publish_schedule_preview(preview, data.get('reason') or '一键生成排班')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except sqlite3.IntegrityError:
        get_db().rollback()
        return jsonify({'error': '发布冲突：部分日期已有排班，请重新预览'}), 409
    return jsonify({'message': f'排班发布成功，共生成{created}条记录', 'created': created})


@bp.route('/preview', methods=['POST'])
def preview_schedule():
    """生成排班预览，不写入数据库。"""
    data = request.get_json(silent=True) or {}
    try:
        class_id = parse_int(data.get('class_id'), '班级')
        year, month = parse_month_parts(data.get('year'), data.get('month'))
        preview = build_schedule_preview(class_id, year, month)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(preview)


@bp.route('/publish', methods=['POST'])
def publish_schedule():
    """确认发布排班预览。"""
    data = request.get_json(silent=True) or {}
    try:
        if data.get('preview'):
            submitted = data['preview']
            class_id = parse_int((submitted.get('class') or {}).get('id'), '班级')
            year, month = parse_month_parts(submitted.get('year'), submitted.get('month'))
            preview = build_schedule_preview(class_id, year, month)
        else:
            class_id = parse_int(data.get('class_id'), '班级')
            year, month = parse_month_parts(data.get('year'), data.get('month'))
            preview = build_schedule_preview(class_id, year, month)
        created = publish_schedule_preview(preview, data.get('reason') or '确认发布排班')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except sqlite3.IntegrityError:
        get_db().rollback()
        return jsonify({'error': '发布冲突：部分日期已有排班，请重新预览'}), 409
    return jsonify({'message': f'排班发布成功，共生成{created}条记录', 'created': created})


# ---------- 调班 ----------

@bp.route('/swap', methods=['POST'])
def swap_schedule():
    """调班（换人）- 替换单个学生"""
    data = request.get_json(silent=True) or {}
    try:
        schedule_id = parse_int(data.get('schedule_id'), '排班ID')
        raw1 = data.get('new_student1_id')
        raw2 = data.get('new_student2_id')
        new_student1_id = parse_int(raw1, '新学生1') if raw1 is not None else None
        new_student2_id = parse_int(raw2, '新学生2') if raw2 is not None else None
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if new_student1_id is None and new_student2_id is None:
        return jsonify({'error': '缺少新学生参数'}), 400

    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [schedule_id], one=True)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404

    final1 = new_student1_id if new_student1_id is not None else schedule['student1_id']
    final2 = new_student2_id if new_student2_id is not None else schedule['student2_id']
    if final1 is not None and final1 == final2:
        return jsonify({'error': '同一个学生不能同时承担两个职责'}), 400

    for raw_id in (new_student1_id, new_student2_id):
        if raw_id is None:
            continue
        student = query_db('SELECT * FROM students WHERE id = ?', [raw_id], one=True)
        if not student or not student['is_active']:
            return jsonify({'error': '新学生不存在或已停用'}), 404
        if student['class_id'] != schedule['class_id']:
            return jsonify({'error': f'{student["name"]} 不是本班学生，不能调换'}), 400

    db = get_db()
    # 仅在原始学生未被记录时才写入 original 字段，避免多次调班覆盖原始信息
    if new_student1_id is not None:
        orig1 = schedule['original_student1_id'] or schedule['student1_id']
        db.execute(
            'UPDATE duty_schedule SET student1_id = ?, original_student1_id = ?, updated_at = ? WHERE id = ?',
            [new_student1_id, orig1, now_iso(), schedule_id]
        )
    if new_student2_id is not None:
        orig2 = schedule['original_student2_id'] or schedule['student2_id']
        db.execute(
            'UPDATE duty_schedule SET student2_id = ?, original_student2_id = ?, updated_at = ? WHERE id = ?',
            [new_student2_id, orig2, now_iso(), schedule_id]
        )
    log_change(
        'swap',
        class_id=schedule['class_id'],
        schedule_id=schedule_id,
        date=schedule['date'],
        old_student1_id=schedule['student1_id'],
        old_student2_id=schedule['student2_id'],
        new_student1_id=final1,
        new_student2_id=final2,
        reason=data.get('reason') or '调班'
    )
    db.commit()

    return jsonify({'message': '调班成功'})


@bp.route('/swap-between', methods=['POST'])
def swap_between():
    """原子交换两个排班位置的学生"""
    data = request.get_json(silent=True) or {}
    s1_id = data.get('schedule1_id')
    s1_slot = data.get('slot1')  # 0=student1, 1=student2
    s2_id = data.get('schedule2_id')
    s2_slot = data.get('slot2')

    try:
        s1_id = parse_int(s1_id, '排班1')
        s2_id = parse_int(s2_id, '排班2')
        s1_slot = parse_int(s1_slot, '位置1', 0, 1)
        s2_slot = parse_int(s2_slot, '位置2', 0, 1)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    s1 = query_db('SELECT * FROM duty_schedule WHERE id = ?', [s1_id], one=True)
    s2 = query_db('SELECT * FROM duty_schedule WHERE id = ?', [s2_id], one=True)
    if not s1 or not s2:
        return jsonify({'error': '排班记录不存在'}), 404

    # 使用安全的白名单列名（避免 f-string 拼接 SQL 列名）
    SAFE_FIELDS = {
        0: ('student1_id', 'original_student1_id'),
        1: ('student2_id', 'original_student2_id'),
    }

    stu_col1, orig_col1 = SAFE_FIELDS[s1_slot]
    stu_col2, orig_col2 = SAFE_FIELDS[s2_slot]
    val1 = s1[stu_col1]
    val2 = s2[stu_col2]

    if val1 == val2:
        return jsonify({'message': '同一个学生，无需调换'})

    db = get_db()
    # 仅在原始学生未被记录时才写入 original 字段，避免多次调班覆盖原始信息
    orig1_val = s1[orig_col1] if s1[orig_col1] else val1
    orig2_val = s2[orig_col2] if s2[orig_col2] else val2

    db.execute(
        f'UPDATE duty_schedule SET {stu_col1} = ?, {orig_col1} = ? WHERE id = ?',
        [val2, orig1_val, s1_id]
    )
    db.execute(
        f'UPDATE duty_schedule SET {stu_col2} = ?, {orig_col2} = ? WHERE id = ?',
        [val1, orig2_val, s2_id]
    )
    log_change(
        'swap',
        class_id=s1['class_id'],
        schedule_id=s1_id,
        date=s1['date'],
        old_student1_id=s1['student1_id'],
        old_student2_id=s1['student2_id'],
        new_student1_id=val2 if s1_slot == 0 else s1['student1_id'],
        new_student2_id=val2 if s1_slot == 1 else s1['student2_id'],
        reason=data.get('reason', '调班'),
        commit=False,
    )
    if s2_id != s1_id:
        log_change(
            'swap',
            class_id=s2['class_id'],
            schedule_id=s2_id,
            date=s2['date'],
            old_student1_id=s2['student1_id'],
            old_student2_id=s2['student2_id'],
            new_student1_id=val1 if s2_slot == 0 else s2['student1_id'],
            new_student2_id=val1 if s2_slot == 1 else s2['student2_id'],
            reason=data.get('reason', '调班'),
            commit=False,
        )
    db.commit()

    return jsonify({'message': '调换成功'})


@bp.route('/swap-records', methods=['GET'])
def get_swap_records():
    """获取调班记录"""
    class_id = request.args.get('class_id')
    if class_id:
        try:
            class_id = parse_int(class_id, '班级')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    query = '''SELECT ds.date, ds.id as schedule_id, ds.class_id,
                  s1.name as student1_name, s2.name as student2_name,
                  os1.name as original_student1_name, os2.name as original_student2_name,
                  c.name as class_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           LEFT JOIN students os1 ON ds.original_student1_id = os1.id
           LEFT JOIN students os2 ON ds.original_student2_id = os2.id
           LEFT JOIN classes c ON ds.class_id = c.id
           WHERE (ds.original_student1_id IS NOT NULL OR ds.original_student2_id IS NOT NULL)'''
    params = []

    if class_id:
        query += ' AND ds.class_id = ?'
        params.append(class_id)

    query += ' ORDER BY ds.date DESC'

    records = query_db(query, params)
    return jsonify([dict(r) for r in records])


@bp.route('/swap-records/<int:record_id>', methods=['DELETE'])
def delete_swap_record(record_id):
    """撤销调班记录（恢复原始学生）"""
    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [record_id], one=True)
    if not schedule:
        return jsonify({'error': '记录不存在'}), 404

    if schedule['original_student1_id']:
        update_db(
            'UPDATE duty_schedule SET student1_id = original_student1_id, original_student1_id = NULL WHERE id = ?',
            [record_id]
        )
    if schedule['original_student2_id']:
        update_db(
            'UPDATE duty_schedule SET student2_id = original_student2_id, original_student2_id = NULL WHERE id = ?',
            [record_id]
        )
    log_change(
        'revert_swap',
        class_id=schedule['class_id'],
        schedule_id=record_id,
        date=schedule['date'],
        old_student1_id=schedule['student1_id'],
        old_student2_id=schedule['student2_id'],
        new_student1_id=schedule['original_student1_id'] or schedule['student1_id'],
        new_student2_id=schedule['original_student2_id'] or schedule['student2_id'],
        reason='撤销调班'
    )

    return jsonify({'message': '调班已撤销'})


@bp.route('/<int:schedule_id>/swap-date', methods=['PUT'])
def swap_schedule_date(schedule_id):
    """换课（调整某天值日日期）"""
    data = request.get_json(silent=True) or {}
    new_date = data.get('new_date')

    if not new_date:
        return jsonify({'error': '缺少new_date参数'}), 400
    try:
        new_date = validate_date(new_date, '新日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    old_schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [schedule_id], one=True)
    if not old_schedule:
        return jsonify({'error': '排班记录不存在'}), 404

    # 检查新日期是否已有排班（排除自身，允许原地修改）
    existing = query_db(
        'SELECT id FROM duty_schedule WHERE class_id = ? AND date = ? AND id != ?',
        [old_schedule['class_id'], new_date, schedule_id],
        one=True
    )
    if existing:
        return jsonify({'error': '该日期已有排班'}), 400

    # 检查新日期是否为工作日
    if not is_workday(new_date):
        return jsonify({'error': '该日期为非工作日或节假日'}), 400

    update_db(
        'UPDATE duty_schedule SET date = ?, updated_at = ? WHERE id = ?',
        [new_date, now_iso(), schedule_id]
    )
    log_change(
        'change_date',
        class_id=old_schedule['class_id'],
        schedule_id=schedule_id,
        date=new_date,
        old_student1_id=old_schedule['student1_id'],
        old_student2_id=old_schedule['student2_id'],
        new_student1_id=old_schedule['student1_id'],
        new_student2_id=old_schedule['student2_id'],
        reason=f'调整日期：{old_schedule["date"]} -> {new_date}'
    )

    return jsonify({'message': '日期调整成功'})


# ---------- 状态与删除 ----------

@bp.route('/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """删除单条排班记录"""
    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [schedule_id], one=True)
    if not schedule:
        return jsonify({'error': '排班记录不存在'}), 404
    db = get_db()
    # 解除审计记录对该排班的引用，保留操作历史
    db.execute('UPDATE change_logs SET schedule_id = NULL WHERE schedule_id = ?', [schedule_id])
    db.execute('DELETE FROM duty_schedule WHERE id = ?', [schedule_id])
    db.commit()
    return jsonify({'message': '已删除'})


@bp.route('/<int:schedule_id>/complete', methods=['PUT'])
def complete_schedule(schedule_id):
    """标记值日完成"""
    schedule = query_db('SELECT * FROM duty_schedule WHERE id = ?', [schedule_id], one=True)
    if not schedule:
        return jsonify({'error': '排班不存在'}), 404
    update_db(
        "UPDATE duty_schedule SET status = 'completed', updated_at = ? WHERE id = ?",
        [now_iso(), schedule_id]
    )
    log_change(
        'complete',
        class_id=schedule['class_id'],
        schedule_id=schedule_id,
        date=schedule['date'],
        new_student1_id=schedule['student1_id'],
        new_student2_id=schedule['student2_id'],
        reason='标记完成'
    )
    return jsonify({'message': '值日已标记为完成'})


@bp.route('/bulk-status', methods=['POST'])
def bulk_update_schedule_status():
    """批量标记完成/待完成。"""
    data = request.get_json(silent=True) or {}
    ids = data.get('schedule_ids') or []
    status = data.get('status', 'completed')
    if status not in ['completed', 'pending']:
        return jsonify({'error': '状态只能是 completed 或 pending'}), 400
    if not ids:
        return jsonify({'error': '请选择要操作的排班'}), 400

    parsed_ids = []
    try:
        for sid in ids:
            parsed_ids.append(parse_int(sid, '排班ID'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    db = get_db()
    updated = 0
    action = 'bulk_complete' if status == 'completed' else 'bulk_pending'
    for sid in parsed_ids:
        row = query_db('SELECT * FROM duty_schedule WHERE id = ?', [sid], one=True)
        if not row:
            continue
        db.execute('UPDATE duty_schedule SET status = ?, updated_at = ? WHERE id = ?', [status, now_iso(), sid])
        log_change(
            action,
            class_id=row['class_id'],
            schedule_id=sid,
            date=row['date'],
            new_student1_id=row['student1_id'],
            new_student2_id=row['student2_id'],
            reason=data.get('reason') or ('批量标记完成' if status == 'completed' else '批量改回待完成'),
            commit=False,
        )
        updated += 1
    db.commit()
    return jsonify({'message': f'已更新{updated}条排班', 'updated': updated})


# ---------- 导出 ----------

@bp.route('/export', methods=['GET'])
def export_schedule():
    """导出当月排班 Excel。"""
    try:
        class_id = parse_int(request.args.get('class_id'), '班级')
        month = validate_month(request.args.get('month') or datetime.now().strftime('%Y-%m'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    rows = query_db(
        '''SELECT ds.date, ds.duty1_type, ds.duty2_type, ds.status,
                  s1.name as student1_name, s2.name as student2_name, c.name as class_name
           FROM duty_schedule ds
           LEFT JOIN students s1 ON ds.student1_id = s1.id
           LEFT JOIN students s2 ON ds.student2_id = s2.id
           LEFT JOIN classes c ON ds.class_id = c.id
           WHERE ds.class_id = ? AND ds.date LIKE ?
           ORDER BY ds.date''',
        [class_id, f'{month}%']
    )
    export_rows = []
    for r in rows:
        weekday = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][datetime.strptime(r['date'], '%Y-%m-%d').weekday()]
        export_rows.append([r['date'], weekday, r['student1_name'] or '', r['duty1_type'] or '', r['student2_name'] or '', r['duty2_type'] or '', '已完成' if r['status'] == 'completed' else '待完成'])
    data = create_simple_xlsx(['日期', '星期', '学生1', '职责1', '学生2', '职责2', '状态'], export_rows, '排班表')
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = f'attachment; filename=schedule-{month}.xlsx'
    return resp
