"""后台认证：登录/登出、失败限速、路由守卫。"""
import hmac
import os
import time

from flask import Blueprint, jsonify, redirect, render_template, request, session

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 登录失败限速：每个 IP 的 (失败次数, 窗口起始时间)
LOGIN_ATTEMPTS = {}
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 60

bp = Blueprint('auth', __name__)


def is_admin_logged_in():
    return session.get('admin_logged_in', False)


def login_rate_limited():
    """检查该 IP 是否因连续登录失败被临时限制。"""
    record = LOGIN_ATTEMPTS.get(request.remote_addr)
    if not record:
        return False
    failures, window_start = record
    if time.time() - window_start > LOGIN_WINDOW_SECONDS:
        del LOGIN_ATTEMPTS[request.remote_addr]
        return False
    return failures >= LOGIN_MAX_FAILURES


def record_login_failure():
    now = time.time()
    record = LOGIN_ATTEMPTS.get(request.remote_addr)
    if not record or now - record[1] > LOGIN_WINDOW_SECONDS:
        LOGIN_ATTEMPTS[request.remote_addr] = (1, now)
    else:
        LOGIN_ATTEMPTS[request.remote_addr] = (record[0] + 1, record[1])


def clear_login_failures():
    LOGIN_ATTEMPTS.pop(request.remote_addr, None)


@bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html')
    if login_rate_limited():
        return jsonify({'error': '尝试次数过多，请1分钟后再试'}), 429
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if hmac.compare_digest(str(password), str(ADMIN_PASSWORD)):
        session['admin_logged_in'] = True
        clear_login_failures()
        return jsonify({'message': '登录成功'})
    record_login_failure()
    return jsonify({'error': '密码错误'}), 401


@bp.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect('/admin/login')


def register_auth_guard(app):
    """注册 /admin 路由的登录守卫。"""
    @app.before_request
    def require_admin_login():
        path = request.path
        # 放行：登录页、登出、静态资源、前台学生API、公开班级API（精确匹配，避免前缀绕过）
        public_paths = {'/', '/admin/login', '/admin/logout', '/favicon.ico'}
        if path in public_paths or path.startswith('/static/') or path.startswith('/api/student') or path.startswith('/api/classes'):
            return
        # 所有 /admin 下的页面和API都需要登录
        if path.startswith('/admin'):
            if not is_admin_logged_in():
                content_type = request.headers.get('Content-Type', '')
                is_json = 'application/json' in content_type or request.args.get('format') == 'json'
                if is_json:
                    return jsonify({'error': '未登录'}), 401
                return redirect('/admin/login')


def warn_insecure_config():
    """提醒生产环境注意的安全配置。"""
    if not os.environ.get('FLASK_SECRET_KEY'):
        print('[安全提示] 未设置 FLASK_SECRET_KEY，每次重启后所有登录会话都会失效。'
              '生产环境请通过环境变量固定一个随机密钥。')
    if ADMIN_PASSWORD == 'admin123':
        print('[安全提示] 正在使用默认管理密码 admin123，'
              '生产环境请通过环境变量 ADMIN_PASSWORD 修改。')
