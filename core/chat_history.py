"""Occurrence IDs for captured messages, plus evidence-aware selective forgetting."""
from __future__ import annotations
from collections import OrderedDict
import copy
from difflib import SequenceMatcher
import re
import uuid

def message_key(row):
    return row[0], re.sub(r"\s+", "", str(row[2]))

class ScreenLedger:
    """Align ordered visible bubbles, rather than globally banning similar text.

    Remember recent viewports so forgotten occurrences keep their IDs on recapture
    and scrolling. A newly appended identical bubble receives a different ID.
    """
    def __init__(self):
        self.previous = []
        self.windows = OrderedDict()
        self.session = uuid.uuid4().hex
        self.serial = 0

    def observe(self, lines):
        keys = tuple(message_key(line) for line in lines)
        if not keys:
            return [], []
        old_keys = [(r["who"], re.sub(r"\s+", "", r["text"])) for r in self.previous]
        # Chat viewports usually advance: the old tail becomes the new head.
        # Prefer that overlap when repeated text gives SequenceMatcher several
        # equally plausible alignments, or it can swallow a genuinely new tail.
        overlap = next((n for n in range(min(len(old_keys), len(keys)), 0, -1)
                        if tuple(old_keys[-n:]) == keys[:n]), 0)
        if overlap:
            reuse = {j: self.previous[len(old_keys) - overlap + j] for j in range(overlap)}
        else:
            blocks = SequenceMatcher(None, old_keys, keys, autojunk=False).get_matching_blocks()
            reuse = {block.b + j: self.previous[block.a + j] for block in blocks for j in range(block.size)}
        last_known = max(reuse, default=-1)
        if keys in self.windows and (keys == tuple(old_keys) or last_known == len(keys) - 1 or not reuse):
            records = copy.deepcopy(self.windows[keys])
            self.windows.move_to_end(keys)
            self.previous = records
            return records, []
        records, new = [], []
        for i, (who, name, text, *_rest) in enumerate(lines):
            if i not in reuse:
                self.serial += 1
            item = copy.deepcopy(reuse[i]) if i in reuse else {
                "id": f"{self.session}-{self.serial}", "who": who, "name": name, "text": text}
            item.update(who=who, name=name, text=text)
            records.append(item)
            if i not in reuse and i > last_known:
                new.append(item)
        self.previous = records
        self.windows[keys] = copy.deepcopy(records)
        while len(self.windows) > 80:
            self.windows.popitem(last=False)
        return records, new

def source_ids(messages, ids, quote, role=None):
    if not ids:
        return []
    found = [ids[i] for i, m in enumerate(messages)
        if i < len(ids) and ids[i] and quote in m[1] and (role is None or m[0] == role)]
    return found[-1:]

def from_start(records, start_id):
    """Return the chosen suffix and IDs to exclude, without calling a model."""
    index = next((i for i, row in enumerate(records) if row["id"] == start_id), None)
    if index is None:
        raise ValueError("请选择本轮第一条消息")
    return copy.deepcopy(records[index:]), {row["id"] for row in records[:index]}

def forget_profile(profile, entries):
    """Remove derived records and exact imported messages; keep hand-written facts."""
    from core.partner import format_transcript, parse_transcript
    p = copy.deepcopy(profile)
    ids = {e["id"] for e in entries}
    counts = {"memories": 0, "todos": 0, "observations": 0, "reference": 0}
    def related(item, field):
        if set(item.get("source_ids", [])) & ids:
            return True
        if item.get("source_ids"):
            def session(ident):
                return ident.split("-", 1)[0] if re.fullmatch(r"[0-9a-f]{32}-\d+", ident) else ident
            if {session(s) for s in item["source_ids"]} & {session(s) for s in ids}:
                return False
        # Older versions lack IDs: match their existing verbatim evidence only.
        if field == "memories" and item.get("origin") != "对话原文":
            return False
        evidence = item.get("evidence", "")
        if not evidence:
            return False
        for e in entries:
            if field == "memories" and item.get("subject") in ("我", "对方"):
                if e["who"] != ("me" if item["subject"] == "我" else "her"):
                    continue
            if field == "todos":
                portions = re.findall(r"(?:我|她)：([^\n]+)", evidence)
                if any(len(s) >= 2 and s in e["text"] for s in portions):
                    return True
            elif len(evidence) >= 4 and evidence in e["text"]:
                return True
        return False
    for field in ("memories", "todos"):
        kept = []
        for item in p.get(field, []):
            if related(item, field):
                counts[field] += 1
                p["dismissed"].append(item["id"])
                ids.update(item.get("source_ids", []))
            else:
                kept.append(item)
        p[field] = kept
    notes = []
    for line in p.get("confirmed_notes", "").splitlines():
        quote = re.search(r"^\[推测/(?:我|对方|双方)\].*（依据：(.*)）$", line)
        if quote and any(quote[1] in e["text"] for e in entries):
            counts["observations"] += 1
        else:
            notes.append(line)
    p["confirmed_notes"] = "\n".join(notes)
    if p.get("reference_dialogue", "").strip():
        try:
            original = parse_transcript(p["reference_dialogue"])
            selected = {(e["who"], e["text"].strip()) for e in entries}
            kept = [(who, text) for who, text in original if (who, text.strip()) not in selected]
            counts["reference"] = len(original) - len(kept)
            p["reference_dialogue"] = format_transcript(kept)
        except ValueError:
            pass
    p["forgotten_sources"] = list(dict.fromkeys(p.get("forgotten_sources", []) + list(ids)))[-2000:]
    return p, counts
