"""通用辅助函数：输入校验、格式化、请求判断。"""
import re
from datetime import datetime

from flask import jsonify, request


def normalize_name(name):
    """清理姓名中的多余空白，减少重复登记。"""
    if name is None:
        return ''
    return re.sub(r'\s+', ' ', str(name)).strip()


def parse_int(value, field_name='参数', min_value=None, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name}必须是数字') from exc
    if min_value is not None and parsed < min_value:
        raise ValueError(f'{field_name}不能小于{min_value}')
    if max_value is not None and parsed > max_value:
        raise ValueError(f'{field_name}不能大于{max_value}')
    return parsed


def validate_date(value, field_name='日期'):
    if not value:
        raise ValueError(f'缺少{field_name}')
    value = str(value)
    try:
        parsed = datetime.strptime(value, '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError(f'{field_name}格式应为 YYYY-MM-DD') from exc
    canonical = parsed.strftime('%Y-%m-%d')
    if canonical != value:
        # 拒绝 2026-2-3 这类非规范格式，否则会静默绕过 LIKE 'YYYY-MM%' 月度过滤
        raise ValueError(f'{field_name}格式应为 YYYY-MM-DD')
    return canonical


def parse_month_parts(year, month):
    year = parse_int(year, '年份', 1900, 2100)
    month = parse_int(month, '月份', 1, 12)
    return year, month


def validate_month(value, field_name='月份'):
    if not value:
        raise ValueError(f'缺少{field_name}')
    value = str(value)
    if not re.match(r'^\d{4}-\d{2}$', value):
        raise ValueError(f'{field_name}格式应为 YYYY-MM')
    parse_month_parts(value[:4], value[5:])
    return value


def json_error(message, status=400):
    return jsonify({'error': message}), status


def now_iso():
    return datetime.now().isoformat(timespec='seconds')


def weekday_name(duty_weekday):
    names = ['', '星期一', '星期二', '星期三', '星期四', '星期五']
    try:
        return names[int(duty_weekday)]
    except (ValueError, IndexError):
        return str(duty_weekday)


def wants_json_request():
    """判断页面路由的本次请求是否应返回 JSON（前端 AJAX 双用途路由）。"""
    content_type = request.headers.get('Content-Type', '')
    return 'application/json' in content_type or request.args.get('format') == 'json'


def request_prefers_json():
    """判断错误响应应返回 JSON（API 调用）还是 HTML 页面。"""
    if request.path.startswith('/api/'):
        return True
    if request.args.get('format') == 'json':
        return True
    content_type = request.headers.get('Content-Type', '')
    if 'application/json' in content_type:
        return True
    accept = request.headers.get('Accept', '')
    return 'application/json' in accept and 'text/html' not in accept
