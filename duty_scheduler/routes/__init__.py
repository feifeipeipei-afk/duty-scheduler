"""路由蓝图集合。"""
from . import admin_api, pages, schedule_api, stats_api, student_api


def register_blueprints(app):
    from ..auth import bp as auth_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(pages.bp)
    app.register_blueprint(admin_api.bp)
    app.register_blueprint(schedule_api.bp)
    app.register_blueprint(schedule_api._leave_bp)
    app.register_blueprint(stats_api.bp)
    app.register_blueprint(student_api.bp)
