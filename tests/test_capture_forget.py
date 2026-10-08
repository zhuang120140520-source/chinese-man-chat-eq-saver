import copy
import json
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import numpy as np

import main
from app import worker
from app.partner_store import ProfileStore
from core.chat_history import ScreenLedger, forget_profile, from_start
from core.engine import AnalysisCancelled, analyze
from core.partner import new_profile, normalize_profile
from core.partner_memory import merge_review, normalize_memory, normalize_todo, validate_review

def lines(*texts):
    return [("her", None, text, i * 40) for i, text in enumerate(texts)]

class LedgerTests(unittest.TestCase):
    def test_repeated_and_similar_new_bubbles_keep_distinct_ids(self):
        ledger = ScreenLedger()
        first, _ = ledger.observe(lines("明天一起看展？", "可以呀"))
        second, new = ledger.observe(lines("明天一起看展？", "可以呀", "可以啊", "可以呀"))
        self.assertEqual(len(new), 2)
        self.assertEqual(second[1]["id"], first[1]["id"])
        self.assertNotEqual(second[-1]["id"], first[1]["id"])
        third, new = ledger.observe(lines("明天一起看展？", "可以呀", "可以啊", "可以呀"))
        self.assertEqual(new, [])
        self.assertEqual([r["id"] for r in third], [r["id"] for r in second])

    def test_recapture_scrollback_reuses_ids_but_rotating_new_tail_is_new(self):
        ledger = ScreenLedger()
        a, _ = ledger.observe(lines("第一句", "第二句"))
        b, new = ledger.observe(lines("第二句", "第一句"))
        self.assertEqual(len(new), 1)
        c, new = ledger.observe(lines("第一句", "第二句"))
        self.assertEqual(len(new), 1)
        self.assertNotEqual(c[-1]["id"], a[-1]["id"])
        d, _ = ledger.observe(lines("新末尾"))
        old, new = ledger.observe(lines("第一句", "第二句"))
        self.assertEqual(new, [])
        self.assertEqual(old[-1]["id"], c[-1]["id"])

