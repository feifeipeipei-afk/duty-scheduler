"""删除路径回归测试：修复前这些场景在发布过排班后会因外键约束返回 500。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def test_delete_schedule_after_publish(published):
    """删除已发布（有关联审计记录）的排班，应成功而不是 500。"""
    client, rows = published
    result = ok(client.delete('/admin/schedule/{}'.format(rows[0]['id'])))
    assert result['message'] == '已删除'
    remaining = ok(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
    assert len(remaining) == len(rows) - 1
    # 审计记录应保留（schedule_id 被置空而不是丢失）
    logs = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    assert any(log['action_type'] == 'publish_schedule' for log in logs)


def test_delete_schedule_missing(published):
    client, _ = published
    ok(client.delete('/admin/schedule/99999'), 404)


def test_delete_student_keeps_partner_duty(published):
    """删除有值日的学生：搭档的值日应保留（修复前整行被删且 500）。"""
    client, rows = published
    victim = rows[0]['student1_id']
    partner = rows[0]['student2_id']
    result = ok(client.delete(f'/admin/students/{victim}'))
    assert result['message'] == '学生删除成功'

    remaining = ok(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
    row0 = next(r for r in remaining if r['id'] == rows[0]['id'])
    survived_ids = {row0['student1_id'], row0['student2_id']}
    assert partner in survived_ids
    # 自动补位或置空后，被删学生不应再出现
    assert victim not in survived_ids


def test_delete_class_cascade(published):
    """删除班级：排班、学生、请假记录一起清理，审计引用解除。"""
    client, rows = published
    ok(client.post('/admin/leave', json={
        'student_id': rows[1]['student1_id'], 'date': rows[1]['date'], 'reason': 'r',
    }))
    result = ok(client.delete('/admin/classes/1'))
    assert '已全部删除' in result['message']
    schedules = ok(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
    assert schedules == []
    students = ok(client.get('/admin/classes/1/students?format=json'))
    assert students == []
    # 学期仍在，可继续使用
    semesters = ok(client.get('/admin/semesters?format=json'))
    assert len(semesters) == 1


def test_delete_semester_with_holidays(seeded):
    """删除带节假日的学期：解除引用而不是 500。"""
    client = seeded
    ok(client.post('/admin/semesters', json={
        'name': '空学期', 'start_date': '2026-05-01', 'end_date': '2026-06-30',
    }))
    ok(client.post('/admin/holidays', json={
        'name': '自定义假', 'date': '2026-05-20', 'semester_id': 2,
    }))
    result = ok(client.delete('/admin/semesters/2'))
    assert result['message'] == '学期删除成功'


def test_delete_semester_with_classes_blocked(seeded):
    client = seeded
    result = ok(client.delete('/admin/semesters/1'), 400)
    assert '还有班级' in result['error']
