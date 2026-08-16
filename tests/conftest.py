"""pytest 公共夹具：每个测试使用独立的临时数据库和应用实例。"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from duty_scheduler import create_app
from duty_scheduler.auth import ADMIN_PASSWORD, LOGIN_ATTEMPTS
from duty_scheduler.db import init_db


def _fresh_app(tmp_path):
    application = create_app({
        'DATABASE': str(tmp_path / 'test.db'),
        'TESTING': True,
    })
    application.secret_key = 'test-secret'
    with application.app_context():
        init_db()
    LOGIN_ATTEMPTS.clear()
    return application


@pytest.fixture()
def anon_client(tmp_path):
    """未登录的客户端。"""
    application = _fresh_app(tmp_path)
    with application.test_client() as c:
        yield c


@pytest.fixture()
def client(tmp_path):
    """已登录管理员的客户端。"""
    application = _fresh_app(tmp_path)
    with application.test_client() as c:
        resp = c.post('/admin/login', json={'password': ADMIN_PASSWORD})
        assert resp.status_code == 200
        yield c


@pytest.fixture()
def seeded(client):
    """学期 + 班级 + A/B 两组学生的基础数据。"""
    assert client.post('/admin/semesters', json={
        'name': '测试学期', 'start_date': '2026-02-01', 'end_date': '2026-03-31',
    }).status_code == 200
    assert client.post('/admin/semesters/1/activate').status_code == 200
    assert client.post('/admin/classes', json={
        'name': '高一一班', 'semester_id': 1, 'duty_weekday': 1,
    }).status_code == 200
    assert client.post('/admin/students/batch', json={
        'class_id': 1, 'group_name': 'A', 'names': ['A1', 'A2', 'A3', 'A4'],
    }).status_code == 200
    assert client.post('/admin/students/batch', json={
        'class_id': 1, 'group_name': 'B', 'names': ['B1', 'B2'],
    }).status_code == 200
    return client


@pytest.fixture()
def published(seeded):
    """已发布 2026-02（A组）排班的环境，返回当月排班列表。"""
    resp = seeded.post('/admin/schedule/publish', json={'class_id': 1, 'year': 2026, 'month': 2})
    assert resp.status_code == 200
    rows = seeded.get('/admin/schedule/list?format=json&class_id=1&month=2026-02').get_json()
    assert rows, '发布后应有排班记录'
    return seeded, rows
