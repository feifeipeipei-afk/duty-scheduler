"""安全加固回归测试：认证、限速、登出方法、上传加固。"""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from duty_scheduler.auth import ADMIN_PASSWORD, LOGIN_MAX_FAILURES
from duty_scheduler.xlsx import XLSX_MAX_FILE_BYTES


def ok(resp, status=200):
    assert resp.status_code == status, (resp.status_code, resp.get_json(silent=True), resp.data[:200])
    return resp.get_json(silent=True)


def test_admin_pages_require_login(anon_client):
    c = anon_client
    # 页面访问重定向到登录页
    resp = c.get('/admin')
    assert resp.status_code == 302
    assert '/admin/login' in resp.headers['Location']
    # API 请求返回 401 JSON
    resp = c.get('/admin/schedule/list?format=json&class_id=1')
    assert resp.status_code == 401
    assert resp.get_json()['error'] == '未登录'
    resp = c.post('/admin/semesters', json={'name': 'x'})
    assert resp.status_code == 401
    # 前缀绕过检查：/admin/login-evil 仍需要登录
    resp = c.get('/admin/login-evil')
    assert resp.status_code == 302
    # 公开路径照常可访问
    assert c.get('/').status_code == 200
    assert c.get('/api/classes').status_code == 200


def test_login_wrong_password(anon_client):
    resp = anon_client.post('/admin/login', json={'password': 'wrong'})
    assert resp.status_code == 401
    assert resp.get_json()['error'] == '密码错误'


def test_login_rate_limited(anon_client):
    for _ in range(LOGIN_MAX_FAILURES):
        resp = anon_client.post('/admin/login', json={'password': 'wrong'})
        assert resp.status_code == 401
    # 达到上限后即使密码正确也先被限速拒绝
    resp = anon_client.post('/admin/login', json={'password': ADMIN_PASSWORD})
    assert resp.status_code == 429
    # 错误密码同样被拒（窗口期内）
    resp = anon_client.post('/admin/login', json={'password': 'wrong'})
    assert resp.status_code == 429


def test_logout_is_post_only(client):
    resp = client.get('/admin/logout')
    assert resp.status_code == 405
    resp = client.post('/admin/logout')
    assert resp.status_code == 302
    # 会话已清除
    assert client.get('/admin/schedule/list?format=json&class_id=1').status_code == 401


def _make_xlsx_with_sheet(sheet_xml):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('[Content_Types].xml',
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    buf.seek(0)
    return buf


def test_xlsx_with_doctype_rejected(seeded):
    """包含 DOCTYPE/实体声明的 xlsx 应被拒绝（防 XML 实体膨胀）。"""
    malicious = _make_xlsx_with_sheet(
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "boom">]>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
    )
    resp = seeded.post('/admin/students/import-preview', data={
        'class_id': '1',
        'file': (malicious, 'evil.xlsx'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 400
    assert 'XML' in resp.get_json()['error']


def test_xlsx_oversize_rejected(seeded):
    """超过大小上限的文件应被拒绝。"""
    big = io.BytesIO(b'x' * (XLSX_MAX_FILE_BYTES + 1))
    resp = seeded.post('/admin/students/import-preview', data={
        'class_id': '1',
        'file': (big, 'big.xlsx'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 400
    assert '过大' in resp.get_json()['error']


def test_xlsx_valid_file_still_works(seeded):
    """正常模板文件不受加固影响。"""
    template = seeded.get('/admin/students/import-template')
    resp = seeded.post('/admin/students/import-preview', data={
        'class_id': '1',
        'file': (io.BytesIO(template.data), 'list.xlsx'),
    }, content_type='multipart/form-data')
    assert resp.status_code == 200
    assert resp.get_json()['summary']['new'] >= 1
