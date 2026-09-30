"""Validate and merge calendar proposals without mutating confirmed state."""

from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from time_utils import shanghai_today

MAX_EVENTS = 40
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
REMINDER_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise ValueError("日程日期格式错误")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("日程日期无效") from error
    return value


def _time(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not TIME_RE.fullmatch(value):
        raise ValueError("日程时间格式错误")
    return value


def _reminder(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not REMINDER_RE.fullmatch(value):
        raise ValueError("提醒时间格式错误")
    _date(value[:10])
    return value


def _short(value, limit):
    if not isinstance(value, str):
        raise ValueError("日程文本格式错误")
    return value.strip()[:limit]


def _title_key(value):
    return re.sub(r"[\s\u3000，。、“”‘’：:；;（）()、/·-]", "", value or "").lower()


def _task_kind(title):
    """Return a conservative semantic group for tasks that should share one plan item."""
    value = _title_key(title)
    groups = (
        ("rental_online_signing", ("租赁网签", "合同网签")),
        ("rental_filing", ("租赁备案", "合同备案")),
        ("electricity_handover", ("水电", "用电", "电表", "电力")),
        ("gas_handover", ("燃气", "燃气表")),
        ("water_handover", ("用水", "水表")),
        ("old_home_handover", ("旧住处交接", "旧住处退租", "退租交接", "钥匙交接")),
        ("old_home_inspection", ("旧住处验房", "退租验房")),
        ("housing_screening", ("筛选房源", "房源筛选", "租房筛选", "筛选住房")),
        ("housing_viewing", ("实地看房", "预约看房", "看房")),
        ("rental_contract", ("租赁签约", "租房签约", "确认住所")),
        ("move_preparation", ("搬家安排", "搬家车辆", "搬运报价", "入住条件")),
        ("move_completion", ("完成搬家", "搬入新住处", "新住所入住")),
        ("onboarding_medical", ("入职体检", "体检要求", "体检机构")),
        ("hr_onboarding", ("hr确认入职", "报到地点", "入职信息")),
        ("broadband", ("宽带", "网络")),
        ("housing_fund", ("公积金",)),
        ("social_insurance", ("社保",)),
        ("medical_insurance", ("医保",)),
        ("residency_registration", ("居住登记",)),
        ("residence_permit", ("居住证",)),
    )
    for group, keywords in groups:
        if any(keyword in value for keyword in keywords):
            return group
    return None


def _event_difference(existing, proposed):
    """Return fields a duplicate add would change on an existing event."""
    changed = []
    if _title_key(existing.get("title")) != _title_key(proposed.get("title")):
        changed.append("title")
    fields = ("start_date", "due_date", "due_time", "reminder_at", "detail", "kind", "date_basis", "source_note", "sources")
    changed.extend(field for field in fields if existing.get(field) != proposed.get(field))
    return changed


def _clarification(existing, proposed, status="confirmed"):
    return {
        "existing_status": status,
        "existing_id": existing["id"],
        "existing_title": existing["title"],
        "existing_date": existing.get("due_date"),
        "proposed_title": proposed["title"],
        "proposed_date": proposed.get("due_date"),
        "different_fields": _event_difference(existing, proposed),
    }


def clean_sources(raw):
    if not isinstance(raw, list):
        return []
    result = []
    for source in raw[:5]:
        if not isinstance(source, dict):
            continue
        url = source.get("source_url", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            url = ""
        result.append({
            "source_name": _short(str(source.get("source_name") or "信息待确认"), 120),
            "source_url": url[:1000],
            "source_status": _short(str(source.get("source_status") or "信息待确认"), 120),
            "verified_at": _short(str(source.get("verified_at") or ""), 40),
        })
    return result


def clean_event(raw):
    if not isinstance(raw, dict):
        raise ValueError("日程事件格式错误")
    event_id = raw.get("id")
    if not isinstance(event_id, str) or not ID_RE.fullmatch(event_id):
        raise ValueError("日程 ID 格式错误")
    title = _short(raw.get("title"), 80)
    if not title:
        raise ValueError("日程标题不能为空")
    due_date = _date(raw.get("due_date"))
    start_date = _date(raw.get("start_date", due_date))
    if start_date and due_date and start_date > due_date:
        raise ValueError("起始日期不能晚于终止日期")
    return {
        "id": event_id,
        "title": title,
        "start_date": start_date,
        "due_date": due_date,
        "due_time": _time(raw.get("due_time")),
        "reminder_at": _reminder(raw.get("reminder_at")),
        "detail": _short(raw.get("detail", ""), 300),
        "kind": raw.get("kind") if raw.get("kind") in ("task", "deadline") else "task",
        "hard_deadline": raw.get("hard_deadline") is True,
        "date_basis": raw.get("date_basis") if raw.get("date_basis") in ("用户明确", "建议日期", "日期待确认") else "日期待确认",
        "source_note": _short(raw.get("source_note", "信息待确认"), 400),
        "sources": clean_sources(raw.get("sources", [])),
        "depends_on_ids": [value for value in raw.get("depends_on_ids", []) if isinstance(value, str) and ID_RE.fullmatch(value) and value != event_id][:12] if isinstance(raw.get("depends_on_ids", []), list) else [],
        "done": raw.get("done") is True,
    }


def clean_events(raw):
    if not isinstance(raw, list) or len(raw) > MAX_EVENTS:
        raise ValueError("日程数量超出限制")
    events = [clean_event(item) for item in raw]
    if len({item["id"] for item in events}) != len(events):
        raise ValueError("日程 ID 重复")
    return events


def clean_calendar(raw):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("日历状态格式错误")
    confirmed = clean_events(raw.get("confirmed", []))
    pending_raw = raw.get("pending")
    pending = clean_events(pending_raw) if pending_raw is not None else None
    return {"confirmed": confirmed, "pending": pending}


def _from_operation(op, event_id, done=False, previous=None):
    previous = previous or {}
    due_date = op.get("due_date")
    reminder_at = op.get("reminder_at", previous.get("reminder_at"))
    if (reminder_at and reminder_at == previous.get("reminder_at") and previous.get("due_date")
            and due_date and due_date != previous["due_date"]):
        reminder_at = _shift_date(reminder_at[:10], (date.fromisoformat(due_date) - date.fromisoformat(previous["due_date"])).days) + reminder_at[10:]
    start_date = op.get("start_date") or previous.get("start_date") or due_date
    if previous.get("due_date") and previous.get("start_date") == previous.get("due_date") and due_date != previous.get("due_date") and not op.get("start_date"):
        start_date = due_date
    keep_manual_range = event_id.startswith("m_") and previous.get("start_date") != previous.get("due_date") and not op.get("start_date")
    if op.get("date_basis") == "建议日期" and not keep_manual_range:
        start_date = due_date
    return clean_event({
        "id": event_id,
        "title": op.get("title", ""),
        "start_date": start_date,
        "due_date": due_date,
        "due_time": op.get("due_time"),
        "reminder_at": reminder_at,
        "detail": op.get("detail", ""),
        "kind": op.get("kind", "task"),
        "hard_deadline": (op.get("hard_deadline", previous.get("hard_deadline", False)) if previous.get("hard_deadline") or op.get("date_basis") != "建议日期" else False),
        "date_basis": op.get("date_basis", "日期待确认"),
        "source_note": op.get("source_note", "信息待确认"),
        "sources": op.get("sources", previous.get("sources", [])),
        "depends_on_ids": op.get("depends_on_ids", previous.get("depends_on_ids", [])),
        "done": done,
    })


def _changes(previous, candidate):
    """Describe only the delta between the current proposal base and candidate."""
    old = {item["id"]: item for item in previous}
    new = {item["id"]: item for item in candidate}
    changed = []
    for item in candidate:
        before = old.get(item["id"])
        if before is None:
            changed.append({"id": item["id"], "type": "新增", "title": item["title"]})
        elif before != item:
            changed.append({"id": item["id"], "type": "修改", "title": item["title"]})
    for item in previous:
        if item["id"] not in new:
            changed.append({"id": item["id"], "type": "删除", "title": item["title"]})
    return changed


def _shift_date(value, days):
    if not value:
        return value
    return (date.fromisoformat(value) + timedelta(days=days)).isoformat()


def _profile_date(value, today):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(?:(20\d{2})[年/-])?(0?[1-9]|1[0-2])[月/-](0?[1-9]|[12]\d|3[01])[日号]?\s*", value)
    if not match:
        return None
    year = int(match.group(1) or today.year)
    try:
        return date(year, int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def _apply_planning_constraints(candidate, touched_ids, profile, today):
    """Enforce explicit target dates on model-touched relocation events."""
    move_target = _profile_date((profile or {}).get("move_deadline"), today)
    handover_target = _profile_date((profile or {}).get("housing_handover_date"), today)
    full_target = _profile_date((profile or {}).get("full_process_deadline"), today)
    today_key = today.isoformat()
    for event in candidate:
        if event["id"] not in touched_ids:
            continue
        title = _title_key(event["title"])
        completion = any(word in title for word in ("完成搬家", "搬入新住处", "新住所入住")) and not any(word in title for word in ("确认", "安排", "条件"))
        preparation = any(word in title for word in ("搬家安排", "入住条件", "旧住处交接"))
        if move_target and completion and event.get("date_basis") != "用户明确":
            # 交房延期已把该事项推至新交房日时，不用旧的搬家资料日期
            # 将其重新拉回交房之前。
            if not (handover_target and move_target < handover_target and event.get("due_date") and event["due_date"] >= handover_target):
                event["start_date"] = move_target
                event["due_date"] = move_target
                event["date_basis"] = "用户明确"
        elif move_target and preparation and event.get("date_basis") == "建议日期" and event.get("due_date"):
            safe_date = min(max(event["due_date"], today_key), move_target)
            event["due_date"] = safe_date
            event["start_date"] = safe_date
        if handover_target and "交房" in title and "交房前" not in title:
            event["start_date"] = handover_target
            event["due_date"] = handover_target
            event["date_basis"] = "用户明确"
        actual_service = any(word in title for word in ("宽带安装", "已预约搬家服务", "搬入新住处", "入住交接"))
        if handover_target and actual_service and event.get("due_date") and event["due_date"] < handover_target:
            event["start_date"] = handover_target
            event["due_date"] = handover_target
        if full_target and "全流程" in title and "里程碑" in title:
            event["start_date"] = full_target
            event["due_date"] = full_target
            event["date_basis"] = "用户明确"


def _operation(action, event=None, *, title="", due_date=None, due_time=None, reminder_at=None, detail="", date_basis="日期待确认", source_note="信息待确认", sources=None):
    event = event or {}
    return {
        "action": action,
        "id": event.get("id", ""),
        "title": title or event.get("title", ""),
        "due_date": due_date if due_date is not None else event.get("due_date"),
        "due_time": due_time if due_time is not None else event.get("due_time"),
        "reminder_at": reminder_at if reminder_at is not None else event.get("reminder_at"),
        "detail": detail or event.get("detail", ""),
        "kind": event.get("kind", "task"),
        "date_basis": date_basis or event.get("date_basis", "日期待确认"),
        "source_note": source_note or event.get("source_note", "信息待确认"),
        "sources": sources if sources is not None else event.get("sources", []),
        "depends_on_ids": event.get("depends_on_ids", []),
        "hard_deadline": event.get("hard_deadline", False),
    }


def _delete_all_requested(message):
    text = re.sub(r"\s+", "", message or "")
    if any(word in text for word in ("不要删除", "别删除", "不要清空", "别清空", "不删除所有")):
        return False
    return bool(re.search(r"(?:删除|清空|移除)(?:当前|现有|我的|日历中|计划日历中|待确认或已确认)?(?:所有|全部|整个)(?:计划|日程|待办|事项)|(?:把|将)?(?:所有|全部)(?:计划|日程|待办|事项)(?:都|全部)?(?:删除|清空|移除)", text))


def _initial_plan_requested(message):
    value = re.sub(r"\s+", "", message or "")
    if re.search(r"(?:不要|别|无需|不用)(?:生成|制定|安排|规划).{0,8}(?:计划|日程)", value):
        return False
    return bool(
        re.search(r"(?:生成|制定|做|给我|出)(?:一份|我的|完整的?)?(?:搬家|安家|完整)?(?:计划|日程|安排)|计划表|日程安排", value)
        or re.search(r"(?:根据|按照|基于).{0,12}(?:资料|信息|情况).{0,12}(?:如何安排|怎么安排|帮我安排|安排一下|规划一下)", value)
    )


def _pending_rejected(message):
    value = re.sub(r"\s+", "", message or "")
    return bool(re.search(r"不需要改动当前日程表|(?:算了|先别|暂时别|还是别)(?:，|,)?(?:先)?(?:别|不)?(?:改|调整|动|安排)|(?:不用|不要|取消|拒绝|撤销)(?:这次|当前|刚才|上述|待确认)?(?:的)?(?:日程)?(?:改动|修改|提议|草案|安排)|(?:保持|维持)(?:原|现有|当前)(?:计划|日程)(?:不变)?", value))


def _complete_first_plan(ops, profile, today):
    """Fill missing stages of a first plan without treating an unknown handover as fact."""
    titles = [item.get("title", "") for item in ops if item.get("action") == "add"]
    move = _profile_date((profile or {}).get("move_deadline"), today)
    hire = _profile_date((profile or {}).get("start_date"), today)
    if not (move and hire):
        return ops
    move_day, hire_day = date.fromisoformat(move), date.fromisoformat(hire)
    def add_if_missing(words, title, day, detail):
        if any(any(word in existing for word in words) for existing in titles):
            return
        ops.append(_operation("add", title=title, due_date=max(today, day).isoformat(), detail=detail,
                              date_basis="建议日期", source_note="根据用户搬家或入职目标倒排；具体办理条件和时间需自行核验。"))
        titles.append(title)

    if not (profile or {}).get("current_housing") and not (profile or {}).get("housing_handover_date"):
        add_if_missing(("区域", "房源筛选"), "筛选租住区域与房源范围", move_day - timedelta(days=10), "按公司位置、月租和通勤偏好筛选区域；挂牌租金及通勤仍需核验。")
        add_if_missing(("看房",), "看房并核验租约条件", move_day - timedelta(days=5), "自行核对房屋、费用、合同责任与入住条件。")
        add_if_missing(("签约", "租赁合同", "完成租房"), "核验租赁合同并完成签约", move_day - timedelta(days=3), "自行核对合同主体、租金、押金、交房日和退租条款。")
    add_if_missing(("交房", "可入住条件"), "确认新住所交房与可入住条件", move_day - timedelta(days=2), "向出租方核验实际交房日、钥匙和入住条件；此日期仅为建议核验日。")
    add_if_missing(("搬家安排", "搬家方案", "搬家服务"), "确认搬家方案与旧住处交接", move_day - timedelta(days=1), "核对搬运、旧房交接及新住所可进入时间。")
    add_if_missing(("完成搬家", "搬入", "新住所入住"), "搬入新住处并完成入住检查", move_day, "核对钥匙、房屋状态与物品搬运完成情况。")
    add_if_missing(("宽带", "网络"), "核验宽带安装条件", move_day - timedelta(days=1), "核验地址覆盖和安装时间；预约须自行确认。")
    add_if_missing(("水电", "燃气", "表读数"), "核对水电燃气交接", move_day, "入住时核对表读数、费用归属与房屋状态。")
    add_if_missing(("HR", "hr", "入职材料", "报到要求"), "向HR核验报到地点、材料与体检要求", hire_day - timedelta(days=3), "向单位核验报到和体检要求，不自行预约。")
    add_if_missing(("通勤试走", "试走通勤"), "通勤试走", hire_day - timedelta(days=1), "入职前按实际早高峰路线试走，核对到岗时间。")
    add_if_missing(("入职当天", "入职报到", "到岗入职"), "入职报到并核对单位参保安排", hire_day, "向HR确认报到、社保医保与公积金起缴安排。")
    add_if_missing(("居住登记",), "核验居住登记办理条件", move_day + timedelta(days=1), "入住后向官方入口核验适用条件、材料和办理方式。")
    return ops


def _move_change_requested(message):
    value = re.sub(r"\s+", "", message or "")
    return bool(re.search(r"(?:把|将)?(?:完成)?搬家(?:完成)?(?:时间|日期|日)?(?:改到|改为|调整到|推迟到|提前到|延到)", value))


def _explicit_move_target(message, today):
    """Read the date in an explicit move-date command, independent of profile updates."""
    value = re.sub(r"\s+", "", message or "")
    marker = re.search(r"(?:搬家(?:完成)?(?:时间|日期|日)?|完成搬家|搬入|入住)[^。；，,？！?!]{0,16}(?:改到|改为|调整到|推迟到|提前到|延到)", value)
    if not marker:
        return None
    dates = list(re.finditer(r"(?:(20\d{2})年)?(0?[1-9]|1[0-2])月((?:[12]\d|3[01]|0?[1-9]))日?", value[marker.end():]))
    if not dates:
        return None
    match = dates[-1]
    try:
        return date(int(match.group(1) or today.year), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def _accepted_move_after_hire(message):
    value = re.sub(r"\s+", "", message or "")
    return bool(re.search(r"(?:接受|确认|坚持|仍要|仍然要|决定|选择).{0,16}入职后.{0,8}搬家|入职后搬家.{0,12}(?:确认|可以|接受|就这样)", value))


def augment_model_result(calendar_state, model_result, profile, latest_message, today=None):
    """Add deterministic operations for facts that invalidate an existing plan."""
    today = today or shanghai_today()
    result = dict(model_result)
    ops = [dict(item) for item in result.get("operations", []) if isinstance(item, dict)]
    base = calendar_state["pending"] if calendar_state["pending"] is not None else calendar_state["confirmed"]

    if calendar_state["pending"] is not None and _pending_rejected(latest_message):
        result.update({"response_mode": "C", "calendar_intent": "none", "operations": [],
                       "advice_items": [], "follow_ups": [], "quick_choices": [],
                       "clear_pending": True,
                       "answer": "已撤销待确认的日程改动，已确认的计划日历保持原样。"})
        return result

    # “请安排”有可能是新增，也有可能是改已有搬家事项；未明确要求改期时先确认意图。
    message = latest_message or ""
    if re.search(r"(?:请|帮我)?安排.{0,20}搬家|(?:请|帮我)?安排.{0,20}入住", message) and not _move_change_requested(message):
        existing_move = next((item for item in base if not item.get("done") and any(word in item.get("title", "") for word in ("完成搬家", "搬入新住处", "新住所入住"))), None)
        mentioned_date = re.search(r"(?:20\d{2}年)?\d{1,2}月\d{1,2}日", message)
        if existing_move and mentioned_date:
            result.update({"response_mode": "E", "calendar_intent": "none", "operations": [],
                           "advice_items": [], "follow_ups": [], "quick_choices": [],
                           "suppress_profile_fields": ["move_deadline"],
                           "answer": f"当前已有“{existing_move['title']}”日程（{existing_move.get('due_date') or '日期待确认'}）。你是要把这项日程改到{mentioned_date.group()}，还是另外新增一项搬家事项？确认前不会改变现有计划。"})
            return result

    if _delete_all_requested(latest_message):
        confirmed = calendar_state["confirmed"]
        pending = calendar_state["pending"] or []
        unique = {item["id"]: item for item in confirmed + pending}
        result.update({
            "response_mode": "D",
            "calendar_intent": "propose" if unique else "none",
            "operations": [_operation("delete", item) for item in unique.values()],
            "delete_all": bool(unique),
            "advice_items": [],
            "follow_ups": [],
            "quick_choices": [],
            "answer": f"这次拟删除已确认日程中的{len(confirmed)}项" + (f"，并撤销待确认草案中的{len([item for item in pending if item['id'] not in {event['id'] for event in confirmed}])}项新增事项" if pending else "") + "。请核对下方清单；确认前计划日历不会改变。" if unique else "当前没有可删除的计划日程。",
        })
        return result

    # 首次完成信息采集后，模型偶尔只返回文字而遗漏 operations。为避免
    # 用户看到“计划生成失败”，用用户明确提供的日期生成一版待确认草案。
    # 这只是提议，不会绕过前端确认直接写入日历。
    plan_request = _initial_plan_requested(latest_message)
    empty_calendar = not calendar_state["confirmed"] and not calendar_state["pending"]
    if plan_request and empty_calendar and ops:
        result["response_mode"] = "B"
        result["calendar_intent"] = "propose"
    if plan_request and empty_calendar and not ops:
        move_target = _profile_date((profile or {}).get("move_deadline"), today)
        hire_target = _profile_date((profile or {}).get("start_date"), today)
        if move_target or hire_target:
            move_day = date.fromisoformat(move_target) if move_target else None
            hire_day = date.fromisoformat(hire_target) if hire_target else None
            if move_day:
                ops.append(_operation("add", title="确认租住区域与租房预算", due_date=max(today, move_day - timedelta(days=7)).isoformat(), detail="按公司位置、通勤时间和月租预算确定可重点了解的区域；区域租金与通勤数据需再次核验。", date_basis="建议日期", source_note="依据用户搬家完成日期倒排；区域匹配信息待确认。"))
                ops.append(_operation("add", title="完成看房、核验租房细节并签约", due_date=max(today, move_day - timedelta(days=3)).isoformat(), detail="确认房屋条件、租约责任、实际费用及入住安排。", date_basis="建议日期", source_note="依据用户计划完成搬家时间倒排；具体房源信息待确认。"))
                ops.append(_operation("add", title="确认搬家安排与旧住处交接", due_date=max(today, move_day - timedelta(days=1)).isoformat(), detail="确认搬运方式、旧住处退租交接和新住处入住条件。", date_basis="建议日期", source_note="依据用户计划完成搬家时间倒排；旧合同条款需核验。"))
                ops.append(_operation("add", title="搬入新住处并完成入住检查", due_date=move_day.isoformat(), detail="核对钥匙、水电燃气表读数、房屋状态和网络安装条件。", date_basis="用户明确", source_note="日期来自用户保存的计划完成搬家时间。"))
                ops.append(_operation("add", title="核验宽带安装与水电燃气交接", due_date=move_day.isoformat(), detail="自行核验地址覆盖、安装时间、表具读数和费用归属。", date_basis="建议日期", source_note="依据入住日期安排；具体服务入口和资费待核验。"))
                ops.append(_operation("add", title="核验居住登记办理要求", due_date=max(today, move_day + timedelta(days=1)).isoformat(), detail="入住后核验上海居住登记办理条件、材料和官方入口，再自行办理。", date_basis="建议日期", source_note="具体适用条件和办理入口以官方渠道核验为准。"))
            if hire_day:
                ops.append(_operation("add", title="向HR确认入职地点、材料与体检要求", due_date=max(today, hire_day - timedelta(days=3)).isoformat(), detail="向单位核对报到地点、所需材料、是否要求体检及办理方式。", date_basis="建议日期", source_note="依据用户保存的入职日期倒排；具体要求由用人单位确认。"))
                ops.append(_operation("add", title="到岗入职并核对单位参保、公积金", due_date=hire_day.isoformat(), detail="向单位确认社保登记、医保缴费和公积金起缴安排。", date_basis="用户明确", source_note="日期来自用户保存的入职时间。"))
                ops.append(_operation("add", title="核对社保医保与公积金缴存状态", due_date=(hire_day + timedelta(days=30)).isoformat(), detail="核对单位实际办理及缴存情况；具体起缴月份和查询入口向HR及官方渠道确认。", date_basis="建议日期", source_note="按入职日期安排一次核对提醒；实际政策时限及适用性待官方核验。"))
            result["response_mode"] = "B"
            result["calendar_intent"] = "propose"
            result["advice_items"] = []
            result["follow_ups"] = []
            result["operations"] = ops
            result["answer"] = "目前信息总结：已根据保存的入职和搬家日期整理第一版安家计划。以下日期为待确认建议，请核对下方清单；确认前不会写入计划日历。"

    if empty_calendar and ops and (plan_request or result.get("response_mode") == "B"):
        result["operations"] = _complete_first_plan(ops, profile, today)
        result["quick_choices"] = []
        result["follow_ups"] = [
            question for question in result.get("follow_ups", [])
            if isinstance(question, str) and not re.search(r"(?:是否|要不要|需不需要)[^。！？\n]{0,60}(?:生成|制定|安排)[^。！？\n]{0,15}(?:计划|日程)", question)
        ]
        result["answer"] = re.sub(
            r"(?:请确认)?(?:是否|要不要|需不需要)[^。！？\n]{0,60}(?:生成|制定|安排)[^。！？\n]{0,15}(?:计划|日程)[。！？?]?",
            "", str(result.get("answer", "")),
        ).strip()

    completion_signal = re.search(r"(?:已经|已|刚刚|刚)\s*(?:搬好家|搬完家|完成搬家|入住了|搬家完成)", latest_message or "")
    delete_confirmed = re.search(r"(?:已完成|已经完成|完成了)[^\n]{0,20}(?:删除|移除)|(?:删除|移除)[^\n]{0,20}(?:已完成|已经完成)", latest_message or "")
    if completion_signal and not delete_confirmed:
        affected_words = ("搬家", "搬入", "入住", "找房", "看房", "租住区域", "租赁签约", "网签备案", "水电气交接", "搬家安排", "可入住条件", "旧住处", "退租", "收尾", "盘点物品", "搬运条件")
        affected_events = [event for event in base if not event.get("done") and (any(word in event.get("title", "") for word in affected_words) or any(word in event.get("detail", "") for word in ("盘点物品", "搬运条件")))]
        result["response_mode"] = "D"
        result["calendar_intent"] = "propose" if affected_events else "none"
        result["operations"] = [_operation("delete", event, title="盘点物品并核对搬运条件" if any(word in event.get("detail", "") for word in ("盘点物品", "搬运条件")) else event.get("title", "")) for event in affected_events]
        result["quick_choices"] = []
        result["answer"] = "你提到搬家已经完成。请先确认是否要从计划日历中移除以下已完成的搬家相关安排："
        return result
    if delete_confirmed:
        affected_words = ("搬家", "搬入", "入住", "找房", "看房", "租住区域", "租赁签约", "网签备案", "水电气交接", "搬家安排", "可入住条件", "旧住处", "退租", "收尾", "盘点物品", "搬运条件")
        removed = [event for event in base if not event.get("done") and (any(word in event.get("title", "") for word in affected_words) or any(word in event.get("detail", "") for word in ("盘点物品", "搬运条件")))]
        if removed:
            result["response_mode"] = "D"
            result["calendar_intent"] = "propose"
            ops = [item for item in ops if item.get("id") not in {event.get("id") for event in removed}]
            ops.extend(_operation("delete", event) for event in removed)
            result["operations"] = ops
            result["answer"] = "已确认搬家相关事项完成。下面仅列出将从计划日历中移除的已完成安排；后续仍需办理的入职、社保、公积金等事项会保留。"

    # 交房完成只说明住所已可进入，不能误当作“搬家完成”。旧找房任务
    # 提议移除，后续事项按交房事实解锁；历史已完成事项继续保留。
    if re.search(r"(?:已经|已)交房完成|交房(?:已|已经)完成|(?:已经|已)完成交房", latest_message or ""):
        search_words = ("找房", "看房", "筛选房源", "区域参考", "租房注意", "租住区域")
        result["response_mode"] = "D"
        ops = []
        for event in base:
            if not event.get("done") and any(word in event["title"] for word in search_words):
                ops = [item for item in ops if item.get("id") != event["id"]]
                ops.append(_operation("delete", event))
        handover = _profile_date((profile or {}).get("housing_handover_date"), today)
        ready = max(today.isoformat(), handover or today.isoformat())
        follow_up = (date.fromisoformat(ready) + timedelta(days=1)).isoformat()
        unlocked = (
            ("核验网络安装条件", ready, "核验地址覆盖、入户安装条件和可用时间；预约需自行确认。", ("网络", "宽带")),
            ("确认搬家方案和服务时间", ready, "核对搬运方式、车辆、电梯与停车条件；自行向服务方确认。", ("搬家安排", "搬家方案", "搬家服务")),
            ("搬入并核对水电燃气交接", follow_up, "记录水电燃气表读数、费用归属和房屋状态。", ("搬入", "入住交接", "水电交接", "完成搬家", "搬家完成")),
            ("核验居住登记办理条件", follow_up, "入住后按住所类型核验材料、条件及官方办理入口。", ("居住登记",)),
        )
        for title, due, detail, equivalent in unlocked:
            existing = next((event for event in base if not event.get("done") and any(word in event["title"] for word in equivalent)), None)
            if existing:
                if existing.get("due_date") and existing["due_date"] < due and not existing.get("hard_deadline") and not any(word in existing["title"] for word in ("已预约", "已预订")):
                    ops.append(_operation("update", existing, due_date=due, detail=existing.get("detail", "") + "；交房完成后方可执行。", date_basis="建议日期", source_note="依据已完成交房日重排；执行条件需自行核验。"))
                continue
            if any(item.get("action") == "add" and any(word in item.get("title", "") for word in equivalent) for item in ops):
                continue
            ops.append(_operation("add", title=title, due_date=due, detail=detail, date_basis="建议日期", source_note="依据用户已完成交房安排后续核验；具体服务时间和办理条件需自行确认。"))
        result.update({
            "calendar_intent": "propose" if ops else "none", "operations": ops,
            "advice_items": [], "follow_ups": [],
            "answer": "已记录交房完成。下方提议移除不再需要的找房事项，并安排网络、水电交接、搬家及入住后的居住登记核验；请核对后确认，计划日历在确认前不会改变。" if ops else "交房后的找房清理及后续任务已在现有计划或待确认清单中，没有新增变更。",
        })
        return result

    # 提醒属于“我的”页面的设置项，不作为日程变更提议，避免在问答页
    # 出现计划清单确认卡片。微信提醒也只能在具备订阅能力后由设置页处理。
    if "提醒" in (latest_message or "") and re.search(r"(?:改|设置|设为|提前)", latest_message or ""):
        message = latest_message or ""
        matches = [event for event in base if not event.get("done") and (
            event["title"] in message or
            ("搬家" in message and any(word in event["title"] for word in ("完成搬家", "搬入新住处"))) or
            ("向单位确认入职" in message and "向单位确认入职" in event["title"])
        )]
        if len(matches) == 1:
            event = matches[0]
            target = re.search(r"(?:(20\d{2})[年/-])?(\d{1,2})[月/-](\d{1,2})日?", message)
            offset = re.search(r"提前([一二三四五六七八九十\d]+)天", message)
            hour = re.search(r"(?:上午|早上|下午|晚上)?\s*(\d{1,2})\s*[点时](?:\s*(\d{1,2})分?)?", message)
            if target:
                year = int(target.group(1) or (event.get("due_date") or today.isoformat())[:4])
                try:
                    reminder_day = date(year, int(target.group(2)), int(target.group(3)))
                except ValueError:
                    reminder_day = None
            elif offset and event.get("due_date"):
                days = int(offset.group(1)) if offset.group(1).isdigit() else {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7}.get(offset.group(1))
                reminder_day = date.fromisoformat(event["due_date"]) - timedelta(days=days) if days is not None else None
            else:
                reminder_day = None
            if reminder_day:
                reminder_hour = int(hour.group(1)) if hour else 9
                if hour and re.search(r"下午|晚上", message) and reminder_hour < 12:
                    reminder_hour += 12
                reminder_minute = int(hour.group(2) or 0) if hour else 0
                if reminder_hour <= 23 and reminder_minute <= 59:
                    reminder_at = f"{reminder_day.isoformat()}T{reminder_hour:02d}:{reminder_minute:02d}"
                    changed_task_date = bool(target and re.search(r"(?:任务|事项).{0,8}改到|改到.{0,20}提醒", message))
                    result.update({
                        "response_mode": "C", "calendar_intent": "none", "quick_choices": [],
                        "operations": [], "advice_items": [], "follow_ups": [],
                        "answer": f"提醒设置不能在问答中直接修改。请到“我的”→“提醒设置”，自行调整“{event['title']}”的提醒时间。当前仅支持打开页面时显示站内提醒，微信订阅和后台推送尚未接入。",
                    })
                    return result

    # 全局提醒偏好及尚未接入的微信提醒仍引导到设置页。
    if "提醒" in (latest_message or "") and re.search(r"(?:改|设置|设为|开启|打开|关闭|提前)", latest_message or ""):
        result.update({
            "response_mode": "C", "calendar_intent": "none", "operations": [],
            "advice_items": [], "follow_ups": [],
            "answer": "提醒设置目前在“我的－提醒设置”中保存，聊天不能修改单个事项的提醒时间或后台调度。站内提醒只会在打开小程序页面时显示；微信提醒尚未接入，不能在这里开通或发送。请到提醒设置查看可调整的全局提醒时间。",
        })
        return result

    # 月租数额不说明是否包含水电、网络等经常性费用。区域结论前
    # 先问清预算口径，避免把抽样租金当成可负担总费用。
    region_question = re.search(r"(?:哪些|哪个|什么).{0,12}区域|区域.{0,12}(?:适合|推荐)|住哪里", latest_message or "")
    budget_available = re.search(r"(?:租金|月租|租房预算).{0,8}\d{3,5}|\d{3,5}.{0,8}(?:租金|月租)", latest_message or "") or (profile or {}).get("monthly_rent_budget")
    if region_question and budget_available:
        scope_known = re.search(r"(?:只算|仅含|不含|包含|包括|含).{0,12}(?:水电|网费|物业|杂费|房租|租金)", latest_message or "")
        scope_saved = re.search(r"(?:只算|仅含|不含|包含|包括|含).{0,12}(?:水电|网费|物业|杂费)", str((profile or {}).get("monthly_rent_budget", "")))
        if not scope_known and not scope_saved:
            questions = ["你的月预算是只算房租，还是包含水电、网费和物业等费用？"]
            if not (profile or {}).get("shared_housing") and not re.search(r"合租|整租", latest_message or ""):
                questions.append("你接受合租，还是只考虑整租？")
            result.update({
                "response_mode": "C", "calendar_intent": "none", "operations": [],
                "advice_items": [], "follow_ups": questions,
                "answer": "目前信息总结：已收到你的租金上限。区域匹配还需要确认预算口径；不同房源的水电、网络和物业费用可能另计。\n" + "\n".join(questions),
            })
            return result

    # 用户明确要求将搬家推到已知入职日之后时，先提供处理方向。
    # 只有其后明确选择接受该方案，才继续生成改期提议。
    if _move_change_requested(latest_message) and not _accepted_move_after_hire(latest_message):
        move_target = _profile_date((profile or {}).get("move_deadline"), today)
        hire_target = _profile_date((profile or {}).get("start_date"), today)
        if move_target and hire_target and move_target > hire_target:
            previous_day = (date.fromisoformat(hire_target) - timedelta(days=1)).isoformat()
            result.update({
                "response_mode": "E", "calendar_intent": "none", "operations": [],
                "advice_items": [], "follow_ups": [],
                "quick_choices": [f"把搬家提前到{previous_day}", f"接受入职后搬家（目标{move_target}），核验过渡条件"],
                "answer": f"搬家完成目标{move_target}晚于入职日{hire_target}，可能影响报到前通勤、住所和物品安排。请选择：一、提前搬家到入职前；二、接受入职后搬家，并先核验过渡住所与通勤条件。选择后再生成待确认的日程变更。",
            })
            return result

    # 冲突选项带回明确日期后，也必须形成真正的待确认 update。
    # 同时兜住模型只写文字、不输出 operations 的情况。
    explicit_move_choice = _move_change_requested(latest_message) or _accepted_move_after_hire(latest_message)
    explicit_target = _explicit_move_target(latest_message, today)
    has_date = bool(re.search(r"(?:20\d{2}[年/-])?\d{1,2}[月/-]\d{1,2}[日号]?", latest_message or ""))
    if explicit_move_choice and (explicit_target or (_accepted_move_after_hire(latest_message) and has_date)):
        # Prefer the date in this explicit command. The profile may still contain
        # the previous target while the user is revising an existing pending draft.
        move_target = explicit_target or _profile_date((profile or {}).get("move_deadline"), today)
        move_events = [
            event for event in base if not event.get("done")
            and any(word in event["title"] for word in ("完成搬家", "搬家完成", "搬入新住处", "新住所入住"))
            and not any(word in event["title"] for word in ("安排", "服务", "改约"))
        ]
        if move_target and move_events:
            move_ids = {event["id"] for event in move_events}
            ops = [item for item in ops if item.get("id") not in move_ids]
            for event in move_events:
                if event.get("due_date") != move_target:
                    ops.append(_operation("update", event, due_date=move_target, date_basis="用户明确", source_note="用户明确选择的搬家目标日期；确认前不写入计划日历。"))
            hire_target = _profile_date((profile or {}).get("start_date"), today)
            if _accepted_move_after_hire(latest_message) and hire_target and move_target > hire_target:
                title = "核验入职后搬家期间的过渡住所与通勤"
                if not any(title == event["title"] and not event.get("done") for event in base):
                    due = max(today, date.fromisoformat(hire_target) - timedelta(days=1)).isoformat()
                    ops.append(_operation("add", title=title, due_date=due, detail="确认入职至正式搬入期间的住处、行李存放、到岗路线和费用；如需住宿或交通服务，由用户自行联系确认。", date_basis="建议日期", source_note="依据用户选择入职后搬家提出的风险核验，不代表已预订过渡住所。"))
            if ops:
                result["response_mode"] = "D"
                result["calendar_intent"] = "propose"
                result["answer"] = f"搬家完成目标拟调整为{move_target}；请同时核验入职到搬入期间的住处和通勤安排。请核对下方变更，确认前计划日历不会改变。"
                result["advice_items"] = []
                result["follow_ups"] = []

    # 入职日期是硬顺序约束：通勤试走必须发生在报到日前，不能随着原日期
    # 留在入职后。模型漏提或误排时，在确认表中补上确定的关联变更。
    hire_match = re.search(r"入职(?:日期|时间)?[^\n]{0,16}?(?:改到|改到了|改为|调整到|调整为|变更为)\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]?", latest_message or "")
    if hire_match:
        year = int(hire_match.group(1) or today.year)
        month, day = int(hire_match.group(2)), int(hire_match.group(3))
        try:
            hire_date = date(year, month, day)
        except ValueError:
            hire_date = None
        if hire_date:
            commute_date = (hire_date - timedelta(days=1)).isoformat()
            result["quick_choices"] = []
            answer_parts = [f"入职日期改为{hire_date.isoformat()}。以下仅列出需要调整的关联事项，确认前计划日历不会改变。"]
            commute_events = [event for event in base if "通勤试走" in event.get("title", "") and not event.get("done")]
            for event in commute_events:
                ops = [item for item in ops if item.get("id") != event.get("id")]
                if not event.get("due_date") or event["due_date"] >= hire_date.isoformat():
                    ops.append(_operation("update", event, due_date=commute_date, detail=event.get("detail", "") + "；入职日期变更后，通勤试走必须安排在入职日前。", date_basis="建议日期", source_note="入职日期变更后的前置安排。"))
                    answer_parts.append(f"通勤试走拟调整到入职前一天{commute_date}。")

            # 入职提前不等于每一项搬家安排都要重写。只有原有的“完成搬家”
            # 目标晚于新入职日时，才需要把它提前到入职前一天并出现在确认表。
            # 已经早于新入职日的目标是有效安排，既不修改，也不作为无变化项展示。
            move_events = [
                event for event in base
                if not event.get("done")
                and _task_kind(event.get("title", "")) == "move_completion"
                and event.get("due_date")
            ]
            moved_earlier = []
            stable_move_ids = set()
            for event in move_events:
                move_day = date.fromisoformat(event["due_date"])
                if move_day > hire_date:
                    target = commute_date
                    ops = [item for item in ops if item.get("id") != event["id"]]
                    ops.append(_operation(
                        "update", event, due_date=target,
                        detail=event.get("detail", "") + "；入职日期提前，搬家完成目标需调整到入职前。",
                        date_basis="建议日期", source_note="新入职日前完成搬家的顺序建议；确认前不写入计划日历。",
                    ))
                    moved_earlier.append(target)
                else:
                    stable_move_ids.add(event["id"])

            if stable_move_ids:
                # 模型可能会把无变化的搬家任务一并带入 operations；明确剔除，
                # 让确认表只保留实际变化的事项。
                ops = [
                    item for item in ops
                    if item.get("id") not in stable_move_ids
                    and not (
                        item.get("action") == "add"
                        and _task_kind(item.get("title", "")) == "move_completion"
                    )
                ]

            if moved_earlier:
                answer_parts.append(f"原搬家完成目标晚于新入职日，拟调整为{moved_earlier[0]}；请在下方确认。")
            elif move_events:
                answer_parts.append("现有搬家完成目标已早于新入职日，因此保持不变，不会出现在确认清单中。")
            result["answer"] = "\n".join(answer_parts)
            result["calendar_intent"] = "propose" if ops else "none"
            if ops:
                result["response_mode"] = "D"
                result["advice_items"] = []
                result["follow_ups"] = []

    # A request to move the relocation completion date must not silently rewrite
    # unrelated onboarding tasks that happen to be in the model's plan output.
    if re.search(r"搬家完成(?:时间|日)?.{0,20}(?:改到|调整|变更)", latest_message or ""):
        relocation_words = ("搬家", "搬入", "入住", "旧住处", "退租", "交接", "宽带", "网络", "水电", "燃气", "居住登记")
        related_ids = {
            event["id"] for event in base
            if any(word in event["title"] for word in relocation_words)
        }
        ops = [
            item for item in ops
            if item.get("id") in related_ids
            or (item.get("action") == "add" and any(word in item.get("title", "") for word in relocation_words))
        ]

    if re.search(r"已(?:经)?找到房子|已(?:经)?确定住处", latest_message or ""):
        result["calendar_intent"] = "propose"
        search_words = ("区域参考", "租房注意", "找房", "看房", "筛选房源", "筛选允许养猫")
        dependency_words = ("交房", "网络", "宽带", "搬家", "入住", "水电", "燃气")
        ops = [
            item for item in ops
            if not (item.get("action") in ("add", "update") and any(word in item.get("title", "") for word in dependency_words))
        ]
        for event in base:
            if not event.get("done") and any(word in event["title"] for word in search_words):
                ops.append(_operation("delete", event))
        handover = _profile_date((profile or {}).get("housing_handover_date"), today)
        def ensure(words, title, detail, basis="建议日期"):
            existing = next((item for item in base if not item.get("done") and any(word in item["title"] for word in words)), None)
            note = "依据用户已确定住所及交房日期重排；确认前不写入计划日历。"
            if existing:
                ops.append(_operation("update", existing, title=title, due_date=handover, detail=detail, date_basis=basis, source_note=note))
            else:
                ops.append(_operation("add", title=title, due_date=handover, detail=detail, date_basis=basis, source_note=note))
        ensure(("交房",), "交房并完成入住验收", "按约定接收钥匙，验收房屋并记录表具读数。", "用户明确")
        ensure(("网络", "宽带"), "核验网络安装条件", "向运营商核验可安装时间、地址覆盖及所需材料，不代为预约。")
        ensure(("搬家安排", "搬家方案"), "确认搬家安排并约定服务时间", "自行选择搬运方式并向服务方确认可用时间和改约规则。")
        ensure(("水电交接",), "搬入新住处并核对水电交接", "入住时核对水电燃气表读数、账单归属及设施状态。")

    if re.search(r"交房.{0,30}(?:晚|延期|改到|调整到|延到|推迟到)", latest_message or ""):
        if not re.search(r"(?:改到|延期至|延到|调整到|推迟到)[^。；\n]{0,8}(?:(?:20\d{2})[年/-])?\d{1,2}[月/-]\d{1,2}", latest_message or ""):
            result.update({
                "response_mode": "E", "calendar_intent": "none", "operations": [],
                "advice_items": [], "follow_ups": ["新的交房日期是哪一天？"],
                "answer": "交房延期会影响搬家、宽带安装和入住交接。请先提供新的交房日期，再核对受影响的待确认变更；已预约服务需要你自行向服务方确认改约。",
            })
            return result
        result["response_mode"] = "D"
        result["calendar_intent"] = "propose"
        target = _profile_date((profile or {}).get("housing_handover_date"), today)
        affected_ids = {
            item["id"] for item in base
            if any(word in item["title"] for word in ("交房", "宽带", "网络安装", "搬家服务", "完成搬家", "搬入", "入住交接"))
        }
        ops = []
        for event in base:
            if event.get("done") or event["id"] not in affected_ids or not target:
                continue
            if "交房" in event["title"]:
                ops.append(_operation("update", event, due_date=target, detail=event.get("detail", "") + "；交房日已按用户最新信息更新。", date_basis="用户明确", source_note="用户明确提供新的交房日。"))
            elif any(word in event["title"] for word in ("宽带", "网络安装")) and (not event.get("due_date") or event["due_date"] < target):
                service_date = (date.fromisoformat(target) + timedelta(days=1)).isoformat()
                old_date = event.get("due_date") or "日期待确认"
                ops.append(_operation("update", event, title="待确认宽带安装改约", due_date=service_date, detail=f"原预约为{old_date}，尚未向运营商完成改约；{event.get('detail', '')}", date_basis="建议日期", source_note="站内建议日期；实际服务时间须用户自行向运营商确认。"))
            elif any(word in event["title"] for word in ("搬家服务", "完成搬家", "搬入", "入住交接")):
                if event.get("due_date") and event["due_date"] >= target:
                    continue
                booked = "已预约" in event["title"] or "已预订" in event["title"]
                new_title = "待确认搬家服务改约" if booked else event["title"]
                old_date = event.get("due_date") or "日期待确认"
                detail = (f"原预约为{old_date}，尚未向服务方完成改约；" if booked else "") + event.get("detail", "") + "；新日期仅为站内建议，需用户自行确认。"
                ops.append(_operation("update", event, title=new_title, due_date=target, detail=detail, date_basis="建议日期", source_note="交房延期后，搬家及入住不得早于新交房日；外部服务未自动改约。"))
        if target:
            if any("宽带" in event["title"] or "网络安装" in event["title"] for event in base) or re.search(r"宽带.{0,10}(?:已|已经).{0,4}(?:约|预约)", latest_message or ""):
                if not any("联系运营商确认安装改约" in event["title"] for event in base):
                    ops.append(_operation("add", title="联系运营商确认安装改约", due_date=today.isoformat(), detail="联系原预约运营商确认取消或改至交房后；记录费用和新的服务时段。", date_basis="建议日期", source_note="仅提醒用户自行确认，不代表系统已代为改约。"))
            if any("搬家服务" in event["title"] for event in base):
                if not any("联系搬运服务方确认改约" in event["title"] for event in base):
                    ops.append(_operation("add", title="联系搬运服务方确认改约", due_date=today.isoformat(), detail="联系原预约搬运服务方确认取消或改至交房日及以后；记录费用和新的服务时段。", date_basis="建议日期", source_note="仅提醒用户自行确认，不代表系统已代为改约。"))
            result["calendar_intent"] = "propose" if ops else "none"
            result["answer"] = f"交房日拟调整为{target}。受影响的宽带、搬家或入住事项已列在下方待确认清单；已预约服务请你自行联系服务方确认改约，系统不会代为办理。确认前计划日历不会改变。" if ops else f"已记录交房日变更为{target}；当前计划没有需要调整的事项。若有外部预约，请自行向服务方核验。"
            result["advice_items"] = []
            result["follow_ups"] = []

    if re.search(r"周末[^\n]{0,10}只有半天|半天[^\n]{0,10}有空", latest_message or ""):
        dated = {}
        for event in base:
            if event.get("due_date") and not event.get("done"):
                dated.setdefault(event["due_date"], []).append(event)
        if dated:
            crowded_date, crowded = max(dated.items(), key=lambda item: len(item[1]))
            if len(crowded) > 3:
                result["response_mode"] = "D"
                result["calendar_intent"] = "propose"
                result["answer"] = f"目前信息总结：你说明周末仅有半天、约3–4小时可用。{crowded_date}原有{len(crowded)}项任务，已提出保留阻塞项并将轻量任务分散到相邻工作日晚间的方案；你确认前不会写入计划日历。"
                result["advice_items"] = []
                result["follow_ups"] = []
                result["quick_choices"] = []
                def priority(event):
                    title = event["title"]
                    if any(word in title for word in ("看房", "确认住处", "签约")):
                        return 0
                    if any(word in title for word in ("单位", "HR", "入职")):
                        return 1
                    return 2
                def estimated_hours(event):
                    detail = event.get("detail", "")
                    match = re.search(r"(?:预计|约|需)?\s*(\d+(?:\.\d+)?)\s*(?:小时|h)", detail)
                    if match:
                        return float(match.group(1))
                    if "半小时" in detail:
                        return 0.5
                    return 3.0 if priority(event) == 0 else 0.5 if priority(event) == 1 else 1.0
                kept, movable, used_hours = [], [], 0.0
                for event in sorted(crowded, key=priority):
                    duration = estimated_hours(event)
                    if event.get("hard_deadline") or (len(kept) < 3 and used_hours + duration <= 4):
                        kept.append(event)
                        used_hours += duration
                    else:
                        movable.append(event)
                if used_hours > 4 or len(kept) > 3:
                    result.update({"response_mode": "E", "calendar_intent": "none", "operations": [],
                                   "answer": f"{crowded_date}的硬截止或不可移动事项已超过半天可用时间；请确认哪些事项可改期，暂不生成冲突日程。"})
                    return result
                # Keep blockers at their original date. The model may have
                # proposed arbitrary dates for the same crowded events; this
                # deterministic capacity rule owns those updates instead.
                crowded_ids = {event["id"] for event in crowded}
                ops = [item for item in ops if item.get("id") not in crowded_ids]
                base_day = date.fromisoformat(crowded_date)
                offsets = (-1, 1, -2, 2, -3, 3)
                slots = []
                for offset in offsets:
                    slot = base_day + timedelta(days=offset)
                    if slot >= today and slot.weekday() < 5:
                        slots.append(slot.isoformat())
                for index, event in enumerate(movable):
                    target = slots[index % len(slots)] if slots else crowded_date
                    ops.append(_operation(
                        "update", event, due_date=target, due_time="19:00",
                        detail=event.get("detail", "") + "；因周末仅半天可用，移至工作日晚间处理。",
                        date_basis="建议日期", source_note="依据用户周末仅有约3–4小时的时间约束重排。",
                    ))

    full_target = _profile_date((profile or {}).get("full_process_deadline"), today)
    if full_target and re.search(r"\d{1,2}\s*(?:周|天)内完成(?:搬家)?全流程", latest_message or ""):
        result["calendar_intent"] = "propose"
        existing = next((item for item in base if "全流程目标完成里程碑" in item["title"]), None)
        detail = "完成入住后的网络就绪、水电交接及其他基础生活配置核验；该日期与入职日分别管理。"
        planned = next((item for item in ops if "全流程" in item.get("title", "") and "里程碑" in item.get("title", "") and item.get("action") != "delete"), None)
        if planned:
            planned["due_date"] = full_target
            planned["date_basis"] = "用户明确"
            planned["source_note"] = "按用户指定的开始规划日加完整天数换算。"
        else:
            ops.append(_operation("update" if existing else "add", existing, title="全流程目标完成里程碑", due_date=full_target, detail=detail, date_basis="用户明确", source_note="按用户指定的开始规划日加完整天数换算。"))

    result["operations"] = ops[:30]
    return result


def _propagate_move_date(confirmed, candidate, touched_ids=None, today=None):
    """Keep the common move handoff task aligned when the move date changes."""
    today = today or shanghai_today()
    old_moves = {item["id"]: item for item in confirmed if any(word in item["title"] for word in ("完成搬家", "搬入", "入住")) and not any(word in item["title"] for word in ("安排", "服务", "改约"))}
    for event in candidate:
        if touched_ids is not None and event["id"] not in touched_ids:
            continue
        old = old_moves.get(event["id"])
        if not old or not old.get("due_date") or not event.get("due_date") or old["due_date"] == event["due_date"]:
            continue
        delta = (date.fromisoformat(event["due_date"]) - date.fromisoformat(old["due_date"])).days
        for dependent in candidate:
            if dependent["id"] == event["id"] or dependent.get("hard_deadline") or (touched_ids is not None and dependent["id"] in touched_ids):
                continue
            if any(word in dependent["title"] for word in ("旧住处交接", "搬家安排", "交接")):
                dependent_due = dependent.get("due_date")
                if not dependent_due:
                    continue
                # Only shift a real move dependency. A stale or unrelated event
                # months away must not be dragged by the same date delta.
                distance = abs((date.fromisoformat(dependent_due) - date.fromisoformat(old["due_date"])).days)
                shifted_due = _shift_date(dependent_due, delta)
                if distance > 60 or date.fromisoformat(shifted_due) < today:
                    continue
                dependent["due_date"] = shifted_due
                dependent["start_date"] = _shift_date(dependent.get("start_date"), delta)


def _propagate_explicit_dependencies(base, candidate, touched_ids):
    """Shift linked, unfinished tasks with their prerequisite; never move hard dates."""
    old = {item["id"]: item for item in base}
    current = {item["id"]: item for item in candidate}
    changed = set(touched_ids)
    for _ in range(len(candidate)):
        new_changes = set()
        for item in candidate:
            if item.get("done") or item.get("hard_deadline") or not item.get("due_date"):
                continue
            for prerequisite_id in item.get("depends_on_ids", []):
                prerequisite = current.get(prerequisite_id)
                previous = old.get(prerequisite_id)
                if prerequisite_id not in changed or not prerequisite or not previous or not prerequisite.get("due_date") or not previous.get("due_date"):
                    continue
                delta = (date.fromisoformat(prerequisite["due_date"]) - date.fromisoformat(previous["due_date"])).days
                if not delta:
                    continue
                if item["id"] not in old or item["id"] in touched_ids:
                    continue
                shifted = _shift_date(old[item["id"]]["due_date"], delta)
                if shifted < prerequisite["due_date"]:
                    shifted = prerequisite["due_date"]
                if shifted != item["due_date"]:
                    offset = (date.fromisoformat(shifted) - date.fromisoformat(item["due_date"])).days
                    item["due_date"] = shifted
                    item["start_date"] = _shift_date(item.get("start_date"), offset)
                    new_changes.add(item["id"])
        if not new_changes:
            break
        changed.update(new_changes)


def _dependency_conflicts(candidate, affected_ids):
    by_id = {item["id"]: item for item in candidate}
    conflicts = []
    for item in candidate:
        for parent_id in item.get("depends_on_ids", []):
            parent = by_id.get(parent_id)
            if not parent or not parent.get("due_date") or not item.get("due_date"):
                continue
            if parent_id in affected_ids or item["id"] in affected_ids:
                if parent["due_date"] > item["due_date"]:
                    conflicts.append(f"{item['title']}（{item['due_date']}）早于前置事项{parent['title']}（{parent['due_date']}）")
    moved = [item for item in candidate if item["id"] in affected_ids and _task_kind(item["title"]) == "move_completion" and item.get("due_date")]
    for move in moved:
        for item in candidate:
            if item.get("due_date") and "交房" in item["title"] and item["due_date"] > move["due_date"]:
                conflicts.append(f"{move['title']}（{move['due_date']}）早于新住处{item['title']}（{item['due_date']}）")
            if item.get("hard_deadline") and item.get("due_date") and _task_kind(item["title"]) == "old_home_handover" and item["due_date"] < move["due_date"]:
                conflicts.append(f"{item['title']}（硬截止 {item['due_date']}）早于{move['title']}（{move['due_date']}），需先核验旧住处交接和物品存放安排")
    return conflicts


def _remove_past_suggestions(candidate, today=None):
    """Do not surface stale model backfills as current plan items."""
    today = today or shanghai_today()
    kept = []
    for event in candidate:
        due = event.get("due_date")
        if event.get("date_basis") == "建议日期" and due:
            due_day = date.fromisoformat(due)
            if due_day < today:
                continue
            start = event.get("start_date")
            if start and date.fromisoformat(start) < today:
                event["start_date"] = today.isoformat()
        kept.append(event)
    return kept


def build_proposal(calendar_state, model_result, profile=None, today=None):
    """Return the complete proposed schedule and diff, or None.

    The caller sends this to the browser; only the browser's confirm action saves it.
    """
    if model_result.get("calendar_intent") != "propose":
        return None
    if model_result.get("delete_all"):
        confirmed = calendar_state["confirmed"]
        pending = calendar_state["pending"] or []
        original = confirmed if confirmed else pending
        if not original:
            return None
        return {
            "events": [],
            "changes": _changes(original, []),
            "clarifications": [],
            "bulk_delete_all": True,
            "pending_only_delete": not bool(confirmed),
            "removed_pending": [item for item in pending if item["id"] not in {event["id"] for event in confirmed}],
        }
    ops = model_result.get("operations", [])
    if not isinstance(ops, list) or not ops or len(ops) > 30:
        return None
    confirmed = calendar_state["confirmed"]
    today = today or shanghai_today()
    base = calendar_state["pending"] if calendar_state["pending"] is not None else confirmed
    candidate = [dict(item) for item in base]
    clarifications = []
    removed_pending = []
    touched_ids = set()
    title_dependencies = {}
    confirmed_ids = {item["id"] for item in confirmed}
    for op in ops:
        if not isinstance(op, dict):
            continue
        action = op.get("action")
        event_id = op.get("id")
        idx = next((i for i, item in enumerate(candidate) if item["id"] == event_id), None)
        if action == "add":
            try:
                event = _from_operation(op, "e_" + uuid.uuid4().hex[:12])
            except ValueError:
                continue
            same_title = next((item for item in candidate if _title_key(item["title"]) == _title_key(event["title"])), None)
            if same_title is not None:
                if same_title["id"] not in touched_ids and _event_difference(same_title, event):
                    status = "confirmed" if same_title["id"] in confirmed_ids else "pending"
                    clarifications.append(_clarification(same_title, event, status))
                continue
            group = _task_kind(event["title"])
            similar = next((item for item in candidate if group and _task_kind(item["title"]) == group), None)
            if similar is not None and similar["id"] not in touched_ids:
                status = "confirmed" if similar["id"] in confirmed_ids else "pending"
                clarifications.append(_clarification(similar, event, status))
            else:
                candidate.append(event)
                touched_ids.add(event["id"])
                title_dependencies[event["id"]] = op.get("depends_on_titles", [])
        elif action == "update" and idx is not None:
            try:
                candidate[idx] = _from_operation(op, event_id, candidate[idx]["done"], candidate[idx])
                touched_ids.add(event_id)
                title_dependencies[event_id] = op.get("depends_on_titles", [])
            except ValueError:
                continue
        elif action == "delete" and idx is not None:
            if calendar_state["pending"] is not None and candidate[idx]["id"] not in confirmed_ids:
                removed_pending.append({"id": candidate[idx]["id"], "title": candidate[idx]["title"]})
            candidate.pop(idx)
    for item in candidate:
        titles = title_dependencies.get(item["id"], [])
        if not isinstance(titles, list):
            continue
        for title in titles[:12]:
            if not isinstance(title, str):
                continue
            match = next((other for other in candidate if other["id"] != item["id"] and _title_key(other["title"]) == _title_key(title)), None)
            if match and match["id"] not in item["depends_on_ids"]:
                item["depends_on_ids"].append(match["id"])
    _apply_planning_constraints(candidate, touched_ids, profile, today)
    _propagate_move_date(confirmed, candidate, touched_ids, today)
    _propagate_explicit_dependencies(base, candidate, touched_ids)
    for item in candidate:
        item["depends_on_ids"] = [key for key in item.get("depends_on_ids", []) if key in {event["id"] for event in candidate}]
    conflicts = _dependency_conflicts(candidate, touched_ids)
    if conflicts:
        return {"events": base, "changes": [], "clarifications": clarifications, "conflicts": conflicts}
    if len(candidate) > MAX_EVENTS:
        return None
    # When revising an unconfirmed proposal, show only this turn's delta,
    # never every item that was already pending.
    changes = _changes(base, candidate)
    if calendar_state["pending"] is not None and candidate == confirmed:
        return {"events": candidate, "changes": [], "clarifications": clarifications, "removed_pending": removed_pending, "clear_pending": True}
    if not changes and not clarifications:
        if calendar_state["pending"] is not None and candidate != confirmed:
            return None
        return None
    candidate.sort(key=lambda x: (x["due_date"] is None, x["due_date"] or "9999-12-31", x["due_time"] or "99:99", x["title"]))
    return {"events": candidate, "changes": changes, "clarifications": clarifications, "removed_pending": removed_pending}
