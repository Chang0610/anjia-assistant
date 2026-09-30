"""Validate the browser's long-term user profile and model-suggested updates."""

import re
from datetime import date, timedelta
from time_utils import shanghai_today

FIELDS = (
    "name", "destination_city", "current_city", "company_city", "company_district", "company_location",
    "start_date", "move_deadline", "moving_budget", "monthly_rent_budget",
    "housing_handover_date", "planning_start_date", "full_process_deadline", "availability_constraints",
    "commute_preference", "shared_housing", "pets", "housing_preferences",
    "current_housing", "employment_type", "social_insurance",
    "medical_insurance", "housing_fund", "household_registration",
    "other_requirements",
)
FIELD_SET = set(FIELDS)


def clean_profile(raw):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("用户资料格式错误")
    result = {}
    for key, value in raw.items():
        if key not in FIELD_SET or not isinstance(value, str):
            continue
        trimmed = value.strip()
        if trimmed:
            result[key] = trimmed[:1500 if key == "other_requirements" else 300]
    return result


def merge_profile(current, updates):
    result = dict(current)
    if not isinstance(updates, list):
        return result
    for item in updates:
        if not isinstance(item, dict) or item.get("field") not in FIELD_SET:
            continue
        value = item.get("value")
        if value is None or value == "":
            result.pop(item["field"], None)
        elif isinstance(value, str):
            result[item["field"]] = value.strip()[:1500 if item["field"] == "other_requirements" else 300]
    return result


def _parsed_date(value, today):
    match = re.fullmatch(r"(?:(20\d{2})[年/-])?(0?[1-9]|1[0-2])[月/-](0?[1-9]|[12]\d|3[01])[日号]?", value or "")
    if not match:
        return None
    try:
        return date(int(match.group(1) or today.year), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def explicit_profile_updates(message, today=None):
    """Catch unambiguous core facts if the model omits them."""
    if not isinstance(message, str):
        return []
    today = today or shanghai_today()
    updates = []
    date_pattern = r"(?<![\d/-])((?:20\d{2}[年/-])?(?:0?[1-9]|1[0-2])[月/-](?:0?[1-9]|[12]\d|3[01])[日号]?)(?![\d/-])"
    before = re.search(date_pattern + r"[^。；，,？！?!\n\d]{0,8}入职", message)
    after = re.search(r"入职(?:时间|日期)[^。；，,？！?!\n\d]{0,8}" + date_pattern, message)
    start_date = before.group(1) if before else after.group(1) if after else None
    if start_date:
        updates.append({"field": "start_date", "value": start_date})
    move_before = re.search(date_pattern + r"[^。；，,？！?!\n\d]{0,12}(?:(?:完成)?搬家|搬入|入住)", message)
    move_after = re.search(r"(?:搬家(?:完成)?(?:时间|日期)?|完成搬家|搬入|入住)[^。；，,？！?!\n\d]{0,12}" + date_pattern, message)
    move_deadline = move_before.group(1) if move_before else move_after.group(1) if move_after else None
    if move_deadline:
        updates.append({"field": "move_deadline", "value": move_deadline})
    handover_changed = re.search(r"交房[^。；\n]{0,30}?(?:改到|延期至|调整到|延到|推迟到)\s*" + date_pattern, message)
    handover_before = re.search(date_pattern + r"[^。；，,？！?!\n\d]{0,8}交房", message)
    handover_after = re.search(r"交房(?:日期|时间|日)?[^。；，,？！?!\n\d]{0,14}" + date_pattern, message)
    handover_date = handover_changed.group(1) if handover_changed else handover_before.group(1) if handover_before else handover_after.group(1) if handover_after else None
    if handover_date:
        updates.append({"field": "housing_handover_date", "value": handover_date})
    if re.search(r"已(?:经)?找到房子|已(?:经)?确定住处|房东说交房|(?:已经|已)交房完成|交房(?:已|已经)完成", message):
        updates.append({"field": "current_housing", "value": message.strip()})
    if re.search(r"周末[^\n]{0,10}只有半天|半天[^\n]{0,10}有空", message):
        updates.append({"field": "availability_constraints", "value": "周末仅半天可用，约3–4小时"})
    planning_match = re.search(date_pattern + r"[^。；，,？！?!\n\d]{0,10}开始规划", message)
    if not planning_match:
        planning_match = re.search(r"今天[（(]?\s*" + date_pattern + r"\s*[）)]?[^\n]{0,10}开始规划", message)
    planning_raw = planning_match.group(1) if planning_match else None
    planning_day = _parsed_date(planning_raw, today)
    if planning_day:
        updates.append({"field": "planning_start_date", "value": planning_day.isoformat()})
        duration = re.search(r"(\d{1,2})\s*(周|天)内完成(?:搬家)?全流程", message)
        if duration:
            days = int(duration.group(1)) * (7 if duration.group(2) == "周" else 1)
            updates.append({"field": "full_process_deadline", "value": (planning_day + timedelta(days=days)).isoformat()})
    return updates


def has_explicit_handover_date(message):
    """A move-in date alone must never become a confirmed handover fact."""
    return any(item["field"] == "housing_handover_date" for item in explicit_profile_updates(message))
