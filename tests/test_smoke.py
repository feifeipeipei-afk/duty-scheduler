#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight smoke tests for the duty scheduler.

Run with:
    python3 tests/test_smoke.py
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as duty


def assert_status(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def make_client():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)
    duty.app.config['DATABASE'] = path
    duty.app.config['TESTING'] = True
    duty.app.secret_key = 'test-secret'
    with duty.app.app_context():
        duty.init_db()
    client = duty.app.test_client()
    assert_status(client.post('/admin/login', json={'password': duty.ADMIN_PASSWORD}))
    return client, path


def seed_basic(client):
    assert_status(client.post('/admin/semesters', json={
        'name': '测试学期',
        'start_date': '2026-02-01',
        'end_date': '2026-03-31',
    }))
    assert_status(client.post('/admin/semesters/1/activate'))
    assert_status(client.post('/admin/classes', json={
        'name': '高一一班',
        'semester_id': 1,
        'duty_weekday': 1,
    }))
    assert_status(client.post('/admin/students/batch', json={
        'class_id': 1,
        'group_name': 'A',
        'names': ['A1', 'A2', 'A3'],
    }))
    assert_status(client.post('/admin/students/batch', json={
        'class_id': 1,
        'group_name': 'B',
        'names': ['B1', 'B2'],
    }))


def test_core_flow():
    client, path = make_client()
    try:
        seed_basic(client)

        bad = assert_status(client.get('/api/student/schedule?class_id=abc&name=张三'), 400)
        assert '班级必须是数字' in bad['error']

        bad_class_semester = assert_status(client.post('/admin/classes', json={
            'name': '孤儿班',
            'semester_id': 999,
            'duty_weekday': 1,
        }), 404)
        assert '学期不存在' in bad_class_semester['error']

        bad_class_payload = assert_status(client.post('/admin/classes', data='not-json'), 400)
        assert '缺少班级名称' in bad_class_payload['error']

        missing_student = assert_status(client.get('/api/student/schedule?class_id=1&name=不存在'), 404)
        assert '名单中没有找到' in missing_student['error']
        students_after_missing = assert_status(client.get('/admin/classes/1/students?format=json'))
        assert all(s['name'] != '不存在' for s in students_after_missing)

        created_student = assert_status(client.post('/admin/students', json={
            'class_id': 1,
            'name': '补录学生',
            'group_name': 'A',
        }))
        assert created_student['message'] == '学生添加成功'
        duplicate_student = assert_status(client.post('/admin/students', json={
            'class_id': 1,
            'name': '补录学生',
            'group_name': 'A',
        }), 400)
        assert '请勿重复添加' in duplicate_student['error']
        known_student = assert_status(client.get('/api/student/schedule?class_id=1&name=补录学生&group=A'))
        assert known_student['student']['name'] == '补录学生'
        orphan_student = assert_status(client.post('/admin/students', json={
            'class_id': 999,
            'name': '孤儿学生',
            'group_name': 'A',
        }), 404)
        assert '班级不存在' in orphan_student['error']
        orphan_batch = assert_status(client.post('/admin/students/batch', json={
            'class_id': 999,
            'group_name': 'A',
            'names': ['孤儿学生'],
        }), 404)
        assert '班级不存在' in orphan_batch['error']

        bad_list_class = assert_status(client.get('/admin/schedule/list?format=json&class_id=abc&month=2026-02'), 400)
        assert '班级必须是数字' in bad_list_class['error']

        bad_list_month = assert_status(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-13'), 400)
        assert '月份不能大于12' in bad_list_month['error']

        preview = assert_status(client.post('/admin/schedule/preview', json={
            'class_id': 1,
            'year': 2026,
            'month': 2,
        }))
        assert preview['can_publish'] is True
        assert [r['date'] for r in preview['preview']] == ['2026-02-02', '2026-02-09']
        assert [r['date'] for r in preview['skipped']] == ['2026-02-16', '2026-02-23']

        published = assert_status(client.post('/admin/schedule/publish', json={'preview': preview}))
        assert published['created'] == len(preview['preview'])

        rows = assert_status(client.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
        assert [(r['student1_id'], r['student2_id']) for r in rows] == [
            (r['student1_id'], r['student2_id']) for r in preview['preview']
        ]

        assert_status(client.post('/admin/schedule/bulk-status', json={
            'schedule_ids': [rows[0]['id']],
            'status': 'completed',
        }))

        leave = assert_status(client.post('/admin/leave', json={
            'student_id': rows[1]['student1_id'],
            'date': rows[1]['date'],
            'reason': '测试请假',
        }))
        assert leave['replacement']['id'] != rows[1]['student1_id']

        logs = assert_status(client.get('/admin/change-logs?format=json&class_id=1'))
        assert any(log['action_type'] == 'leave' for log in logs)
        assert any(log['action_type'] == 'bulk_complete' for log in logs)
        bad_logs = assert_status(client.get('/admin/change-logs?format=json&class_id=abc'), 400)
        assert '班级必须是数字' in bad_logs['error']

        health = assert_status(client.get('/admin/health?format=json'))
        assert health['summary']['block'] == 0

        bad_heatmap = assert_status(client.get('/admin/stats/heatmap?class_id=1&year=abc'), 400)
        assert '年份必须是数字' in bad_heatmap['error']
        bad_summary = assert_status(client.get('/admin/stats/summary?class_id=abc'), 400)
        assert '班级必须是数字' in bad_summary['error']

        template = client.get('/admin/students/import-template')
        assert template.status_code == 200
        assert template.data[:2] == b'PK'

        bad_export = assert_status(client.get('/admin/schedule/export?class_id=1&month=2026-99'), 400)
        assert '月份不能大于12' in bad_export['error']

        imported = client.post('/admin/students/import-preview', data={
            'class_id': '1',
            'file': (io.BytesIO(template.data), 'students-template.xlsx'),
        }, content_type='multipart/form-data')
        preview_import = assert_status(imported)
        assert preview_import['summary']['new'] >= 1

        merge = assert_status(client.post('/admin/students/merge', json={
            'keep_student_id': rows[0]['student1_id'],
            'remove_student_id': rows[0]['student2_id'],
        }))
        assert '已合并到' in merge['message']

        bad_semester = assert_status(client.post('/admin/semesters', json={
            'name': '坏学期',
            'start_date': 'bad',
            'end_date': '2026-03-31',
        }), 400)
        assert 'YYYY-MM-DD' in bad_semester['error']

        orphan_holiday = assert_status(client.post('/admin/holidays', json={
            'name': '不存在学期假期',
            'date': '2026-03-03',
            'semester_id': 999,
        }), 404)
        assert '学期不存在' in orphan_holiday['error']

        bad_init_holiday = assert_status(client.post('/admin/holidays/init-system', json={
            'semester_id': 999,
        }), 404)
        assert '学期不存在' in bad_init_holiday['error']
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


if __name__ == '__main__':
    test_core_flow()
    print('smoke tests passed')
