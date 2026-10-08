import copy
from datetime import date
import json
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import Mock, patch

import main
from app.partner_store import ProfileStore
from core.partner import new_profile, normalize_profile, partner_context, progression
from core.partner_memory import merge_review, normalize_memory, normalize_todo, resolve_day, todo_color, validate_review

class MemoryTests(unittest.TestCase):
    def review(self, hers="好呀，明天下午可以，展览馆见"):
        messages = [("me", "明天下午去展览馆看展？"), ("her", hers)]
        raw = {"todos":[{"event":"看展", "when":"明天下午", "location":"展览馆",
                         "my_evidence":messages[0][1], "her_evidence":hers}], "memories":[]}
        return messages, raw

    def test_quotes_are_role_bound_and_fabricated_details_removed(self):
        messages, raw = self.review()
        raw["todos"][0]["location"] = "模型虚构咖啡馆"
        raw["memories"] = [{"subject":"对方", "kind":"明确事实", "evidence":messages[0][1]},
                           {"subject":"对方", "kind":"性格推测", "evidence":messages[1][1]}]
        result = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-08")
        self.assertEqual(result["memories"], [])
        self.assertEqual(result["todos"][0]["location"], "")
        self.assertEqual(result["todos"][0]["day"], "2026-10-09")

    def test_clear_acceptance_confirmed_and_tentative_or_history_pending(self):
        messages, raw = self.review()
        result = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-08")
        self.assertEqual(result["todos"][0]["status"], "confirmed")
        historical = validate_review(json.dumps(raw, ensure_ascii=False), messages)
        self.assertEqual(historical["todos"][0]["status"], "pending")
        self.assertEqual(historical["todos"][0]["day"], "")
        messages, raw = self.review("明天下午可能可以")
        result = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-08")
        self.assertEqual(result["todos"][0]["status"], "pending")

    def test_refusal_and_unsupported_event_are_not_todos(self):
        for hers in ("明天不太可以", "明天没空，不去了", "明天去不了", "算了，下次吧"):
            messages, raw = self.review(hers)
            self.assertEqual(validate_review(json.dumps(raw, ensure_ascii=False), messages)["todos"], [])
        messages, raw = self.review()
        raw["todos"][0]["event"] = "订酒店"
        self.assertEqual(validate_review(json.dumps(raw, ensure_ascii=False), messages)["todos"], [])

    def test_invitation_question_is_not_acceptance_and_later_cancellation_wins(self):
        messages = [("me", "明天下午去看展？"), ("her", "明天下午可以吗？")]
        raw = {"todos":[{"event":"看展", "when":"明天下午", "my_evidence":messages[0][1], "her_evidence":messages[1][1]}]}
        result = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-08")
        self.assertEqual(result["todos"][0]["status"], "pending")
        messages, raw = self.review()
        messages.append(("her", "临时有事，明天去不了了"))
        self.assertEqual(validate_review(json.dumps(raw, ensure_ascii=False), messages)["todos"], [])

    def test_model_paraphrase_not_promoted_into_memory(self):
        messages = [("her", "我喜欢小型摄影展，不太喜欢人多的地方")]
        raw = {"memories":[{"subject":"对方", "kind":"明确偏好", "note":"她是内向的人",
                            "evidence":messages[0][1]}]}
        review = validate_review(json.dumps(raw, ensure_ascii=False), messages)
        self.assertEqual(review["memories"][0]["text"], messages[0][1])
        self.assertNotIn("内向", str(review["memories"]))

    def test_dates_resolve_with_known_anchor_and_repeating_days_differ(self):
        self.assertEqual(resolve_day("下周六下午", "2026-10-08"), "2026-10-17")
        self.assertEqual(resolve_day("周六下午", "2026-10-08"), "2026-10-10")
        self.assertEqual(resolve_day("周六下午"), "")
        self.assertEqual(resolve_day("2026年10月10日"), "2026-10-10")
        messages, raw = self.review()
        a = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-08")["todos"][0]
        b = validate_review(json.dumps(raw, ensure_ascii=False), messages, "2026-10-09")["todos"][0]
        self.assertNotEqual(a["id"], b["id"])

    def test_deleted_and_completed_items_not_resurrected(self):
        p = new_profile()
        todo = normalize_todo({"id":"test", "event":"看展", "status":"confirmed"})
        p, changed = merge_review(p, {"todos":[todo]})
        self.assertTrue(changed)
        p["todos"][0].update(status="completed", manual=True)
        p, changed = merge_review(p, {"todos":[todo]})
        self.assertFalse(changed)
        self.assertEqual(p["todos"][0]["status"], "completed")
        p["todos"], p["dismissed"] = [], ["test"]
        p, changed = merge_review(p, {"todos":[todo]})
        self.assertFalse(changed)
        self.assertEqual(p["todos"], [])

    def test_auto_pending_upgrades_but_manual_edits_survive(self):
        p = new_profile()
        p["todos"] = [normalize_todo({"id":"test", "status":"pending"})]
        confirmed = normalize_todo({"id":"test", "status":"confirmed"})
        p, changed = merge_review(p, {"todos":[confirmed]})
        self.assertTrue(changed)
        p["todos"][0].update(status="pending", manual=True)
        p, changed = merge_review(p, {"todos":[confirmed]})
        self.assertFalse(changed)

    def test_old_profiles_migrate_without_losing_old_notes(self):
        p = normalize_profile({"id":"old", "name":"旧档案", "confirmed_notes":"原有观察", "goal":"增加感情"})
        self.assertEqual(p["memories"], [])
        self.assertEqual(p["todos"], [])
        self.assertEqual(p["confirmed_notes"], "原有观察")
        p["memories"] = [normalize_memory({"text":"喜欢看展"})]
        self.assertIn("喜欢看展", str(partner_context(p)))
        self.assertIn("开启", progression("邀约见面 / 活动"))
        self.assertIn("不强行", progression("随便聊聊"))

    def test_strip_colors(self):
        base = normalize_todo({"status":"pending"})
        self.assertEqual(todo_color(base)[2], "待确认")
        self.assertEqual(todo_color({**base, "status":"confirmed"})[2], "已确认")
        self.assertEqual(todo_color({**base, "day":"2026-10-01"}, date(2026,10,8))[2], "已过期")
        self.assertEqual(todo_color({**base, "status":"completed"})[2], "已完成")

    def test_open_panel_merge_preserves_live_additions_and_applies_deletion(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProfileStore(Path(temp) / "test.dpapi")
            old = new_profile()
            old["memories"] = [normalize_memory({"id":"old", "text":"旧记忆"})]
            baseline = [copy.deepcopy(old)]
            live = copy.deepcopy(old)
            live.update(goal="增加感情")
            live["memories"].append(normalize_memory({"id":"new", "text":"实时新记忆"}))
            store.profiles = [live]
            draft = copy.deepcopy(old)
            draft["memories"] = []
            draft["dismissed"] = ["old"]
            result = store.merge_drafts([draft], baseline)[0]
            self.assertEqual(result["goal"], "增加感情")
            self.assertEqual([m["id"] for m in result["memories"]], ["new"])

    def test_stale_auto_review_never_saves_after_profile_change(self):
        store = Mock()
        p = new_profile()
        p.update(auto=True, binding="小雨")
        store.for_chat.return_value = p
        results = queue.Queue()
        results.put(("小雨", p["id"], 1, {"memories":[normalize_memory({"text":"过期片段"})]}, ""))
        with patch.object(main, "partner_store", store), patch.object(main, "chats", {}), \
             patch.object(main, "review_results", results), patch.object(main, "ov", Mock(), create=True), \
             patch.object(main, "capture_on", Mock(is_set=lambda:False), create=True):
            main.chat_of("小雨")["review"]["token"] = 2
            main.memory_tick()
        store.replace_profile.assert_not_called()

if __name__ == "__main__":
    unittest.main()
