"""Conservative, display-only labels for the answer's source lines."""

import re


def annotate_answer(answer: str, evidence: dict) -> list[dict]:
    official = {item["source"] for item in evidence.get("policies", []) if item.get("status") == "官方来源已核验"}
    area = evidence.get("area_data") or {}
    rent_url = area.get("rent_source")
    labels = []
    city = evidence.get("city_knowledge") or {}
    source_states = {}
    for record in city.get("knowledge_entries", []):
        for source in record.get("evidence") or []:
            if source.get("url"):
                source_states.setdefault(source["url"], set()).add(record["status"])
    entry_urls = {entry["url"] for entry in city.get("entries", [])
                  if entry.get("url") and entry.get("status") == "verified"}
    for index, line in enumerate(answer.splitlines()):
        if "信息依据或入口" not in line:
            continue
        tags = []
        link = None
        matched = next((url for url in official if url in line), None)
        if matched:
            tags.append("官方来源已核验")
            link = matched
        for url, states in source_states.items():
            if url not in line:
                continue
            link = link or url
            # A shared source can back both checked and unchecked claims.
            if "pending_verification" in states:
                tags.append("信息待确认")
            elif "sample_reference" in states:
                tags.append("样本参考")
            elif states == {"verified"}:
                tags.append("知识来源已核验")
        entry_link = next((url for url in entry_urls if url in line), None)
        if entry_link:
            tags.append("服务入口已核验")
            link = link or entry_link
        if rent_url and rent_url in line:
            tags.append("挂牌样本" + (" · " + str(area["rent_as_of"]) if area.get("rent_as_of") else ""))
            link = link or rent_url
        if "通勤" in line and ("估算" in line or "参考" in line):
            tags.append("通勤估算")
        if any(term in line for term in ("配套待核验", "地图核验", "POI待核验")):
            tags.append("配套待核验")
        if any(term in line for term in ("信息待确认", "待核验", "需核验", "待确认", "后端计划指引")):
            tags.append("部分信息待确认" if tags else "信息待确认")
        if not tags:
            tags.append("入口或依据待核验")
        labels.append({"line": index, "tags": list(dict.fromkeys(tags)), "verified_url": link})
    return labels
