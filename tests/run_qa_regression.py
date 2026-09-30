"""Run replayable multi-turn QA scenarios against the local chat API.

Usage: python3 tests/run_qa_regression.py --url http://127.0.0.1:8766
The runner never applies proposals to confirmed calendar state.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]

def post(url, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode()
    req = Request(url, data=raw, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as res:
        return json.loads(res.read().decode())

def check_result(check, result, previous=None):
    proposal = result.get("proposal") or {}
    changes = proposal.get("changes") or []
    operations = []
    for change in changes:
        operations.extend(change.get("operations") or [])
    answer = result.get("answer", "")
    if check == "no_calendar_change": return not proposal
    if check == "has_calendar_proposal": return bool(proposal)
    if check == "has_operations": return bool(operations or proposal.get("events"))
    if check == "has_delete_operation": return any(x.get("action") == "delete" for x in operations)
    if check == "has_follow_up": return "最后追问" in answer or "请补充" in answer
    if check == "has_confirmation_language": return "确认" in answer or "确认" in json.dumps(proposal, ensure_ascii=False)
    if check == "has_evidence_or_uncertainty": return any(x in answer for x in ("依据", "待确认", "待核验", "入口"))
    if check == "does_not_claim_applied": return not any(x in answer for x in ("已添加", "已修改", "已删除", "已经写入"))
    if check == "mentions_risk_or_verification": return any(x in answer for x in ("风险", "核验", "冲突", "硬截止"))
    if check == "second_turn_no_duplicate_add": return not proposal or not any(x.get("action") == "add" for x in operations)
    if check == "second_turn_no_calendar_change": return not proposal
    return False

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8766")
    ap.add_argument("--cases", default=str(ROOT / "tests/scenarios/qa_regression.json")); ap.add_argument("--out", default=str(ROOT / "artifacts/qa_regression")); args = ap.parse_args()
    cases = json.loads(Path(args.cases).read_text())
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    report = {"run_at": datetime.now().isoformat(timespec="seconds"), "url": args.url, "cases": []}
    for case in cases:
        messages=[]; calendar=case.get("calendar", {"confirmed": [], "pending": None}); profile=case.get("profile", {}); turns=[]; errors=[]
        for text in case["turns"]:
            messages.append({"role":"user", "content":text})
            try: result=post(args.url + "/api/chat", {"messages":messages, "profile":profile, "calendar":calendar})
            except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                errors.append(str(exc)); turns.append({"user":text,"error":str(exc)}); break
            profile=result.get("profile", profile); turns.append({"user":text,"response":result})
            messages.append({"role":"assistant", "content":result.get("answer","")})
        checks=[]
        for check in case.get("checks", []):
            target=turns[-1].get("response", {}) if check.startswith("second_turn") else turns[0].get("response", {})
            checks.append({"name":check,"passed":bool(target) and check_result(check,target)})
        item={"id":case["id"],"name":case["name"],"checks":checks,"status":"error" if errors else ("pass" if all(x["passed"] for x in checks) else "review"),"errors":errors,"turns":turns}
        report["cases"].append(item); (out/(case["id"]+".json")).write_text(json.dumps(item,ensure_ascii=False,indent=2))
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=[f"# QA 回归报告\n\n运行时间：{report['run_at']}\n接口：`{args.url}`\n\n| 用例 | 状态 | 断言 |\n|---|---|---|"]
    for c in report["cases"]: lines.append(f"| {c['id']} {c['name']} | {c['status']} | " + "; ".join(('✅' if x['passed'] else '❌')+x['name'] for x in c['checks']) + " |")
    lines += ["\n详细 JSON：每个用例一个文件；本轮未执行确认写入。"]
    (out/"report.md").write_text("\n".join(lines))
    print(out/"report.md")
    return 1 if any(c["status"] == "error" for c in report["cases"]) else 0
if __name__ == "__main__": sys.exit(main())
