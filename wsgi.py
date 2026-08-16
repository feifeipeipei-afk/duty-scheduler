#!/usr/bin/env python3
"""WSGI 入口（gunicorn / uWSGI 等生产服务器使用）。

用法：
    gunicorn --bind 0.0.0.0:5001 --workers 2 wsgi:app
"""

from duty_scheduler import create_app
from duty_scheduler.db import init_db

app = create_app()

with app.app_context():
    init_db()
