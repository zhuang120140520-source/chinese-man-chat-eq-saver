"""Evidence-bound memories and arrangements, independent of generated replies."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import re
import uuid

def fingerprint(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]

def normalize_memory(m):
    return {"id": str(m.get("id") or uuid.uuid4().hex)[:64],
            "subject": str(m.get("subject") or "双方")[:12],
            "text": str(m.get("text") or "")[:500], "evidence": str(m.get("evidence") or "")[:500],
            "created": str(m.get("created") or "")[:32], "origin": str(m.get("origin") or "手动确认")[:32],
            "source_ids": [str(s)[:64] for s in m.get("source_ids", [])][:60]}

def normalize_todo(t):
    day = str(t.get("day") or "")[:10]
    try:
        if day:
            date.fromisoformat(day)
    except ValueError:
        day = ""
    status = t.get("status") if t.get("status") in ("pending", "confirmed", "completed") else "pending"
    return {"id": str(t.get("id") or uuid.uuid4().hex)[:64], "event": str(t.get("event") or "待补充事项")[:120],
            "when": str(t.get("when") or "时间待确认")[:120], "location": str(t.get("location") or "")[:120],
            "day": day, "status": status, "evidence": str(t.get("evidence") or "")[:800],
            "created": str(t.get("created") or "")[:32], "manual": bool(t.get("manual", False)),
            "source_ids": [str(s)[:64] for s in t.get("source_ids", [])][:60]}

def resolve_day(text, anchor=None):
    """Only resolve relative dates when the messages have a known capture date."""
    exact = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})(?:日|号)?", text)
    if exact:
        try:
            return date(*map(int, exact.groups())).isoformat()
        except ValueError:
            return ""
    if not anchor:
        return ""
    today = date.fromisoformat(str(anchor)[:10])
    for word, delta in (("大后天", 3), ("后天", 2), ("明天", 1), ("今天", 0)):
        if word in text:
            return (today + timedelta(days=delta)).isoformat()
    weekday = re.search(r"(下周|本周|这周|周|星期)([一二三四五六日天])", text)
    if weekday:
        n = "一二三四五六日".find(weekday[2].replace("天", "日"))
        offset = (n - today.weekday()) % 7
        if weekday[1] == "下周":
            offset = 7 - today.weekday() + n
        return (today + timedelta(days=offset)).isoformat()
    month_day = re.search(r"(\d{1,2})月(\d{1,2})(?:日|号)", text)
    if month_day:
        try:
            return date(today.year, *map(int, month_day.groups())).isoformat()
        except ValueError:
            pass
    return ""

def todo_color(t, today=None):
    if t["status"] == "completed":
        return "#e8ebed", "#667077", "已完成"
    if t.get("day") and t["day"] < (today or date.today()).isoformat():
        return "#fbe8e4", "#ab4234", "已过期"
    if t["status"] == "confirmed":
        return "#e2f3e9", "#18754d", "已确认"
    return "#fff0d8", "#956320", "待确认"

def _quote(item, key, messages, role=None):
    quote = str(item.get(key) or "").strip()
    return quote if 2 <= len(quote) <= 400 and any(
        quote in m[1] and (role is None or m[0] == role) for m in messages) else ""

def validate_review(content, messages, anchor=None, message_ids=None):
    from core.chat_history import source_ids
    from core.partner import format_transcript, validate_observations
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        data = json.loads(clean)
        if not isinstance(data, dict):
            raise ValueError()
    except ValueError:
        raise ValueError("模型未返回有效的点评，请重试") from None
    source = format_transcript(messages)
    out = {"summary": {}, "observations": validate_observations(clean, source), "memories": [], "todos": []}
    for subject in ("我", "对方", "整体对话"):
        entry = data.get("summary", {}).get(subject, {}) if isinstance(data.get("summary"), dict) else {}
        if isinstance(entry, dict) and _quote(entry, "evidence", messages):
            out["summary"][subject] = {"note": str(entry.get("note") or "")[:260], "evidence": entry["evidence"][:400]}
    stamp = datetime.now().isoformat(timespec="minutes")
    for item in data.get("memories", [])[:12] if isinstance(data.get("memories"), list) else []:
        if not isinstance(item, dict) or item.get("kind") not in ("明确偏好", "明确事实", "共同经历"):
            continue
        subject = item.get("subject")
        role = {"我": "me", "对方": "her"}.get(subject)
        # Store the quotation itself, never the model's personality inference or paraphrase.
        evidence = _quote(item, "evidence", messages, role)
        if not role or not evidence or len(evidence) < 4:
            continue
        sources = source_ids(messages, message_ids, evidence, role)
        out["memories"].append(normalize_memory({"id": fingerprint(subject, evidence, *sources) if sources else fingerprint(subject, evidence), "subject": subject,
            "text": evidence, "evidence": evidence, "created": stamp, "origin": "对话原文", "source_ids": sources}))
    for item in data.get("todos", [])[:8] if isinstance(data.get("todos"), list) else []:
        if not isinstance(item, dict):
            continue
        mine, hers = _quote(item, "my_evidence", messages, "me"), _quote(item, "her_evidence", messages, "her")
        event, when, location = [str(item.get(k) or "").strip()[:120] for k in ("event", "when", "location")]
        evidence = mine + "\n" + hers
        if not mine or not hers or not event or event not in evidence:
            continue
        # Every displayed detail must occur in the dialogue, never solely in the user's goal.
        when = when if when and when in evidence else "时间待确认"
        location = location if location and location in evidence else ""
        # The later statement is the response; either person can initiate the invitation.
        my_index = max(i for i, m in enumerate(messages) if m[0] == "me" and mine in m[1])
        her_index = max(i for i, m in enumerate(messages) if m[0] == "her" and hers in m[1])
        decision = mine if my_index > her_index else hers
        if re.search(r"不去|不行|没空|不要|算了|拒绝|不.{0,2}可以|不想|不太方便|不了|下次吧|去不了", decision):
            continue
        later = messages[max(my_index, her_index) + 1:]
        if any(re.search(r"不去了|去不了|改天吧|算了", m[1]) for m in later):
            continue
        tentative = bool(re.search(r"可能|应该|也许|再看|改天|有空再|不确定|到时候|吧|待定", evidence))
        accepted = not re.search(r"[?？]|要不要|行不行|可以吗|好不好", decision) and bool(re.search(
            r"好[呀啊的]|可以|没问题|就这么定|说定了|到时见|行[呀啊]|(?<!不)行[！!。\s]*$", decision))
        day = resolve_day(when, anchor)
        status = "confirmed" if accepted and not tentative and day else "pending"
        # The capture date disambiguates repeating phrases such as "明天" on different days.
        ident = fingerprint(event, day or when, location, "" if day else anchor or "历史")
        sources = source_ids(messages, message_ids, mine, "me") + source_ids(messages, message_ids, hers, "her")
        if sources:
            ident = fingerprint(ident, *sources)
        out["todos"].append(normalize_todo({"id": ident, "event": event, "when": when, "location": location,
            "day": day, "status": status, "evidence": "我：" + mine + "\n她：" + hers, "created": stamp,
            "source_ids": sources}))
    return out

def merge_review(profile, review, include_memories=True):
    """Merge only new grounded records; respect manual completion/deletion and edits."""
    import copy
    p = copy.deepcopy(profile)
    dismissed = set(p.get("dismissed", []))
    forgotten = set(p.get("forgotten_sources", []))
    changed = False
    for field in (["memories", "todos"] if include_memories else ["todos"]):
        seen = {m["id"] for m in p.get(field, [])}
        for item in review.get(field, []):
            if set(item.get("source_ids", [])) & forgotten:
                continue
            if field == "todos" and item["id"] not in dismissed:
                same = next((t for t in p[field] if t["id"] != item["id"] and
                    (t["event"], t["day"], t["location"], t["when"]) ==
                    (item["event"], item["day"], item["location"], item["when"])), None)
                if same:
                    if not same.get("manual") and same["status"] != "completed":
                        same["source_ids"] = list(dict.fromkeys(same.get("source_ids", []) + item.get("source_ids", [])))
                        if item["status"] == "confirmed":
                            same.update(status="confirmed", evidence=item["evidence"])
                        changed = True
                    continue
            if item["id"] not in seen and item["id"] not in dismissed:
                p.setdefault(field, []).append(copy.deepcopy(item))
                seen.add(item["id"])
                changed = True
            elif field == "todos":
                for old in p[field]:
                    if old["id"] == item["id"] and old["status"] == "pending" and not old.get("manual") and item["status"] == "confirmed":
                        old.update(status="confirmed", evidence=item["evidence"])
                        changed = True
    return p, changed