class ForgetTests(unittest.TestCase):
    def test_remove_sources_and_legacy_evidence_keep_manual_background(self):
        p = new_profile()
        p.update(partner_facts="本人手动填的资料", goal="增加感情",
                 reference_dialogue="我：一起去看展？\n她：我喜欢摄影展\n她：另一段内容")
        p["memories"] = [normalize_memory({"id":"derived", "text":"我喜欢摄影展", "origin":"对话原文", "evidence":"我喜欢摄影展", "source_ids":["selected"]}),
                         normalize_memory({"id":"manual", "text":"我喜欢摄影展", "origin":"手动确认"}),
                         normalize_memory({"id":"legacy", "text":"我喜欢摄影展", "origin":"对话原文", "evidence":"我喜欢摄影展"})]
        p["todos"] = [normalize_todo({"id":"todo", "event":"看展", "source_ids":["selected"]})]
        p["confirmed_notes"] = "[推测/对方] 可能喜欢看展（依据：我喜欢摄影展）\n手动备注"
        forgotten, counts = forget_profile(p, [{"id":"selected", "who":"her", "text":"我喜欢摄影展"}])
        self.assertEqual(counts, {"memories":2, "todos":1, "observations":1, "reference":1})
        self.assertEqual([m["id"] for m in forgotten["memories"]], ["manual"])
        self.assertEqual(forgotten["partner_facts"], p["partner_facts"])
        self.assertEqual(forgotten["goal"], "增加感情")
        self.assertEqual(forgotten["confirmed_notes"], "手动备注")
        self.assertNotIn("摄影展", forgotten["reference_dialogue"])

    def test_new_identical_statement_can_form_new_memory_after_forgetting(self):
        p = new_profile()
        messages = [("her", "我喜欢摄影展")]
        raw = json.dumps({"memories":[{"subject":"对方", "kind":"明确偏好", "evidence":"我喜欢摄影展"}]}, ensure_ascii=False)
        old = validate_review(raw, messages, message_ids=["old"])
        p, _ = merge_review(p, old)
        p, _ = forget_profile(p, [{"id":"old", "who":"her", "text":"我喜欢摄影展"}])
        p, changed = merge_review(p, old)
        self.assertFalse(changed)
        fresh = validate_review(raw, messages, message_ids=["new"])
        p, changed = merge_review(p, fresh)
        self.assertTrue(changed)
        self.assertEqual(p["memories"][0]["source_ids"], ["new"])

    def test_stale_panel_cannot_restore_deleted_provenance(self):
        p = new_profile()
        p["forgotten_sources"] = ["old"]
        p["memories"] = [normalize_memory({"text":"不该恢复", "source_ids":["old"]})]
        self.assertEqual(normalize_profile(p)["memories"], [])

    def test_occurrence_ids_preserve_other_identical_messages_but_legacy_matches_after_restart(self):
        session = "a" * 32
        p = new_profile()
        p["memories"] = [normalize_memory({"id":"other", "text":"我喜欢摄影展", "origin":"对话原文",
            "evidence":"我喜欢摄影展", "source_ids":[session + "-2"]})]
        selected = [{"id":session + "-1", "who":"her", "text":"我喜欢摄影展"}]
        kept, counts = forget_profile(p, selected)
        self.assertEqual(counts["memories"], 0)
        selected[0]["id"] = "b" * 32 + "-1"
        removed, counts = forget_profile(p, selected)
        self.assertEqual(counts["memories"], 1)
        self.assertEqual(removed["memories"], [])

    def test_forgetting_is_persisted_in_encrypted_store(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.dpapi"
            store = ProfileStore(path)
            p = new_profile()
            p.update(binding="虚构测试", persist_reference=True,
                     reference_dialogue="她：我喜欢摄影展\n我：周六见")
            p["memories"] = [normalize_memory({"id":"derived", "text":"我喜欢摄影展",
                "origin":"对话原文", "evidence":"我喜欢摄影展", "source_ids":["selected"]})]
            store.save([p])
            updated, _ = forget_profile(p, [{"id":"selected", "who":"her", "text":"我喜欢摄影展"}])
            store.replace_profile(updated)
            restored = ProfileStore(path).for_chat("虚构测试")
            self.assertEqual(restored["memories"], [])
            self.assertEqual(restored["reference_dialogue"], "我：周六见")
            self.assertIn("selected", restored["forgotten_sources"])
            self.assertNotIn("周六见".encode(), path.read_bytes())

class CaptureMainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.temp.name) / "test.dpapi")
        self.p = new_profile()
        self.p.update(binding="小雨", auto=True)
        self.store.profiles = [self.p]
        self.ov = Mock()
        self.ov.feeds = {}
        self.ov.current_chat.return_value = "小雨"
        self.events = queue.Queue()
        for name, value in (("chats", {}), ("state", {"chat":"小雨", "busy":False, "rerun":None}),
                            ("partner_store", self.store), ("partner_panel", None), ("ov", self.ov),
                            ("q", self.events), ("commands", queue.Queue()), ("child", Mock(is_alive=lambda:True)), ("dbg",None)):
            p = patch.object(main, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)
    def tearDown(self):
        self.temp.cleanup()

    def test_button_requests_screenshot_without_calling_cached_generation(self):
        main.chat_of("小雨")["history"].append(("her", "旧缓存", None))
        with patch.object(main, "start_analyze") as analyze_mock, \
             patch.object(main, "find_chat_hwnd", return_value=(1, Mock(key="wechat"))):
            main.capture_and_generate("小雨")
            analyze_mock.assert_not_called()
        self.assertEqual(main.commands.get_nowait()[0], "snapshot")
        self.assertIsNotNone(main.state["snapshot"])

    def test_manual_snapshot_uses_latest_screen_and_honors_forgetting(self):
        main.chat_of("小雨")["started"] = True
        main.state["snapshot"] = {"id":"request", "expected":"小雨", "profile_id":self.p["id"], "hwnd":1}
        main.chat_of("小雨")["forgotten"].add("old")
        rows = [{"id":"old", "who":"her", "name":None, "text":"忘掉的内容"},
                {"id":"new", "who":"her", "name":None, "text":"刚发的新内容"}]
        self.events.put(("snapshot", "request", "小雨", rows, (0,0,20,20), 30))
        with patch.object(main, "start_analyze") as analyze_mock, patch.object(main.settings, "has_llm_key", return_value=False):
            main.drain()
        self.assertEqual(analyze_mock.call_args.args[1], [("her", "刚发的新内容", None)])
        self.assertTrue(analyze_mock.call_args.kwargs["force"])

    def test_wrong_chat_snapshot_never_reaches_model(self):
        main.state["snapshot"] = {"id":"request", "expected":"小雨", "profile_id":self.p["id"], "hwnd":1}
        self.events.put(("snapshot", "request", "其他人", [], (0,0,20,20), 30))
        with patch.object(main, "start_analyze") as analyze_mock:
            main.drain()
        analyze_mock.assert_not_called()
        self.assertFalse(main.chat_of("其他人")["history"])

    def preview(self):
        main.state["snapshot"] = {"id":"request", "expected":"小雨", "profile_id":self.p["id"], "hwnd":1}
        rows = [{"id":"old", "who":"her", "name":None, "text":"昨天的旧消息"},
                {"id":"me", "who":"me", "name":None, "text":"今天一起看展？"},
                {"id":"her", "who":"her", "name":None, "text":"好呀今天可以"}]
        self.events.put(("snapshot", "request", "小雨", rows, (0,0,20,20), 30))
        main.drain()
        return rows

    def test_first_preview_stays_local_until_start_is_confirmed(self):
        with patch.object(main, "start_analyze") as generate, patch.object(main, "queue_memory_review") as memory:
            rows = self.preview()
            generate.assert_not_called()
            memory.assert_not_called()
            self.assertFalse(main.chat_of("小雨")["history"])
            self.ov.log_message.assert_not_called()
            self.ov.select_chat_start.assert_called_once()
            main.accept_snapshot("request", "me")
        self.assertEqual(generate.call_args.args[1], [("me", "今天一起看展？", None), ("her", "好呀今天可以", None)])
        memory.assert_called_once_with("小雨", manual=True)
        self.assertIn("old", main.chat_of("小雨")["forgotten"])
        # Capturing the same viewport again must not re-admit the ignored prefix.
        self.events.put(("snapshot", "request2", "小雨", rows, (0,0,20,20), 30))
        main.state["snapshot"] = {"id":"request2", "expected":"小雨", "profile_id":self.p["id"], "hwnd":1}
        with patch.object(main, "start_analyze"), patch.object(main, "queue_memory_review"):
            main.drain()
        self.assertNotIn("昨天的旧消息", str(list(main.chat_of("小雨")["history"])))
        self.assertEqual(self.ov.select_chat_start.call_count, 1)

    def test_cancel_start_preview_does_not_ingest_or_call_model(self):
        with patch.object(main, "start_analyze") as generate, patch.object(main, "queue_memory_review") as memory:
            self.preview()
            main.accept_snapshot("request")
        generate.assert_not_called()
        memory.assert_not_called()
        self.assertFalse(main.chat_of("小雨")["history"])
        self.assertFalse(main.chat_of("小雨")["started"])
        self.assertIsNone(main.state["selection"])

    def test_profile_edit_invalidates_pending_preview(self):
        self.preview()
        main.on_profiles_saved()
        with patch.object(main, "start_analyze") as generate:
            main.accept_snapshot("request", "her")
        generate.assert_not_called()
        self.assertFalse(main.chat_of("小雨")["history"])
        self.ov.close_start_dialog.assert_called_once()

    def test_legacy_automatic_packets_do_not_record_chat_or_call_model(self):
        self.events.put(("chat", "小雨"))
        self.events.put(("screen", "小雨", [], [{"id":"old", "who":"her", "name":None, "text":"自动旧消息"}], (0,0,20,20)))
        with patch.object(main, "start_analyze") as generate:
            main.drain()
        generate.assert_not_called()
        self.ov.log_message.assert_not_called()
        self.assertFalse(main.chat_of("小雨")["history"])

    def test_switch_goal_only_saves_and_invalidates_without_generating(self):
        with patch.object(main, "regenerate") as generate, patch.object(main, "find_chat_hwnd") as find:
            main.on_goal_changed("小雨", "增加感情", "自然聊天")
        generate.assert_not_called()
        find.assert_not_called()
        self.assertEqual(self.store.for_chat("小雨")["goal"], "增加感情")

    def test_startup_does_not_find_wechat_start_reader_or_capture(self):
        with patch.object(main, "ProfileStore", return_value=self.store), \
             patch.object(main, "Overlay", return_value=self.ov), \
             patch.object(main, "spawn_worker") as spawn, patch.object(main, "find_chat_hwnd") as find, \
             patch.object(main.worker, "Capture") as capture, \
             patch.object(main.settings, "debug_view", return_value=False), \
             patch.object(main.settings, "check_update", return_value=False), \
             patch.object(main.settings, "has_jev_key", return_value=True), \
             patch.object(main, "debug_on", create=True):
            main.initialize()
        spawn.assert_not_called()
        find.assert_not_called()
        capture.assert_not_called()
        self.assertIsNone(main.child)
        self.assertFalse(main.chats)

    def test_forget_failure_preserves_messages_and_success_cancels_inflight(self):
        row = {"id":"selected", "who":"her", "text":"旧消息", "name":None}
        self.ov.feeds["小雨"] = [("her", None, "旧消息", "12:00", "selected")]
        c = main.chat_of("小雨")
        c["records"].append(row)
        c["history"].append(("her", "旧消息", None))
        c["result"] = {"candidates":["旧建议"]}
        main.state["cancel"] = threading.Event()
        main.state["job"] = "old_job"
        with patch.object(self.store, "replace_profile", side_effect=RuntimeError()):
            ok, _ = main.forget_selected("小雨", ["selected"])
        self.assertFalse(ok)
        self.assertTrue(c["history"])
        ok, _ = main.forget_selected("小雨", ["selected"])
        self.assertTrue(ok)
        self.assertFalse(c["history"])
        self.assertIsNone(c["result"])
        self.assertTrue(main.state["cancel"].is_set())
        self.assertIsNone(main.state["job"])
        self.assertIn("selected", self.store.profiles[0]["forgotten_sources"])

    def test_old_result_does_not_clear_new_job_or_display_forgotten_reply(self):
        result_queue = queue.Queue()
        result_queue.put(("ok", {"candidates":["旧回复"]}, "小雨", 0, "old-job"))
        result_queue.put(("progress", "正在起草回复…", "小雨", 1, "new-job"))
        main.state.update(job="new-job", busy=True)
        with patch.object(main, "results", result_queue), patch.object(main, "drain"), \
             patch.object(main, "memory_tick"):
            main.tick()
        self.assertTrue(main.state["busy"])
        self.ov.show.assert_not_called()
        self.ov.set_status.assert_called_with("正在起草回复…", "busy")

