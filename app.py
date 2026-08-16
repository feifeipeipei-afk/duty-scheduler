#!/usr/bin/env python3
"""
值日排班管理系统 - 启动入口

实际实现已拆分到 duty_scheduler 包：
    duty_scheduler/            应用工厂与核心模块
    duty_scheduler/routes/     页面与 API 蓝图

本文件保留为兼容入口：python app.py 直接启动服务。
"""

import os

from duty_scheduler import create_app
from duty_scheduler.auth import warn_insecure_config
from duty_scheduler.db import init_db

app = create_app()

if __name__ == '__main__':
    # 初始化数据库（含老库迁移）
    with app.app_context():
        init_db()

    warn_insecure_config()
    # 启动Flask应用
    debug_enabled = os.environ.get('FLASK_DEBUG', '').lower() in ['1', 'true', 'yes', 'on']
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5001')),
            debug=debug_enabled, use_reloader=debug_enabled)
