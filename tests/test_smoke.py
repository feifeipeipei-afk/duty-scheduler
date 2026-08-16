"""核心流程回归测试（原有冒烟测试的 pytest 版本）。

运行方式：pytest tests/
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def test_student_api_validation(seeded):
    client = seeded
    bad = ok(client.get('/api/student/schedule?class_id=abc&name=张三'), 400)
    assert '班级必须是数字' in bad['error']
    missing = ok(client.get('/api/student/schedule?class_id=1&name=不存在'), 404)
    assert '名单中没有找到' in missing['error']
    students_after_missing = ok(client.get('/admin/classes/1/students?format=json'))
    assert all(s['name'] != '不存在' for s in students_after_missing)


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
    known = ok(client.get('/api/student/schedule?class_id=1&name=补录学生&group=A'))
    assert known['student']['name'] == '补录学生'
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
        'name': '孤儿班', 'semester_id': 999, 'duty_weekday': 1,
    }), 404)
    assert '学期不存在' in bad['error']
    bad_payload = ok(client.post('/admin/classes', data='not-json'), 400)
    assert '缺少班级名称' in bad_payload['error']


def test_schedule_list_validation(seeded):
    client = seeded
    bad = ok(client.get('/admin/schedule/list?format=json&class_id=abc&month=2026-02'), 400)
    assert '班级必须是数字' in bad['error']
    bad_month = ok(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-13'), 400)
    assert '月份不能大于12' in bad_month['error']


def test_preview_publish_consistency(seeded):
    client = seeded
    preview = ok(client.post('/admin/schedule/preview', json={
        'class_id': 1, 'year': 2026, 'month': 2,
    }))
    assert preview['can_publish'] is True
    # 2026-02 的周一：02、09 可排；16、23 是春节假期
    assert [r['date'] for r in preview['preview']] == ['2026-02-02', '2026-02-09']
    assert [r['date'] for r in preview['skipped']] == ['2026-02-16', '2026-02-23']

    published = ok(client.post('/admin/schedule/publish', json={'preview': preview}))
    assert published['created'] == len(preview['preview'])

    rows = ok(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
    assert [(r['student1_id'], r['student2_id']) for r in rows] == [
        (r['student1_id'], r['student2_id']) for r in preview['preview']
    ]
    # 发布后班级应切换到 B 组
    cls = ok(client.get('/admin/classes?format=json&semester_id=1'))[0]
    assert cls['current_group'] == 'B'


def test_bulk_status_leave_and_logs(published):
    client, rows = published
    ok(client.post('/admin/schedule/bulk-status', json={
        'schedule_ids': [rows[0]['id']], 'status': 'completed',
    }))
    leave = ok(client.post('/admin/leave', json={
        'student_id': rows[1]['student1_id'],
        'date': rows[1]['date'],
        'reason': '测试请假',
    }))
    assert leave['replacement']['id'] != rows[1]['student1_id']

    logs = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    assert any(log['action_type'] == 'leave' for log in logs)
    assert any(log['action_type'] == 'bulk_complete' for log in logs)
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

    bad_export = ok(client.get('/admin/schedule/export?class_id=1&month=2026-99'), 400)
    assert '月份不能大于12' in bad_export['error']

    imported = client.post('/admin/students/import-preview', data={
        'class_id': '1',
        'file': (io.BytesIO(template.data), 'students-template.xlsx'),
    }, content_type='multipart/form-data')
    preview_import = ok(imported)
    assert preview_import['summary']['new'] >= 1


def test_merge_students(published):
    client, rows = published
    merge = ok(client.post('/admin/students/merge', json={
        'keep_student_id': rows[0]['student1_id'],
        'remove_student_id': rows[0]['student2_id'],
    }))
    assert '已合并到' in merge['message']


def test_semester_and_holiday_validation(seeded):
    client = seeded
    bad = ok(client.post('/admin/semesters', json={
        'name': '坏学期', 'start_date': 'bad', 'end_date': '2026-03-31',
    }), 400)
    assert 'YYYY-MM-DD' in bad['error']

    orphan_holiday = ok(client.post('/admin/holidays', json={
        'name': '不存在学期假期', 'date': '2026-03-03', 'semester_id': 999,
    }), 404)
    assert '学期不存在' in orphan_holiday['error']

    bad_init = ok(client.post('/admin/holidays/init-system', json={
        'semester_id': 999,
    }), 404)
    assert '学期不存在' in bad_init['error']
