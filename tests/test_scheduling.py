"""排班核心逻辑测试：唯一索引、发布冲突、健康检查、迁移。"""
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from duty_scheduler.db import get_db, insert_db, migrate_db, query_db
from duty_scheduler.routes import schedule_api as schedule_api_module


def ok(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def test_unique_index_blocks_duplicate_schedules(seeded):
    """UNIQUE(class_id, date) 索引应阻止并发场景下的重复排班。"""
    ok(seeded.post('/admin/classes', json={'name': '二班', 'semester_id': 1, 'duty_weekday': 2}))
    with seeded.application.app_context():
        insert_db(
            'INSERT INTO duty_schedule (class_id, date) VALUES (?, ?)', [1, '2026-02-02'])
        with pytest.raises(sqlite3.IntegrityError):
            insert_db(
                'INSERT INTO duty_schedule (class_id, date) VALUES (?, ?)', [1, '2026-02-02'])
        # 不同班级同一天不受影响
        insert_db(
            'INSERT INTO duty_schedule (class_id, date) VALUES (?, ?)', [2, '2026-02-02'])


def test_publish_conflict_returns_409(seeded, monkeypatch):
    """模拟并发窗口：预览通过后数据被并发写入，发布应返回 409 而不是 500。"""
    with seeded.application.app_context():
        insert_db(
            'INSERT INTO duty_schedule (class_id, date) VALUES (?, ?)', [1, '2026-02-02'])

    def stale_preview(class_id, year, month):
        return {
            'class': {'id': class_id},
            'next_group': 'B',
            'can_publish': True,
            'preview': [{
                'date': '2026-02-02', 'student1_id': 1, 'student2_id': 2,
                'duty1_type': '扫地', 'duty2_type': '擦桌子',
            }],
        }

    monkeypatch.setattr(schedule_api_module, 'build_schedule_preview', stale_preview)
    resp = seeded.post('/admin/schedule/publish', json={'class_id': 1, 'year': 2026, 'month': 2})
    assert resp.status_code == 409
    assert '已有排班' in resp.get_json()['error']


def test_publish_regenerates_server_side(seeded):
    """客户端提交的预览内容不可信：服务端只按 class/year/month 重新生成。"""
    tampered = {
        'class': {'id': 1}, 'year': 2026, 'month': 2,
        'can_publish': True, 'next_group': 'B',
        'preview': [{
            'date': '2026-02-02', 'student1_id': 999, 'student2_id': 998,
            'duty1_type': '扫地', 'duty2_type': '擦桌子',
        }],
    }
    resp = seeded.post('/admin/schedule/publish', json={'preview': tampered})
    assert resp.status_code == 200
    rows = ok(seeded.get('/admin/schedule/list?format=json&class_id=1&month=2026-02'))
    first = rows[0]
    assert {first['student1_id'], first['student2_id']} != {999, 998}


def test_republish_same_month_blocked_by_preview(published):
    """同月已有排班时，预览应报告 block 冲突且 can_publish=False。"""
    client, _ = published
    # 切回 A 组重新预览同一月份
    ok(client.put('/admin/classes/1/group', json={'group_name': 'A'}))
    preview = ok(client.post('/admin/schedule/preview', json={
        'class_id': 1, 'year': 2026, 'month': 2,
    }))
    assert preview['can_publish'] is False
    assert any(c['level'] == 'block' for c in preview['conflicts'])
    resp = client.post('/admin/schedule/publish', json={'preview': preview})
    assert resp.status_code == 400


def test_health_check_flags_same_student_both_slots(seeded):
    with seeded.application.app_context():
        insert_db(
            'INSERT INTO duty_schedule (class_id, date, student1_id, student2_id) '
            "VALUES (1, '2026-02-02', 1, 1)")
    health = ok(seeded.get('/admin/health?format=json'))
    assert any('两个职责' in i['message'] for i in health['issues'])


def test_migration_dedupes_old_database(seeded):
    """老库迁移：删除重复排班（保留最早一条）并建立唯一索引。"""
    with seeded.application.app_context():
        # 直接绕过唯一索引构造老库的重复数据
        db = get_db()
        db.execute('DROP INDEX idx_duty_schedule_class_date')
        db.execute("INSERT INTO duty_schedule (class_id, date) VALUES (1, '2026-03-02')")
        db.execute("INSERT INTO duty_schedule (class_id, date) VALUES (1, '2026-03-02')")
        db.execute("INSERT INTO duty_schedule (class_id, date) VALUES (1, '2026-03-09')")
        db.execute(
            "INSERT INTO change_logs (action_type, class_id, schedule_id, date, reason, created_at) "
            "VALUES ('publish_schedule', 1, 2, '2026-03-02', 'old', '2026-01-01 00:00:00')")
        db.commit()

        migrate_db()

        dates = query_db(
            "SELECT date, COUNT(*) as cnt FROM duty_schedule GROUP BY date HAVING cnt > 1")
        assert not dates, '迁移后不应再有重复'
        # 索引已重建
        idx = query_db(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_duty_schedule_class_date'")
        assert idx
        # 再次迁移应幂等
        migrate_db()
