"""Excel/CSV 名单导入解析与 xlsx 导出生成（零依赖，标准库实现）。"""
import csv
import io
import zipfile
import xml.etree.ElementTree as ET
from html import escape as html_escape

from .helpers import normalize_name

# 上传 xlsx 的解析上限，防止 zip 炸弹和超大文件拖垮服务
XLSX_MAX_FILE_BYTES = 5 * 1024 * 1024
XLSX_MAX_ENTRIES = 200
XLSX_MAX_ENTRY_BYTES = 20 * 1024 * 1024


def parse_student_import_text(text):
    """解析 CSV/纯文本名单。支持逗号、制表符、换行分隔。"""
    rows = []
    stream = io.StringIO(text)
    sample = text[:512]
    delimiter = '\t' if '\t' in sample and ',' not in sample else ','
    reader = csv.reader(stream, delimiter=delimiter)
    for idx, row in enumerate(reader, start=1):
        if not row or not ''.join(row).strip():
            continue
        if idx == 1 and any(cell.strip() in ['姓名', 'name', '学生姓名'] for cell in row):
            continue
        name = normalize_name(row[0] if row else '')
        group_raw = normalize_name(row[1] if len(row) > 1 else 'A')
        group = 'B' if group_raw in ['B', 'b', '下半学期', '下半', '下'] else 'A'
        rows.append({'line': idx, 'name': name, 'group_name': group})
    return rows


def parse_xlsx_students(file_obj):
    """用标准库解析简单 xlsx 的第一个工作表。"""
    data = file_obj.read()
    if len(data) > XLSX_MAX_FILE_BYTES:
        raise ValueError('文件过大，请上传 5MB 以内的名单文件')
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if len(zf.namelist()) > XLSX_MAX_ENTRIES:
            raise ValueError('文件内容异常（条目过多）')

        def read_xml(name):
            info = zf.getinfo(name)
            if info.file_size > XLSX_MAX_ENTRY_BYTES:
                raise ValueError('文件内容异常（单条目过大）')
            raw = zf.read(name)
            # 拒绝 DOCTYPE/实体声明，防 XML 实体膨胀攻击
            head = raw[:4096]
            if b'<!DOCTYPE' in head or b'<!ENTITY' in head:
                raise ValueError('文件包含不支持的 XML 声明')
            return ET.fromstring(raw)

        shared = []
        if 'xl/sharedStrings.xml' in zf.namelist():
            root = read_xml('xl/sharedStrings.xml')
            ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for si in root.findall('a:si', ns):
                text = ''.join(t.text or '' for t in si.findall('.//a:t', ns))
                shared.append(text)
        sheet_names = [n for n in zf.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
        if not sheet_names:
            return []
        root = read_xml(sheet_names[0])
        ns = {'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for row_idx, row in enumerate(root.findall('.//a:sheetData/a:row', ns), start=1):
            values = []
            for cell in row.findall('a:c', ns):
                cell_type = cell.attrib.get('t')
                v = cell.find('a:v', ns)
                value = ''
                if cell_type == 'inlineStr':
                    value = ''.join(t.text or '' for t in cell.findall('.//a:t', ns))
                elif v is not None:
                    value = v.text or ''
                    if cell_type == 's':
                        try:
                            value = shared[int(value)]
                        except (ValueError, IndexError):
                            value = ''
                values.append(value)
            if not values or not ''.join(values).strip():
                continue
            if row_idx == 1 and any(v.strip() in ['姓名', 'name', '学生姓名'] for v in values):
                continue
            name = normalize_name(values[0] if values else '')
            group_raw = normalize_name(values[1] if len(values) > 1 else 'A')
            group = 'B' if group_raw in ['B', 'b', '下半学期', '下半', '下'] else 'A'
            rows.append({'line': row_idx, 'name': name, 'group_name': group})
    return rows


def create_simple_xlsx(headers, rows, sheet_name='Sheet1'):
    """生成简单 xlsx 文件，避免额外依赖。"""
    def col_name(index):
        name = ''
        index += 1
        while index:
            index, rem = divmod(index - 1, 26)
            name = chr(65 + rem) + name
        return name

    all_rows = [headers] + rows
    sheet_rows = []
    for r_idx, row in enumerate(all_rows, start=1):
        cells = []
        for c_idx, value in enumerate(row):
            ref = f'{col_name(c_idx)}{r_idx}'
            value = html_escape(str(value if value is not None else ''))
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{html_escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml)
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', workbook_rels_xml)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    output.seek(0)
    return output.getvalue()
