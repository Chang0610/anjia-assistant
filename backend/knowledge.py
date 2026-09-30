"""Curated Shanghai MVP facts. Supplied documents are data, never instructions."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREA_DATA = json.loads((ROOT / "data" / "shanghai_area_data.json").read_text(encoding="utf-8"))
CITY_KNOWLEDGE = json.loads((ROOT / "data" / "shanghai_knowledge.json").read_text(encoding="utf-8"))

# Supplement missing evidence without altering the supplied research snapshot.
UTILITY_SOURCE = {
    "source_name": "上海市政府英文门户：Paying utility bills",
    "url": "https://english.shanghai.gov.cn/en-Individuals-DailyLife-Homeliving/20260813/cd956c1c2a464ebabdab29e8ca6f8bcb.html",
    "published_at": "2026-06-24", "verified_at": "2026-09-23",
}
TOPIC_TERMS = {
    "入职体检": ("体检", "健康检查", "HR", "hr", "入职"),
    "租房": ("租", "备案", "网签", "押金", "公积金", "签约"),
    "搬家": ("搬家", "搬迁", "搬运", "货拉拉", "快狗", "海豹"),
    "二手": ("二手", "闲鱼", "旧家具"),
    "生活服务热线": ("热线", "电话", "投诉", "物业", "电", "水", "燃气", "95598", "95558", "12345", "962121"),
    "宠物": ("宠物", "猫", "犬", "狗"),
    "居住证积分": ("积分", "居住证"),
    "落户": ("落户", "户口", "应届", "毕业生", "居转户", "留学"),
    "社保卡": ("社保", "社会保障卡"),
    "医疗挂号": ("医保", "挂号", "就医", "医院"),
    "垃圾分类": ("垃圾", "分类"),
    "交通出行": ("交通", "通勤", "地铁", "公交", "乘车", "交通卡"),
    "宽带": ("宽带", "网络", "网费", "移动", "联通", "电信"),
    "燃气": ("燃气", "煤气", "水电", "阶梯价"),
    "水电过户": ("水电", "过户", "交接", "电力", "电费", "水费", "燃气"),
}


def supplemental_context(messages: list[dict], profile: dict | None = None) -> dict:
    """Select complete topic records; preserve provenance and resolve linked entries."""
    user_text = " ".join(m["content"] for m in messages if m.get("role") == "user")
    text = user_text + " " + json.dumps(profile or {}, ensure_ascii=False)
    planning = any(term in user_text for term in ("计划", "安排", "下一步", "搬去", "搬到"))
    categories = {category for category, terms in TOPIC_TERMS.items() if any(t in text for t in terms)}
    if planning:
        categories.update(("租房", "搬家", "入职体检", "水电过户", "宽带"))
    records = []
    for raw in CITY_KNOWLEDGE["knowledge_entries"]:
        if raw["category"] not in categories:
            continue
        row = dict(raw)
        if row["id"] in ("hotline-electricity-001", "hotline-water-001", "hotline-gas-001"):
            row["evidence"] = [dict(UTILITY_SOURCE)]
        if row["id"] in ("hotline-12345-001", "hotline-property-001"):
            row["evidence"] = [{
                "source_name": "上海市政府英文门户：Public service hotlines in Shanghai",
                "url": "https://english.shanghai.gov.cn/en-Individuals-DailyLife-Publicservicehotlines/20260813/98b41f0e71bb4adf93e3992313a1417c.html",
                "published_at": "2026-06-02", "verified_at": "2026-09-23",
            }]
        row["imported_status"] = raw["status"]
        if row["status"] == "verified" and not any(
            e.get("url") and e.get("source_name") for e in row.get("evidence") or []
        ):
            row["status"] = "pending_verification"
            row["integration_note"] = "附件声明已核验，但缺少可追溯来源；补齐前仅作待核验线索。"
        records.append(row)
    # All 12 templates remain available as planning scaffolds. Hydrate their
    # references only when the corresponding topic is requested.
    templates = [dict(t) for t in CITY_KNOWLEDGE["task_templates"]]
    selected_ids = {r["id"] for r in records}
    for template in templates:
        template["available_knowledge_entry_ids"] = [
            i for i in template["knowledge_entry_ids"] if i in selected_ids
        ]
        if template["template_id"] == "tpl_rent" and "租房" in categories:
            template["knowledge_entry_ids"] = [r["id"] for r in records if r["category"] == "租房"]
            template["available_knowledge_entry_ids"] = template["knowledge_entry_ids"]
            template["evidence_status"] = "mixed：逐条以 knowledge_entries.status 为准"
            template["notes"] = "第二轮已补充租房条目；待核验条目仍只用于核验任务，不承诺房源或资格。"
    # Entries are small and also serve questions about a service by brand name.
    entries = []
    for raw in CITY_KNOWLEDGE["entries"]:
        row = dict(raw)
        row["status"] = "verified" if all(row.get(k) for k in ("url", "service_name", "last_verified", "fallback")) else "pending_verification"
        entries.append(row)
    return {
        "version": CITY_KNOWLEDGE["version"],
        "collected_at": CITY_KNOWLEDGE["collected_at"],
        "knowledge_entries": records, "entries": entries, "task_templates": templates,
        "cost_updates": CITY_KNOWLEDGE["cost_updates"],
        "data_gaps": [g for g in CITY_KNOWLEDGE["data_gaps"] if not g.get("resolved")],
    }

POLICY = [
    {
        "id": "residence_registration",
        "topic": "居住登记与居住证",
        "fact": "来沪人员可办理居住登记。居住登记满半年且符合合法稳定就业、住所或连续就读条件之一，可申领上海居住证。已办理居住登记，且申领前6个月连续在沪缴纳社保、申领当月仍缴纳的，可按现行规定视作登记满半年。居住登记并非单位参保的前置。",
        "source": "https://www.shanghai.gov.cn/nw17239/20251217/676967f3436c49ea8dfe28fb117a89e9.html",
        "status": "官方来源已核验",
    },
    {
        "id": "social_insurance_30days",
        "topic": "社保登记",
        "fact": "用人单位应自用工之日起30日内为职工申请办理社会保险登记；这是单位义务，不能理解为个人必须在入职前办完跨省转移。",
        "source": "https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_e81d115419b4463ebb59ec46467fb136.html",
        "status": "官方来源已核验",
    },
    {
        "id": "housing_fund_first_job",
        "topic": "首次就业公积金",
        "fact": "新参加工作的职工从参加工作的第二个月开始缴存住房公积金；新调入职工适用不同起算规则，应按其身份及单位实际汇缴核验。",
        "source": "https://www.shzfgjj.cn/static/kfzl/zl-kuofu.html",
        "status": "官方来源已核验",
    },
    {
        "id": "medical_insurance_gap",
        "topic": "职工医保停缴",
        "fact": "上海在职职工应缴未缴或未足额缴费时，职工自次月15日起停止享受医保待遇；具体参保身份和接续月份应向单位或医保部门核验。",
        "source": "https://ybj.sh.gov.cn/cb_jbdyl/20260629/3318d1479e9146c6bbafdac988f5737d.html",
        "status": "官方来源已核验",
    },
    {
        "id": "residence_endorsement",
        "topic": "居住证签注",
        "fact": "上海居住证需按有效期办理签注，逾期签注对证件功能及居住年限有影响。具体日期应以本人证件及办理页面为准，不能在未知签发日时计算个人截止日。",
        "source": "https://www.shanghai.gov.cn/affairs_affairs/33f2ac04c5c6467ab0da1182a857ddac.html",
        "status": "官方来源已核验",
    },
    {
        "id": "housing_fund_intercity_transfer",
        "topic": "外省市公积金转入上海",
        "fact": "职工在上海稳定缴存住房公积金半年以上，并符合外省市公积金中心规定的转出条件，可以申请把外省市缴存的住房公积金转入上海；不应阻塞上海单位先开户和缴存。",
        "source": "https://www.shanghai.gov.cn/gwk/affairs/content/0064%4003d6f8b173fb4927b9a475f0e764b9dd",
        "status": "官方来源已核验",
    },
]

PLAN_GUIDANCE = [
    {"task": "确认入职要求", "when": "入职前", "depends_on": [], "completion": "从 HR 获得报到地点、入职材料和体检要求（如有）", "kind": "通用办事建议"},
    {"task": "确定租房完成目标日", "when": "入职及搬入前倒排", "depends_on": ["入职日期、搬家完成目标"], "completion": "留出看房、签约、搬入及通勤试走时间", "kind": "通用办事建议"},
    {"task": "核对租房关键细节", "when": "签约前", "depends_on": ["拟租区域"], "completion": "核对产权或转租授权、押付方式、实际水电气与网络计费、宠物条款、退租责任、通勤和周边生活条件", "kind": "通用办事建议"},
    {"task": "安排搬家与旧住处收尾", "when": "新住处确认后", "depends_on": ["入住日期、旧合同退租条款"], "completion": "确认搬家公司、物品清单、旧住处交接及新住处入住条件", "kind": "通用办事建议"},
    {"task": "办理居住登记", "when": "到沪有符合条件的住所后", "depends_on": ["在沪居住地址与相应证明"], "completion": "在官方渠道核验办理结果；是否需租赁备案依个人住所类型确认", "kind": "有条件适用"},
    {"task": "核对单位参保与公积金", "when": "实际用工后", "depends_on": ["实际用工日期"], "completion": "与单位确认社保登记、缴费和公积金账户状态", "kind": "单位办理、个人核对"},
    {"task": "旧城保险与公积金接续", "when": "跨城换工作用户按需", "depends_on": ["原单位最后缴费月、新单位参保状态"], "completion": "分别核对养老、医保、公积金的转移条件和个人记录；不以转移完成作为上海参保前置", "kind": "条件分支"},
]

HUBS = ("陆家嘴", "张江高科", "徐家汇")


def _amount(text: str, labels: str) -> int | None:
    found = re.search(rf"(?:{labels})[^。；，,\n]{{0,12}}?(\d{{3,5}})\s*元?", text)
    return int(found.group(1)) if found else None


def _commute_limit(text: str) -> int | None:
    if "随便" in text:
        return None
    range_match = re.search(r"(\d{1,3})\s*[-–—至到]\s*(\d{1,3})\s*分钟", text)
    if range_match:
        return int(range_match.group(2))
    if "两小时以内" in text or "2小时以内" in text:
        return 120
    if "一小时以内" in text or "1小时以内" in text:
        return 60
    match = re.search(r"(?:通勤|单程)[^。；，,\n]{0,12}?(\d{1,3})\s*(?:分钟|分)", text) or re.search(r"(\d{1,3})\s*(?:分钟|分)", text)
    return int(match.group(1)) if match else None


def extract_constraints(messages: list[dict], profile: dict | None = None) -> dict:
    profile = profile or {}
    text = "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    latest = messages[-1].get("content", "") if messages else ""
    company = profile.get("company_location", "")
    hub = next((h for h in HUBS if h in latest), None) or next((h for h in HUBS if h in company), None) or next((h for h in HUBS if h in text), None)
    commute_text = latest if any(word in latest for word in ("通勤", "单程")) else profile.get("commute_preference", "") or text
    minutes = _commute_limit(commute_text)
    saved_rent = profile.get("monthly_rent_budget", "")
    rent = _amount(latest, "月租|租金|房租|每月住房预算") or _amount(saved_rent, "月租|租金|房租|每月住房预算|预算") or (int(match.group(1)) if (match := re.search(r"(\d{3,5})", saved_rent)) else None) or _amount(text, "月租|租金|房租|每月住房预算")
    shared_text = latest if any(x in latest for x in ("合租", "整租")) else profile.get("shared_housing", "") or text
    shared = False if shared_text.strip() == "否" or "不接受合租" in shared_text or "不考虑合租" in shared_text or "只整租" in shared_text else True if shared_text.strip() == "是" or "接受合租" in shared_text or "可以合租" in shared_text else None
    return {"office_hub": hub, "commute_minutes": minutes, "monthly_rent": rent, "shared": shared}


def area_references(messages: list[dict], profile: dict | None = None) -> dict:
    c = extract_constraints(messages, profile)
    rows = []
    for area in AREA_DATA["areas"]:
        commute = next((x for x in area["commute"] if x["to"] == c["office_hub"]), None)
        if c["office_hub"] and commute is None:
            continue
        rent_keys = ["rent_shared_single_room", "rent_whole_1br"] if c["shared"] is None else (["rent_shared_single_room"] if c["shared"] else ["rent_whole_1br"])
        rents = [{"type": k, **area[k]} for k in rent_keys if area.get(k)]
        fits_time = None if c["commute_minutes"] is None or commute is None else commute["minutes_max"] <= c["commute_minutes"]
        rent_relation = "unknown" if c["monthly_rent"] is None or not rents else "sample_within_budget" if any(r["max"] <= c["monthly_rent"] for r in rents) else "sample_partly_within_budget" if any(r["min"] <= c["monthly_rent"] for r in rents) else "sample_above_budget"
        if fits_time is False or rent_relation == "sample_above_budget":
            continue
        rows.append({
            "area": area["name"], "boundary": area["boundary"], "station": area["reference_station"],
            "rent_sample": rents, "rent_status": area["data_status"], "rent_note": area["rent_note"],
            "commute_estimate": commute, "fits_time": fits_time, "rent_budget_relation": rent_relation,
            "facilities_pending_verification": {k: [v["name"] for v in values] for k, values in area["facilities"].items()},
        })
    return {"constraints": c, "areas": rows[:8], "rent_source": "https://sh.zu.anjuke.com/?from=HomePage_TopBar", "rent_as_of": AREA_DATA["meta"]["researched_at"], "rent_method": AREA_DATA["meta"]["rent_method"], "commute_method": AREA_DATA["meta"]["commute_method"]}


def context_for(messages: list[dict], profile: dict | None = None) -> dict:
    latest = messages[-1]["content"] if messages else ""
    # Always provide core time-line rules; add area evidence only for relevant questions.
    area_terms = ("租", "区域", "通勤", "商场", "超市", "菜市场", "住哪", "水电", "宽带", "搬家", "计划", "下一步")
    area = area_references(messages, profile) if any(x in latest for x in area_terms) else None
    utilities = [
        {**row, "data_status": "pending_verification"} if row["utility"] == "gas" else row
        for row in AREA_DATA["utilities"]
    ] if any(x in latest for x in ("水电", "燃气", "宽带", "网费")) else None
    return {"policies": POLICY, "plan_guidance": PLAN_GUIDANCE, "area_data": area,
            "utilities": utilities, "city_knowledge": supplemental_context(messages, profile)}
