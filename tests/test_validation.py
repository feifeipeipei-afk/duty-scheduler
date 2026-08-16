"""输入校验回归测试：修复前这些请求会 500 或写坏数据。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def ok(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def test_noncanonical_date_rejected_everywhere(published):
    """2026-2-3 这类非规范日期必须被拒绝，否则会绕过 LIKE 月度过滤。"""
    client, rows = published
    leave = ok(client.post('/admin/leave', json={
        'student_id': rows[0]['student1_id'], 'date': '2026-2-3',
    }), 400)
    assert 'YYYY-MM-DD' in leave['error']

    swap_date = ok(client.put(
        '/admin/schedule/{}/swap-date'.format(rows[0]['id']), json={
            'new_date': '2026-2-3',
        }), 400)
    assert 'YYYY-MM-DD' in swap_date['error']

    semester = ok(client.post('/admin/semesters', json={
        'name': 'S', 'start_date': '2026-2-01', 'end_date': '2026-3-31',
    }), 400)
    assert 'YYYY-MM-DD' in semester['error']


def test_swap_rejects_bad_payload(published):
    client, rows = published
    # 非 JSON body 不应 500
    r = client.post('/admin/schedule/swap', data='not-json', content_type='application/json')
    assert r.status_code == 400
    # 缺参数
    ok(client.post('/admin/schedule/swap', json={}), 400)
    # 非数字 id（修复前直接进 SQL）
    bad = ok(client.post('/admin/schedule/swap', json={'schedule_id': 'abc'}), 400)
    assert '数字' in bad['error']
    # 不存在的排班
    ok(client.post('/admin/schedule/swap', json={
        'schedule_id': 99999, 'new_student1_id': 1,
    }), 404)
    # 不提供任何新学生
    ok(client.post('/admin/schedule/swap', json={'schedule_id': rows[0]['id']}), 400)


def test_swap_rejects_same_student_both_slots(published):
    """同一学生不能同时承担两个职责（修复前可以写坏数据）。"""
    client, rows = published
    bad = ok(client.post('/admin/schedule/swap', json={
        'schedule_id': rows[0]['id'],
        'new_student1_id': rows[0]['student2_id'],
        'new_student2_id': rows[0]['student2_id'],
    }), 400)
    assert '两个职责' in bad['error']


def test_swap_rejects_cross_class_and_inactive(seeded):
    client = seeded
    ok(client.post('/admin/classes', json={'name': '二班', 'semester_id': 1, 'duty_weekday': 2}))
    ok(client.post('/admin/students', json={'class_id': 2, 'name': '外班学生', 'group_name': 'A'}))
    ok(client.post('/admin/students', json={'class_id': 1, 'name': '停用学生', 'group_name': 'A'}))

    cls1 = ok(client.get('/admin/classes/1/students?format=json'))
    inactive_id = next(s['id'] for s in cls1 if s['name'] == '停用学生')
    ok(client.delete(f'/admin/students/{inactive_id}'))
    foreign_id = ok(client.get('/admin/classes/2/students?format=json'))[0]['id']

    resp = client.post('/admin/schedule/publish', json={'class_id': 1, 'year': 2026, 'month': 2})
    assert resp.status_code == 200
    row = client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02').get_json()[0]

    cross = ok(client.post('/admin/schedule/swap', json={
        'schedule_id': row['id'], 'new_student1_id': foreign_id,
    }), 400)
    assert '不是本班学生' in cross['error']

    inactive = ok(client.post('/admin/schedule/swap', json={
        'schedule_id': row['id'], 'new_student1_id': inactive_id,
    }), 404)
    assert '已停用' in inactive['error']


def test_swap_writes_audit_log(published):
    """调班必须写审计记录（修复前是唯一不写审计的变更操作）。"""
    client, rows = published
    logs_before = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    swaps_before = sum(1 for entry in logs_before if entry['action_type'] == 'swap')

    # 找一个同班 A 组、不在该排班上的学生来换
    students = ok(client.get('/admin/classes/1/students?format=json'))
    candidates = [s for s in students
                  if s['group_name'] == 'A' and s['is_active']
                  and s['id'] not in (rows[0]['student1_id'], rows[0]['student2_id'])]
    assert candidates
    ok(client.post('/admin/schedule/swap', json={
        'schedule_id': rows[0]['id'], 'new_student1_id': candidates[0]['id'],
    }))
    logs_after = ok(client.get('/admin/change-logs?format=json&class_id=1'))
    swaps_after = sum(1 for entry in logs_after if entry['action_type'] == 'swap')
    assert swaps_after == swaps_before + 1


def test_swap_date_validation(published):
    client, rows = published
    # 不存在的排班
    ok(client.put('/admin/schedule/99999/swap-date', json={'new_date': '2026-02-20'}), 404)
    # 已有排班的日期
    ok(client.put('/admin/schedule/{}/swap-date'.format(rows[0]['id']),
                  json={'new_date': rows[1]['date']}), 400)
    # 周末（非工作日）
    ok(client.put('/admin/schedule/{}/swap-date'.format(rows[0]['id']),
                  json={'new_date': '2026-02-21'}), 400)
    # 合法目标日期：2026-03-20 周五（无节假日）
    result = ok(client.put('/admin/schedule/{}/swap-date'.format(rows[0]['id']),
                           json={'new_date': '2026-03-20'}))
    assert result['message'] == '日期调整成功'
    # 原地改日期（同一天）不应被自身查重误伤
    ok(client.put('/admin/schedule/{}/swap-date'.format(rows[0]['id']),
                  json={'new_date': '2026-03-20'}))


def test_leave_validation(published):
    client, rows = published
    ok(client.post('/admin/leave', json={'date': '2026-02-09'}), 400)
    ok(client.post('/admin/leave', json={'student_id': 'abc', 'date': '2026-02-09'}), 400)
    ok(client.post('/admin/leave', json={
        'student_id': rows[0]['student1_id'], 'date': '2026-03-13',
    }), 404)  # 该日期没有该学生的值日安排
    ok(client.post('/admin/leave', json={
        'student_id': 99999, 'date': '2026-02-09',
    }), 404)


def test_import_confirm_requires_existing_class(seeded):
    client = seeded
    result = ok(client.post('/admin/students/import-confirm', json={
        'class_id': 999,
        'rows': [{'name': '张三', 'group_name': 'A'}],
    }), 404)
    assert '班级不存在' in result['error']


def test_semester_overlap_validation(seeded):
    client = seeded
    # 与 2026-02-01 ~ 2026-03-31 的测试学期重叠
    bad = ok(client.post('/admin/semesters', json={
        'name': '重叠学期', 'start_date': '2026-03-01', 'end_date': '2026-04-30',
    }), 400)
    assert '重叠' in bad['error']
    # 相邻不重叠的学期可以创建
    ok(client.post('/admin/semesters', json={
        'name': '下学期', 'start_date': '2026-04-01', 'end_date': '2026-06-30',
    }))
    # 更新成重叠范围被拒绝
    ok(client.put('/admin/semesters/2', json={
        'name': '下学期', 'start_date': '2026-03-15', 'end_date': '2026-06-30',
    }), 400)
    ok(client.put('/admin/semesters/999', json={
        'name': '不存在', 'start_date': '2026-03-15', 'end_date': '2026-06-30',
    }), 404)


def test_schedule_duty_not_found_returns_404(published):
    """GET /admin/schedule/duty 无记录时应返回 404 JSON 而不是 200 null。"""
    client, _ = published
    result = ok(client.get('/admin/schedule/duty?format=json&class_id=1&date=2026-03-02'), 404)
    assert '没有排班' in result['error']
    found = ok(client.get('/admin/schedule/duty?format=json&class_id=1&date=2026-02-02'))
    assert found['date'] == '2026-02-02'
