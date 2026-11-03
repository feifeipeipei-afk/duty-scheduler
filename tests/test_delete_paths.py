"""删除路径回归测试：删除记录/班级/学期时正确级联且审计保留。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    detail = (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    assert resp.status_code == status, detail
    return resp.get_json(silent=True)


def test_delete_record(seeded):
    """删除误提交的值日记录：成功且审计保留。"""
    client = seeded
    ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}))
    records = ok(client.get('/admin/records?format=json&class_id=1&month=2026-02'))
    assert len(records) == 1
    result = ok(client.delete('/admin/records/{}'.format(records[0]['id'])))
    assert result['message'] == '已删除'
    assert ok(client.get('/admin/records?format=json&class_id=1&month=2026-02')) == []
    logs = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    assert any(log['action_type'] == 'delete_record' for log in logs)


def test_delete_record_missing(seeded):
    client = seeded
    ok(client.delete('/admin/records/99999'), 404)


def test_delete_class_cascade(seeded):
    """删除有值日记录的班级：记录、学生一起清理，审计引用解除，不因外键 500。"""
    client = seeded
    ok(client.post('/api/duty/submit', json={
        'class_id': 1, 'name': 'A1', 'date': '2026-02-10'}))
    result = ok(client.delete('/admin/classes/1'))
    assert '已全部删除' in result['message']
    assert ok(client.get('/admin/classes/1/students?format=json')) == []
    assert ok(client.get('/admin/records?format=json&class_id=1&month=2026-02')) == []
    logs = ok(client.get('/admin/change-logs?format=json'))
    assert any(log['action_type'] == 'submit_duty' for log in logs)
    assert all(log['class_id'] is None for log in logs)
    semesters = ok(client.get('/admin/semesters?format=json'))
    assert len(semesters) == 1


def test_delete_semester(seeded):
    """有班级的学期删除被阻止；空学期可删除。"""
    client = seeded
    result = ok(client.delete('/admin/semesters/1'), 400)
    assert '还有班级' in result['error']
    ok(client.post('/admin/semesters', json={
        'name': '空学期', 'start_date': '2026-05-01', 'end_date': '2026-06-30',
    }))
    ok(client.delete('/admin/semesters/2'))
