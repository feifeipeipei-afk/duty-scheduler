"""值日排班管理系统 — 应用工厂。

模块结构：
- db              数据库连接、Schema、初始化与迁移
- helpers         输入校验与通用工具
- calendar_rules  节假日/调休数据（data/holidays.json）与工作日判断
- scheduling      排班核心业务（预览/发布/替补/健康检查）
- xlsx            名单导入解析与 Excel 导出
- auth            登录/登出、失败限速、路由守卫
- routes/         页面与 API 蓝图
"""
import os

from flask import Flask, jsonify, render_template

from .db import close_db
from .helpers import request_prefers_json


def create_app(test_config=None):
    # 模板与静态资源在项目根目录（本包的上一级），需显式指定
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, 'templates'),
        static_folder=os.path.join(project_root, 'static'),
    )
    app.config['DATABASE'] = os.environ.get(
        'DUTY_SCHEDULER_DB',
        os.path.join(project_root, 'duty_scheduler.db'),
    )
    app.json.ensure_ascii = False
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())

    if test_config:
        app.config.update(test_config)

    app.teardown_appcontext(close_db)

    from .auth import register_auth_guard
    from .routes import register_blueprints
    register_blueprints(app)
    register_auth_guard(app)

    @app.errorhandler(404)
    def not_found(error):
        if request_prefers_json():
            return jsonify({'error': '资源不存在'}), 404
        return render_template('error.html', code=404, message='页面不存在或已被移动'), 404

    @app.errorhandler(500)
    def server_error(error):
        if request_prefers_json():
            return jsonify({'error': '服务器内部错误'}), 500
        return render_template('error.html', code=500, message='服务器开小差了，请稍后重试'), 500

    return app
