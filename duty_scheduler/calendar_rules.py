"""日历规则：中国法定节假日/调休工作日数据与工作日判断。

节假日数据存放在 data/holidays.json，每年国务院办公厅公布新安排后
直接更新该文件即可（避免改动代码）。"""

import json
import os
from datetime import datetime

from .db import query_db

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


def _load_calendar():
    with open(os.path.join(_DATA_DIR, 'holidays.json'), encoding='utf-8') as f:
        data = json.load(f)
    return dict(data.get('holidays') or {}), dict(data.get('workdays') or {})


SYSTEM_HOLIDAYS, SYSTEM_WORKDAYS = _load_calendar()


def is_workday(date_str):
    """判断某天是否为工作日（非周末且非节假日，支持调休工作日）"""
    # 检查是否为调休工作日（周末调整为上班）
    if date_str in SYSTEM_WORKDAYS:
        return True

    # 即使管理员还没导入系统假期，也要按内置法定节假日跳过
    if date_str in SYSTEM_HOLIDAYS:
        return False

    # 检查是否为周末
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    if date_obj.weekday() >= 5:  # 5=周六, 6=周日
        return False

    # 检查是否为节假日
    row = query_db('SELECT * FROM holidays WHERE date = ?', [date_str], one=True)
    if row:
        return False

    return True