class WorkerTests(unittest.TestCase):
    def test_idle_reader_never_captures_or_runs_ocr(self):
        class EndTest(Exception):
            pass
        commands = Mock(get=Mock(side_effect=EndTest()))
        outputs = queue.Queue()
        with patch.object(worker, "Capture") as capture, patch.object(worker, "read_frame") as read:
            with self.assertRaises(EndTest):
                worker.run(outputs, Mock(is_set=lambda:False), commands)
        capture.assert_not_called()
        read.assert_not_called()
        self.assertTrue(outputs.empty())

    def test_each_explicit_request_captures_once_and_stops_before_ocr(self):
        commands, outputs = queue.Queue(), queue.Queue()
        commands.put(("snapshot", "one", 1, None))
        commands.put(("snapshot", "two", 1, None))
        commands.put(("stop",))
        cap = Mock()
        cap.snapshot.return_value = np.zeros((20,20,3), dtype=np.uint8)
        visible = [{"id":"message", "who":"her", "name":None, "text":"最新消息"}]
        parsed = ("小雨", (0,0,20,20,None,0), Mock(last_ms=20), [], visible, visible)
        reads = []
        def read(*args, **kwargs):
            reads.append(cap.stop.call_count)
            return parsed
        with patch.object(worker, "Capture", return_value=cap), patch.object(worker, "unminimize"), \
             patch.object(worker, "read_frame", side_effect=read):
            worker.run(outputs, Mock(is_set=lambda:False), commands)
        packets = list(outputs.queue)
        self.assertEqual([p[0] for p in packets], ["snapshot_status", "snapshot_status", "snapshot"] * 2)
        self.assertEqual(reads, [1, 2])
        self.assertEqual(cap.snapshot.call_count, 2)
        self.assertEqual(cap.stop.call_count, 2)
        cap.settled.assert_not_called()

    def test_cancellation_stops_later_model_stages(self):
        event = threading.Event()
        def judge(*args, **kwargs):
            event.set()
            return {"answers":{}}
        with patch("core.engine.ask", side_effect=judge), patch("core.engine.draft_candidates") as draft:
            with self.assertRaises(AnalysisCancelled):
                analyze([("her", "你好")], "朋友", cancelled=event.is_set)
        draft.assert_not_called()

if __name__ == "__main__":
    unittest.main()
