"""后台管理 API：学期/班级/学生 CRUD、名单导入导出、审计与健康检查。"""
from flask import Blueprint, jsonify, make_response, request

from ..db import get_db, insert_db, query_db, update_db
from ..helpers import normalize_name, parse_int, validate_date
from ..scheduling import (check_semester_overlap, get_active_semester,
                          log_change, run_health_checks)
from ..xlsx import create_simple_xlsx, parse_student_import_text, parse_xlsx_students

bp = Blueprint('admin_api', __name__, url_prefix='/admin')


# ---------- 学期管理 ----------

@bp.route('/semesters', methods=['POST'])
def create_semester():
    """创建学期"""
    data = request.get_json(silent=True) or {}
    name = normalize_name(data.get('name'))
    start_date = data.get('start_date')
    end_date = data.get('end_date')

    if not all([name, start_date, end_date]):
        return jsonify({'error': '缺少必要参数'}), 400
    try:
        start_date = validate_date(start_date, '开始日期')
        end_date = validate_date(end_date, '结束日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if start_date > end_date:
        return jsonify({'error': '开始日期不能晚于结束日期'}), 400
    try:
        check_semester_overlap(start_date, end_date)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    semester_id = insert_db(
        'INSERT INTO semesters (name, start_date, end_date) VALUES (?, ?, ?)',
        [name, start_date, end_date]
    )

    return jsonify({'id': semester_id, 'message': '学期创建成功'})


@bp.route('/semesters/<int:semester_id>', methods=['PUT'])
def update_semester(semester_id):
    """更新学期"""
    data = request.get_json(silent=True) or {}
    name = normalize_name(data.get('name'))
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    if not all([name, start_date, end_date]):
        return jsonify({'error': '缺少必要参数'}), 400
    try:
        start_date = validate_date(start_date, '开始日期')
        end_date = validate_date(end_date, '结束日期')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if start_date > end_date:
        return jsonify({'error': '开始日期不能晚于结束日期'}), 400
    if not query_db('SELECT id FROM semesters WHERE id = ?', [semester_id], one=True):
        return jsonify({'error': '学期不存在'}), 404
    try:
        check_semester_overlap(start_date, end_date, exclude_id=semester_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    update_db(
        'UPDATE semesters SET name = ?, start_date = ?, end_date = ? WHERE id = ?',
        [name, start_date, end_date, semester_id]
    )

    return jsonify({'message': '学期更新成功'})


@bp.route('/semesters/<int:semester_id>', methods=['DELETE'])
def delete_semester(semester_id):
    """删除学期"""
    # 检查是否有关联的班级
    classes = query_db('SELECT COUNT(*) as cnt FROM classes WHERE semester_id = ?', [semester_id], one=True)
    if classes and classes['cnt'] > 0:
        return jsonify({'error': '该学期下还有班级，无法删除'}), 400

    db = get_db()
    # 解除该学期节假日的学期引用（保留假期本身，避免外键约束失败）
    db.execute('UPDATE holidays SET semester_id = NULL WHERE semester_id = ?', [semester_id])
    db.execute('DELETE FROM semesters WHERE id = ?', [semester_id])
    db.commit()
    return jsonify({'message': '学期删除成功'})


@bp.route('/semesters/<int:semester_id>/activate', methods=['POST'])
def activate_semester(semester_id):
    """激活学期（同时将其他学期设为非激活）"""
    semester = query_db('SELECT * FROM semesters WHERE id = ?', [semester_id], one=True)
    if not semester:
        return jsonify({'error': '学期不存在'}), 404
    db = get_db()
    db.execute('UPDATE semesters SET is_active = 0')
    db.execute('UPDATE semesters SET is_active = 1 WHERE id = ?', [semester_id])
    db.commit()
    return jsonify({'message': '学期激活成功'})


# ---------- 班级管理 ----------

@bp.route('/classes', methods=['POST'])
def create_class():
    """创建班级"""
    data = request.get_json(silent=True) or {}
    name = normalize_name(data.get('name'))
    semester_id = data.get('semester_id')

    if not name:
        return jsonify({'error': '缺少班级名称'}), 400

    # 如果没有指定学期，使用当前激活的学期
    if not semester_id:
        semester = get_active_semester()
        if semester:
            semester_id = semester['id']
        else:
            return jsonify({'error': '没有激活的学期，请先创建并激活学期'}), 400
    else:
        try:
            semester_id = parse_int(semester_id, '学期')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

    if not query_db('SELECT id FROM semesters WHERE id = ?', [semester_id], one=True):
        return jsonify({'error': '学期不存在'}), 404

    class_id = insert_db(
        'INSERT INTO classes (name, semester_id, duty_weekday) VALUES (?, ?, 1)',
        [name, semester_id]
    )

    return jsonify({'id': class_id, 'message': '班级创建成功'})


@bp.route('/classes/<int:class_id>', methods=['PUT'])
def update_class(class_id):
    """更新班级"""
    data = request.get_json(silent=True) or {}
    name = normalize_name(data.get('name'))
    if not name:
        return jsonify({'error': '缺少班级名称'}), 400
    if not query_db('SELECT id FROM classes WHERE id = ?', [class_id], one=True):
        return jsonify({'error': '班级不存在'}), 404

    update_db(
        'UPDATE classes SET name = ? WHERE id = ?',
        [name, class_id]
    )

    return jsonify({'message': '班级更新成功'})


@bp.route('/classes/<int:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """删除班级（级联删除学生、值日记录与遗留排班）"""
    if not query_db('SELECT id FROM classes WHERE id = ?', [class_id], one=True):
        return jsonify({'error': '班级不存在'}), 404
    db = get_db()
    # 先解除审计记录的外键引用（保留操作历史，仅去掉指向被删数据的引用）
    db.execute('''
        UPDATE change_logs SET schedule_id = NULL WHERE schedule_id IN
        (SELECT id FROM duty_schedule WHERE class_id = ?)
    ''', [class_id])
    db.execute('UPDATE change_logs SET class_id = NULL WHERE class_id = ?', [class_id])
    db.execute('''
        UPDATE change_logs SET student_id = NULL WHERE student_id IN
        (SELECT id FROM students WHERE class_id = ?)
    ''', [class_id])
    # 删除该班级的值日记录与遗留数据（duty_records 外键指向 students，须先删）
    db.execute('DELETE FROM duty_records WHERE class_id = ?', [class_id])
    db.execute('DELETE FROM duty_schedule WHERE class_id = ?', [class_id])
    db.execute('''
        DELETE FROM leave_records WHERE student_id IN
        (SELECT id FROM students WHERE class_id = ?) OR replacement_id IN
        (SELECT id FROM students WHERE class_id = ?)
    ''', [class_id, class_id])
    # 删除该班级的学生
    db.execute('DELETE FROM students WHERE class_id = ?', [class_id])
    # 删除班级
    db.execute('DELETE FROM classes WHERE id = ?', [class_id])
    db.commit()
    return jsonify({'message': '班级及相关数据已全部删除'})


@bp.route('/classes/<int:class_id>/students', methods=['GET'])
def get_class_students(class_id):
    """获取班级学生列表（前端兼容路由）"""
    students = query_db(
        '''SELECT s.*, c.name as class_name
           FROM students s
           LEFT JOIN classes c ON s.class_id = c.id
           WHERE s.class_id = ?
           ORDER BY s.group_name, s.name''',
        [class_id]
    )
    return jsonify([dict(s) for s in students])


# ---------- 学生管理 ----------

@bp.route('/students', methods=['POST'])
def create_student():
    """添加学生"""
    data = request.get_json(silent=True) or {}
    name = normalize_name(data.get('name'))
    class_id = data.get('class_id')
    group_name = data.get('group_name', 'A')

    if not all([name, class_id]):
        return jsonify({'error': '缺少必要参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not query_db('SELECT id FROM classes WHERE id = ?', [class_id], one=True):
        return jsonify({'error': '班级不存在'}), 404

    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400

    existing = query_db(
        'SELECT id FROM students WHERE class_id = ? AND name = ? AND is_active = 1',
        [class_id, name],
        one=True
    )
    if existing:
        return jsonify({'error': '该班级已有同名学生，请勿重复添加'}), 400

    student_id = insert_db(
        'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
        [name, class_id, group_name]
    )

    return jsonify({'id': student_id, 'message': '学生添加成功'})


@bp.route('/students/<int:student_id>', methods=['DELETE'])
def delete_student(student_id):
    """删除学生（软删除：标记为非活跃）"""
    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404
    # 软删除：标记为非活跃
    update_db('UPDATE students SET is_active = 0 WHERE id = ?', [student_id])
    return jsonify({'message': '学生删除成功'})


@bp.route('/students/<int:student_id>/group', methods=['PUT'])
def change_student_group(student_id):
    """修改学生组别（后台手动调整）"""
    data = request.get_json(silent=True) or {}
    group_name = data.get('group_name')

    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400

    student = query_db('SELECT * FROM students WHERE id = ?', [student_id], one=True)
    if not student:
        return jsonify({'error': '学生不存在'}), 404

    update_db('UPDATE students SET group_name = ? WHERE id = ?', [group_name, student_id])
    label = '上半学期' if group_name == 'A' else '下半学期'
    return jsonify({'message': f'已将 {student["name"]} 调整到{label}值日'})


@bp.route('/students/merge', methods=['POST'])
def merge_students():
    """合并重复学生：保留一个学生，另一个停用，并迁移相关引用。"""
    data = request.get_json(silent=True) or {}
    try:
        keep_id = parse_int(data.get('keep_student_id'), '保留学生')
        remove_id = parse_int(data.get('remove_student_id'), '合并学生')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if keep_id == remove_id:
        return jsonify({'error': '不能合并同一个学生'}), 400

    keep = query_db('SELECT * FROM students WHERE id = ? AND is_active = 1', [keep_id], one=True)
    remove = query_db('SELECT * FROM students WHERE id = ? AND is_active = 1', [remove_id], one=True)
    if not keep or not remove:
        return jsonify({'error': '学生不存在或已停用'}), 404
    if keep['class_id'] != remove['class_id']:
        return jsonify({'error': '只能合并同一个班级的学生'}), 400

    db = get_db()
    db.execute('UPDATE duty_schedule SET student1_id = ? WHERE student1_id = ?', [keep_id, remove_id])
    db.execute('UPDATE duty_schedule SET student2_id = ? WHERE student2_id = ?', [keep_id, remove_id])
    db.execute('UPDATE duty_schedule SET original_student1_id = ? WHERE original_student1_id = ?', [keep_id, remove_id])
    db.execute('UPDATE duty_schedule SET original_student2_id = ? WHERE original_student2_id = ?', [keep_id, remove_id])
    db.execute('UPDATE duty_records SET student_id = ? WHERE student_id = ?', [keep_id, remove_id])
    db.execute('UPDATE students SET is_active = 0 WHERE id = ?', [remove_id])
    db.commit()
    log_change('merge_students', class_id=keep['class_id'], reason=f'合并重复学生：{remove["name"]} -> {keep["name"]}')
    return jsonify({'message': f'已合并到 {keep["name"]}'})


@bp.route('/students/batch', methods=['POST'])
def batch_create_students():
    """批量添加学生"""
    data = request.get_json(silent=True) or {}
    names = data.get('names', [])
    class_id = data.get('class_id')
    group_name = data.get('group_name', 'A')

    if not names or not class_id:
        return jsonify({'error': '缺少必要参数'}), 400
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    if not query_db('SELECT id FROM classes WHERE id = ?', [class_id], one=True):
        return jsonify({'error': '班级不存在'}), 404

    if group_name not in ['A', 'B']:
        return jsonify({'error': '组名必须是 A 或 B'}), 400

    db = get_db()
    count = 0
    skipped = 0
    for name in names:
        name = normalize_name(name)
        if name:
            existing = query_db(
                'SELECT id FROM students WHERE class_id = ? AND name = ? AND is_active = 1',
                [class_id, name],
                one=True
            )
            if existing:
                skipped += 1
                continue
            db.execute(
                'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
                [name, class_id, group_name]
            )
            count += 1

    db.commit()
    msg = f'成功添加{count}名学生'
    if skipped:
        msg += f'，跳过{skipped}名重复学生'
    return jsonify({'message': msg, 'created': count, 'skipped': skipped})


# ---------- 导入导出 / 健康检查 / 变更记录 ----------

@bp.route('/students/import-preview', methods=['POST'])
def import_students_preview():
    """预览导入学生名单。支持 xlsx、csv、文本。"""
    class_id = request.form.get('class_id') or (request.get_json(silent=True) or {}).get('class_id')
    try:
        class_id = parse_int(class_id, '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    rows = []
    if 'file' in request.files:
        file = request.files['file']
        filename = (file.filename or '').lower()
        try:
            if filename.endswith('.xlsx'):
                rows = parse_xlsx_students(file)
            else:
                text = file.read().decode('utf-8-sig')
                rows = parse_student_import_text(text)
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        except Exception:
            return jsonify({'error': '名单文件解析失败，请使用模板中的姓名、值日段两列'}), 400
    else:
        data = request.get_json(silent=True) or {}
        rows = parse_student_import_text(data.get('text', ''))

    existing_names = {
        row['name'] for row in query_db(
            'SELECT name FROM students WHERE class_id = ? AND is_active = 1',
            [class_id]
        )
    }
    preview = []
    for row in rows:
        item = dict(row)
        if not item['name']:
            item['status'] = 'error'
            item['message'] = '姓名为空'
        elif item['name'] in existing_names:
            item['status'] = 'duplicate'
            item['message'] = '同班已有同名学生，默认跳过'
        else:
            item['status'] = 'new'
            item['message'] = '将新增'
        preview.append(item)

    return jsonify({
        'rows': preview,
        'summary': {
            'new': sum(1 for r in preview if r['status'] == 'new'),
            'duplicate': sum(1 for r in preview if r['status'] == 'duplicate'),
            'error': sum(1 for r in preview if r['status'] == 'error'),
        }
    })


@bp.route('/students/import-confirm', methods=['POST'])
def import_students_confirm():
    """确认导入学生名单。重复项默认跳过。"""
    data = request.get_json(silent=True) or {}
    try:
        class_id = parse_int(data.get('class_id'), '班级')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    rows = data.get('rows') or []
    if not rows:
        return jsonify({'error': '没有可导入的学生'}), 400
    if not query_db('SELECT id FROM classes WHERE id = ?', [class_id], one=True):
        return jsonify({'error': '班级不存在'}), 404

    existing_names = {
        row['name'] for row in query_db(
            'SELECT name FROM students WHERE class_id = ? AND is_active = 1',
            [class_id]
        )
    }
    db = get_db()
    created = 0
    skipped = 0
    for row in rows:
        name = normalize_name(row.get('name'))
        group = row.get('group_name') if row.get('group_name') in ['A', 'B'] else 'A'
        if not name or name in existing_names:
            skipped += 1
            continue
        db.execute('INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)', [name, class_id, group])
        existing_names.add(name)
        created += 1
    db.commit()
    log_change('import_students', class_id=class_id, reason=f'导入学生：新增{created}人，跳过{skipped}人')
    return jsonify({'message': f'导入完成：新增{created}人，跳过{skipped}人', 'created': created, 'skipped': skipped})


@bp.route('/students/import-template', methods=['GET'])
def download_student_template():
    data = create_simple_xlsx(['姓名', '值日段'], [['张三', '上半学期'], ['李四', '下半学期']], '学生名单模板')
    resp = make_response(data)
    resp.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    resp.headers['Content-Disposition'] = 'attachment; filename=students-template.xlsx'
    return resp


@bp.route('/change-logs', methods=['GET'])
def get_change_logs():
    class_id = request.args.get('class_id')
    if class_id:
        try:
            class_id = parse_int(class_id, '班级')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
    query = '''SELECT cl.*, c.name as class_name, st.name as student_name,
                      os1.name as old_student1_name, os2.name as old_student2_name,
                      ns1.name as new_student1_name, ns2.name as new_student2_name
               FROM change_logs cl
               LEFT JOIN classes c ON cl.class_id = c.id
               LEFT JOIN students st ON cl.student_id = st.id
               LEFT JOIN students os1 ON cl.old_student1_id = os1.id
               LEFT JOIN students os2 ON cl.old_student2_id = os2.id
               LEFT JOIN students ns1 ON cl.new_student1_id = ns1.id
               LEFT JOIN students ns2 ON cl.new_student2_id = ns2.id'''
    params = []
    if class_id:
        query += ' WHERE cl.class_id = ?'
        params.append(class_id)
    query += ' ORDER BY cl.created_at DESC, cl.id DESC LIMIT 200'
    rows = query_db(query, params)
    return jsonify([dict(r) for r in rows])


@bp.route('/health', methods=['GET'])
def health_check():
    issues = run_health_checks()
    return jsonify({
        'issues': issues,
        'summary': {
            'total': len(issues),
            'block': sum(1 for i in issues if i.get('level') == 'block'),
            'warn': sum(1 for i in issues if i.get('level') == 'warn'),
        }
    })
