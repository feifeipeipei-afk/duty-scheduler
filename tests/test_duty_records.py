"""值日记录核心流程测试：提交校验、值日榜、代补录、迁移幂等与健康检查。"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from duty_scheduler.db import get_db, init_db, query_db


def ok(resp, status=200):
    detail = (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    assert resp.status_code == status, detail
    return resp.get_json(silent=True)


def submit(client, **overrides):
    payload = {'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}
    payload.update(overrides)
    return client.post('/api/duty/submit', json=payload)


def _insert_student(client, name, group):
    with client.application.app_context():
        db = get_db()
        db.execute(
            'INSERT INTO students (name, class_id, group_name) VALUES (?, ?, ?)',
            [name, 1, group])
        db.commit()


# ---------- 学生自主提交 ----------

def test_submit_success_returns_group(seeded):
    client = seeded
    data = ok(submit(client))
    assert data['message'] == '值日记录提交成功'
    assert data['student']['name'] == 'A1'
    assert data['group_label'] == 'A 组（上半学期值日）'
    assert data['record']['date'] == '2026-02-10'
    assert data['record']['duty_type'] == '扫地'
    records = ok(client.get('/api/student/records?class_id=1&name=A1'))
    assert len(records['records']) == 1


def test_submit_defaults_to_today(client):
    today = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
    end = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    ok(client.post('/admin/semesters', json={
        'name': '本学期', 'start_date': start, 'end_date': end}))
    ok(client.post('/admin/semesters/1/activate'))
    ok(client.post('/admin/classes', json={'name': '一班', 'semester_id': 1}))
    ok(client.post('/admin/students', json={
        'class_id': 1, 'name': '今日学生', 'group_name': 'A'}))
    data = ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': '今日学生'}))
    assert data['record']['date'] == today


def test_submit_not_in_roster(seeded):
    client = seeded
    missing = ok(submit(client, name='不存在'), 404)
    assert '名单中没有找到' in missing['error']
    students = ok(client.get('/admin/classes/1/students?format=json'))
    assert all(s['name'] != '不存在' for s in students)


def test_submit_duplicate_same_day(seeded):
    client = seeded
    ok(submit(client))
    dup = ok(submit(client), 409)
    assert '已提交过' in dup['error']


def test_submit_bad_dates(seeded):
    client = seeded
    future = ok(submit(client, date='2026-12-01'), 400)
    assert '不能晚于今天' in future['error']
    outside = ok(submit(client, date='2026-04-10'), 400)
    assert '学期范围' in outside['error']
    bad = ok(submit(client, date='2026/02/10'), 400)
    assert 'YYYY-MM-DD' in bad['error']


def test_submit_bad_duty_type(seeded):
    client = seeded
    bad = ok(submit(client, duty_type='拖地'), 400)
    assert '扫地' in bad['error']
    ok(submit(client, duty_type='擦桌子'))


def test_submit_requires_active_semester(client):
    resp = ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}), 400)
    assert '激活学期' in resp['error']


def test_same_name_disambiguation(seeded):
    client = seeded
    _insert_student(client, '同名', 'A')
    _insert_student(client, '同名', 'B')
    ambiguous = ok(submit(client, name='同名'), 400)
    assert ambiguous.get('need_group') is True
    resolved = ok(submit(client, name='同名', group='B'))
    assert resolved['student']['group_name'] == 'B'
    assert resolved['group_label'] == 'B 组（下半学期值日）'
    other = ok(client.get('/api/student/records?class_id=1&name=同名&group=A'))
    assert other['group_label'] == 'A 组（上半学期值日）'
    assert other['records'] == []


def test_same_name_same_group_rejected(seeded):
    client = seeded
    _insert_student(client, '同名', 'A')
    _insert_student(client, '同名', 'A')
    ambiguous = ok(submit(client, name='同名'), 400)
    assert ambiguous.get('need_group') is True
    conflict = ok(submit(client, name='同名', group='A'), 400)
    assert '联系老师' in conflict['error']


# ---------- 班级值日榜 ----------

def test_summary_groups(seeded):
    client = seeded
    ok(submit(client, name='A1', date='2026-02-10'))
    ok(submit(client, name='A1', date='2026-02-11'))
    ok(submit(client, name='B1', date='2026-02-12'))
    data = ok(client.get('/api/duty/summary?class_id=1'))
    assert data['student_count'] == 6
    assert data['record_count'] == 3
    assert data['not_duty_count'] == 4
    groups = data['groups']
    assert groups['A']['not_duty_count'] == 3
    assert groups['B']['not_duty_count'] == 1
    a1 = next(s for s in groups['A']['students'] if s['name'] == 'A1')
    assert a1['duty_count'] == 2
    assert a1['last_duty_date'] == '2026-02-11'
    b1 = next(s for s in groups['B']['students'] if s['name'] == 'B1')
    assert b1['duty_count'] == 1


def test_summary_validation(seeded):
    client = seeded
    ok(client.get('/api/duty/summary'), 400)
    ok(client.get('/api/duty/summary?class_id=abc'), 400)
    ok(client.get('/api/duty/summary?class_id=999'), 404)


# ---------- 我的值日记录 ----------

def test_student_records_order(seeded):
    client = seeded
    ok(submit(client, date='2026-02-20'))
    ok(submit(client, date='2026-02-10'))
    ok(submit(client, date='2026-03-01'))
    records = ok(client.get('/api/student/records?class_id=1&name=A1'))
    dates = [r['date'] for r in records['records']]
    assert dates == ['2026-03-01', '2026-02-20', '2026-02-10']


# ---------- 老师代补录 / 删除 / 导出 ----------

def test_admin_add_record(seeded):
    client = seeded
    students = ok(client.get('/admin/classes/1/students?format=json'))
    b2 = next(s['id'] for s in students if s['name'] == 'B2')
    ok(client.post('/admin/records', json={'student_id': b2, 'date': '2026-02-15'}))
    dup = ok(client.post('/admin/records', json={
        'student_id': b2, 'date': '2026-02-15'}), 409)
    assert '已有值日记录' in dup['error']
    outside = ok(client.post('/admin/records', json={
        'student_id': b2, 'date': '2026-04-01'}), 400)
    assert '学期范围' in outside['error']
    missing = ok(client.post('/admin/records', json={
        'student_id': 99999, 'date': '2026-02-15'}), 404)
    assert '学生不存在' in missing['error']
    bad_type = ok(client.post('/admin/records', json={
        'student_id': b2, 'date': '2026-02-16', 'duty_type': '拖地'}), 400)
    assert '扫地' in bad_type['error']
    # 学期末延伸到未来后，未来日期仍被拒绝
    ok(client.put('/admin/semesters/1', json={
        'name': '测试学期', 'start_date': '2026-02-01', 'end_date': '2026-12-31'}))
    future = ok(client.post('/admin/records', json={
        'student_id': b2, 'date': '2026-12-01'}), 400)
    assert '不能晚于今天' in future['error']


def test_admin_records_filter_and_export(seeded):
    client = seeded
    ok(submit(client, name='A1', date='2026-02-10'))
    ok(submit(client, name='A2', date='2026-03-05'))
    feb = ok(client.get('/admin/records?format=json&class_id=1&month=2026-02'))
    assert [r['date'] for r in feb] == ['2026-02-10']
    assert feb[0]['student_name'] == 'A1'
    assert feb[0]['student_group'] == 'A'
    mar = ok(client.get('/admin/records?format=json&class_id=1&month=2026-03'))
    assert [r['date'] for r in mar] == ['2026-03-05']
    export = client.get('/admin/records/export?class_id=1&month=2026-02')
    assert export.status_code == 200
    assert export.data[:2] == b'PK'


# ---------- 老库迁移与健康检查 ----------

def test_legacy_migration_idempotent(seeded):
    client = seeded
    students = ok(client.get('/admin/classes/1/students?format=json'))
    a1 = next(s['id'] for s in students if s['name'] == 'A1')
    a2 = next(s['id'] for s in students if s['name'] == 'A2')
    with client.application.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO duty_schedule "
            "(class_id, date, student1_id, student2_id, duty1_type, duty2_type, "
            "status, published_at) VALUES (?, ?, ?, ?, ?, ?, 'completed', "
            "'2026-02-16T18:00:00')",
            [1, '2026-02-16', a1, a2, '扫地', '擦桌子'])
        db.commit()
        init_db()
        init_db()
        rows = query_db(
            'SELECT student_id, duty_type, submitted_at FROM duty_records'
            " WHERE date = '2026-02-16'")
        assert len(rows) == 2
        by_student = {r['student_id']: r for r in rows}
        assert by_student[a1]['duty_type'] == '扫地'
        assert by_student[a2]['duty_type'] == '擦桌子'
        assert by_student[a1]['submitted_at'] == '2026-02-16T18:00:00'


def test_health_checks(seeded):
    client = seeded
    _insert_student(client, '同名', 'A')
    _insert_student(client, '同名', 'B')
    with client.application.app_context():
        db = get_db()
        db.execute(
            'INSERT INTO duty_records (class_id, student_id, date, duty_type,'
            " submitted_at) VALUES (1, 1, '2026-01-05', '扫地', '2026-01-05T18:00:00')")
        db.commit()
    health = ok(client.get('/admin/health?format=json'))
    messages = [i['message'] for i in health['issues']]
    assert any('同名学生' in m for m in messages)
    assert any('不在所属学期范围' in m for m in messages)
    assert health['summary']['block'] == 0


def test_health_no_active_semester(client):
    health = ok(client.get('/admin/health?format=json'))
    assert health['summary']['block'] >= 1
    assert any('激活学期' in i['message'] for i in health['issues'])
