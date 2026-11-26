import csv
import hashlib
import io
import json
import math


def parse_csv(contents, columns):
    keys = [field["key"] for field in columns]
    try:
        reader = csv.DictReader(io.StringIO(contents.lstrip("\ufeff"), newline=""), strict=True)
        if reader.fieldnames != keys:
            raise ValueError(f"CSV 表头应按此顺序填写：{', '.join(keys)}")
        rows = []
        seen = set()
        for line, record in enumerate(reader, start=2):
            if len(rows) == 5000:
                raise ValueError("每份数据最多 5,000 条。")
            if None in record or None in record.values():
                raise ValueError(f"第 {line} 行列数与表头不符。")
            converted = {field["key"]: coerce(record[field["key"]].strip(), field, line) for field in columns}
            sample = converted["sample_id"]
            if sample in seen:
                raise ValueError(f"第 {line} 行样本编号重复：{sample}")
            seen.add(sample)
            rows.append(converted)
    except csv.Error as exc:
        raise ValueError(f"CSV 格式错误：{exc}") from exc
    if not rows:
        raise ValueError("CSV 至少需要一条记录。")
    return rows


def coerce(value, field, line):
    label = f"第 {line} 行「{field['label']}」"
    if not value:
        if field.get("optional"):
            return None
        raise ValueError(f"{label}不能为空。")
    if field["type"] == "text":
        if len(value) > 120:
            raise ValueError(f"{label}最多 120 字符。")
        if field.get("choices") and value not in field["choices"]:
            raise ValueError(f"{label}应为 {' / '.join(field['choices'])}。")
        return value
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{label}应为数字。") from exc
    if not math.isfinite(number) or number < field.get("min", -math.inf) or number > field.get("max", math.inf):
        raise ValueError(f"{label}超出允许范围。")
    return 0.0 if number == 0 else number


def digest(rows):
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def spreadsheet_safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def render_csv(rows, keys, protect=False):
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, keys)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: spreadsheet_safe(row[key]) if protect else row[key] for key in keys})
    return target.getvalue()
