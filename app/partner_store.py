"""Private profiles outside the checkout, encrypted by Windows user DPAPI."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile

from core.partner import matching_profile, normalize_profile

def protect(data):
    import win32crypt
    return win32crypt.CryptProtectData(data, "Jev Partner private profiles", None, None, None, 1)

def unprotect(data):
    import win32crypt
    return win32crypt.CryptUnprotectData(data, None, None, None, 1)[1]

class ProfileStore:
    def __init__(self, path=None, encrypt=protect, decrypt=unprotect):
        self.path = Path(path) if path else Path(os.environ["LOCALAPPDATA"]) / "JevPartnerChat" / "private" / "profiles.dpapi"
        self.encrypt, self.decrypt = encrypt, decrypt
        self.profiles = []
        self.error = ""
        if self.path.exists():
            try:
                payload = json.loads(self.decrypt(self.path.read_bytes()).decode("utf-8"))
                if payload.get("version") != 1 or not isinstance(payload.get("profiles"), list):
                    raise ValueError("unknown profile format")
                self.profiles = self._normalize(payload["profiles"])
            except Exception:
                self.error = "本地档案无法解密或已损坏。请在原 Windows 账户下打开；原文件已保留。"

    @staticmethod
    def _normalize(profiles):
        if len(profiles) > 30:
            raise ValueError("最多保存 30 位联系人")
        normalized = [normalize_profile(p) for p in profiles]
        ids = [p["id"] for p in normalized]
        bindings = [p["binding"] for p in normalized if p["binding"]]
        if len(set(ids)) != len(ids) or len(set(bindings)) != len(bindings):
            raise ValueError("档案编号或绑定会话重复，请每个会话只绑定一份档案")
        return normalized

    def save(self, profiles):
        if self.error:
            raise ValueError(self.error)
        normalized = self._normalize(profiles)
        disk_profiles = copy.deepcopy(normalized)
        for p in disk_profiles:
            if not p["persist_reference"]:
                p["reference_dialogue"] = ""
        raw = json.dumps({"version": 1, "profiles": disk_profiles}, ensure_ascii=False).encode("utf-8")
        encrypted = self.encrypt(raw)  # encryption failure must never fall back to plaintext
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".profiles-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        self.profiles = normalized

    def for_chat(self, title):
        return matching_profile(self.profiles, title)

    def replace_profile(self, profile):
        profiles = copy.deepcopy(self.profiles)
        for i, old in enumerate(profiles):
            if old["id"] == profile["id"]:
                profiles[i] = profile
                self.save(profiles)
                return
        raise ValueError("联系人档案已删除，请重新打开准备页")

    def merge_drafts(self, drafts, baseline):
        """Keep live goal/memory/todo changes made since the panel was opened."""
        before = {p["id"]: p for p in baseline}
        current = {p["id"]: p for p in self.profiles}
        merged = []
        for draft in drafts:
            p = copy.deepcopy(draft)
            old, latest = before.get(p["id"]), current.get(p["id"])
            if old and not latest:
                raise ValueError("该联系人已被删除，请重新打开准备页")
            if old and latest:
                for key, value in latest.items():
                    if key in ("memories", "todos"):
                        old_items = {m["id"]: m for m in old.get(key, [])}
                        draft_items = {m["id"]: m for m in draft.get(key, [])}
                        live_items = {m["id"]: copy.deepcopy(m) for m in value}
                        for ident in old_items.keys() - draft_items.keys():
                            live_items.pop(ident, None)
                        for ident, item in draft_items.items():
                            if item != old_items.get(ident):
                                live_items[ident] = copy.deepcopy(item)
                        p[key] = list(live_items.values())
                    elif key in ("dismissed", "forgotten_sources"):
                        p[key] = list(dict.fromkeys(value + draft.get(key, [])))
                    elif draft.get(key) == old.get(key):
                        p[key] = copy.deepcopy(value)
            merged.append(p)
        return merged
