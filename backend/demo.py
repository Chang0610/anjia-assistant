"""Clearly labelled, deterministic UI demo. Never presented as an LLM answer."""

from __future__ import annotations

from knowledge import area_references, extract_constraints


def answer(messages: list[dict]) -> str:
    latest = messages[-1]["content"]
    c = extract_constraints(messages)
    missing = []
    if not c["office_hub"]:
        missing.append("公司位置（当前通勤数据只覆盖陆家嘴、张江高科、徐家汇）")
    if c["commute_minutes"] is None:
        missing.append("希望的单程通勤时间")
    if c["monthly_rent"] is None:
        missing.append("每月租金预算（与搬家一次性预算分开）")
    if c["shared"] is None:
        missing.append("是否接受合租")
    parts = ["【本地演示回答｜未调用大模型】"]
    if any(word in latest for word in ("租", "通勤", "区域", "住哪", "搬家")):
        if missing:
            parts.append("为了判断区域参考，请再告诉我：" + "、".join(missing) + "。")
        else:
            refs = area_references(messages)["areas"]
            if refs:
                for row in refs[:3]:
                    commute = row["commute_estimate"]
                    rents = row["rent_sample"]
                    rent_text = "；".join(f"{'合租单间' if r['type'] == 'rent_shared_single_room' else '整租一居'}挂牌样本{r['min']}–{r['max']}元/月" for r in rents)
                    parts.append(f"• {row['area']}：{rent_text}；到{c['office_hub']}通勤线网估算约{commute['minutes_min']}–{commute['minutes_max']}分钟。")
                parts.append("以上是2026-09-22挂牌样本与线路估算，不代表实时房源或实测通勤；周边设施尚待地图核验。")
            else:
                parts.append("当前8区域样本中，没有同时满足这些条件的参考项；可以放宽预算或通勤时间，或后续接入更完整的数据。")
    if "社保" in latest:
        parts.append("单位应自用工之日起30日内为职工办理社保登记；居住登记不是单位参保的前置。来源：https://www.samr.gov.cn/zw/zfxxgk/fdzdgknr/bgt/art/2023/art_e81d115419b4463ebb59ec46467fb136.html")
    if "居住证" in latest or "居住登记" in latest:
        parts.append("居住登记满半年是申领居住证的一种路径；已登记且申领前连续6个月在沪缴纳社保、当月仍在缴纳的，也有相应认定路径。来源：https://www.shanghai.gov.cn/nw17239/20251217/676967f3436c49ea8dfe28fb117a89e9.html")
    if len(parts) == 1:
        parts.append("我收到了你的问题。演示模式只展示界面和少量已整理数据；配置模型接口后，才能进行多轮追问并生成个性化计划。")
    return "\n\n".join(parts)
