"""输入校验回归测试：修复前这些请求会 500 或写坏数据。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    detail = (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    assert resp.status_code == status, detail
    return resp.get_json(silent=True)


def test_noncanonical_date_rejected_everywhere(seeded):
    """2026-2-3 这类非规范日期必须被拒绝，否则会绕过 LIKE 月度过滤。"""
    client = seeded
    submit = ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-2-3',
    }), 400)
    assert 'YYYY-MM-DD' in submit['error']
    record = ok(client.post('/admin/records', json={
        'student_id': 1, 'date': '2026-2-3',
    }), 400)
    assert 'YYYY-MM-DD' in record['error']
    semester = ok(client.post('/admin/semesters', json={
        'name': 'S', 'start_date': '2026-2-01', 'end_date': '2026-3-31',
    }), 400)
    assert 'YYYY-MM-DD' in semester['error']


def test_semester_overlap_validation(seeded):
    client = seeded
    bad = ok(client.post('/admin/semesters', json={
        'name': '重叠学期', 'start_date': '2026-03-01', 'end_date': '2026-04-30',
    }), 400)
    assert '重叠' in bad['error']
    ok(client.post('/admin/semesters', json={
        'name': '下学期', 'start_date': '2026-04-01', 'end_date': '2026-06-30',
    }))
    ok(client.put('/admin/semesters/2', json={
        'name': '下学期', 'start_date': '2026-03-15', 'end_date': '2026-06-30',
    }), 400)
    ok(client.put('/admin/semesters/999', json={
        'name': '不存在', 'start_date': '2026-03-15', 'end_date': '2026-06-30',
    }), 404)


def test_import_confirm_requires_existing_class(seeded):
    client = seeded
    result = ok(client.post('/admin/students/import-confirm', json={
        'class_id': 999,
        'rows': [{'name': '张三', 'group_name': 'A'}],
    }), 404)
    assert '班级不存在' in result['error']
