"""核心流程回归测试（学生自主提交模式的冒烟测试）。"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    detail = (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    assert resp.status_code == status, detail
    return resp.get_json(silent=True)


def test_public_pages(seeded):
    client = seeded
    assert client.get('/').status_code == 200
    classes = ok(client.get('/api/classes'))
    assert [c['name'] for c in classes] == ['高一一班']


def test_student_records_validation(seeded):
    client = seeded
    bad = ok(client.get('/api/student/records?class_id=abc&name=A1'), 400)
    assert '班级必须是数字' in bad['error']
    missing = ok(client.get('/api/student/records?class_id=1&name=不存在'), 404)
    assert '名单中没有找到' in missing['error']
    students = ok(client.get('/admin/classes/1/students?format=json'))
    assert all(s['name'] != '不存在' for s in students)


def test_student_crud(seeded):
    client = seeded
    created = ok(client.post('/admin/students', json={
        'class_id': 1, 'name': '补录学生', 'group_name': 'A',
    }))
    assert created['message'] == '学生添加成功'
    duplicate = ok(client.post('/admin/students', json={
        'class_id': 1, 'name': '补录学生', 'group_name': 'A',
    }), 400)
    assert '请勿重复添加' in duplicate['error']
    known = ok(client.get('/api/student/records?class_id=1&name=补录学生&group=A'))
    assert known['student']['name'] == '补录学生'
    assert known['group_label'] == 'A 组（上半学期值日）'
    orphan = ok(client.post('/admin/students', json={
        'class_id': 999, 'name': '孤儿学生', 'group_name': 'A',
    }), 404)
    assert '班级不存在' in orphan['error']
    orphan_batch = ok(client.post('/admin/students/batch', json={
        'class_id': 999, 'group_name': 'A', 'names': ['孤儿学生'],
    }), 404)
    assert '班级不存在' in orphan_batch['error']


def test_class_validation(seeded):
    client = seeded
    bad = ok(client.post('/admin/classes', json={
        'name': '孤儿班', 'semester_id': 999,
    }), 404)
    assert '学期不存在' in bad['error']
    bad_payload = ok(client.post('/admin/classes', data='not-json'), 400)
    assert '缺少班级名称' in bad_payload['error']


def test_records_list_validation(seeded):
    client = seeded
    bad = ok(client.get('/admin/records?format=json&class_id=abc&month=2026-02'), 400)
    assert '班级必须是数字' in bad['error']
    bad_month = ok(client.get(
        '/admin/records?format=json&class_id=1&month=2026-13'), 400)
    assert '月份不能大于12' in bad_month['error']


def test_change_logs_and_health(seeded):
    client = seeded
    ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}))
    logs = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    assert any(log['action_type'] == 'submit_duty' for log in logs)
    assert any(log.get('student_name') == 'A1' for log in logs)
    bad_logs = ok(client.get('/admin/change-logs?format=json&class_id=abc'), 400)
    assert '班级必须是数字' in bad_logs['error']
    health = ok(client.get('/admin/health?format=json'))
    assert health['summary']['block'] == 0


def test_stats_validation(seeded):
    client = seeded
    bad_heatmap = ok(client.get('/admin/stats/heatmap?class_id=1&year=abc'), 400)
    assert '年份必须是数字' in bad_heatmap['error']
    bad_summary = ok(client.get('/admin/stats/summary?class_id=abc'), 400)
    assert '班级必须是数字' in bad_summary['error']


def test_import_template_and_preview(seeded):
    client = seeded
    template = client.get('/admin/students/import-template')
    assert template.status_code == 200
    assert template.data[:2] == b'PK'
    bad_export = ok(client.get('/admin/records/export?class_id=1&month=2026-99'), 400)
    assert '月份不能大于12' in bad_export['error']
    imported = client.post('/admin/students/import-preview', data={
        'class_id': '1',
        'file': (io.BytesIO(template.data), 'students-template.xlsx'),
    }, content_type='multipart/form-data')
    preview_import = ok(imported)
    assert preview_import['summary']['new'] >= 1


def test_merge_students_migrates_records(seeded):
    client = seeded
    ok(client.post('/admin/students', json={
        'class_id': 1, 'name': '重复A1', 'group_name': 'A'}))
    ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}))
    ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': '重复A1', 'date': '2026-02-11'}))
    students = ok(client.get('/admin/classes/1/students?format=json'))
    a1 = next(s['id'] for s in students if s['name'] == 'A1')
    dup = next(s['id'] for s in students if s['name'] == '重复A1')
    merge = ok(client.post('/admin/students/merge', json={
        'keep_student_id': a1, 'remove_student_id': dup,
    }))
    assert '已合并到' in merge['message']
    records = ok(client.get('/api/student/records?class_id=1&name=A1'))
    dates = sorted(r['date'] for r in records['records'])
    assert dates == ['2026-02-10', '2026-02-11']
