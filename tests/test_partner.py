import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.partner_store import ProfileStore
from core.partner import matching_profile, new_profile, parse_transcript, partner_context, validate_observations
from core.engine import analyze
from core.draft import draft_candidates
from core.jev_client import JevError

class PartnerTests(unittest.TestCase):
    def profile(self):
        p = new_profile()
        p.update(name="测试小雨", binding="测试小雨", my_facts="普通上班族", persona="自信但不夸张",
                 preferences="喜欢小型展览", goal="邀约见面 / 活动", goal_detail="周六下午去看展",
                 reference_dialogue="我：上次展览挺有意思\n她：下次也叫上我")
        return p

    def test_binding_is_exact_unique_and_isolated(self):
        a, b = self.profile(), new_profile()
        b.update(binding="测试小青", preferences="喜欢跑步")
        self.assertIs(matching_profile([a, b], "测试小雨"), a)
        self.assertIsNone(matching_profile([a, b], "测试小"))
        self.assertIsNone(matching_profile([a, a], "测试小雨"))
        self.assertIsNone(matching_profile([a, b], ""))
        self.assertNotIn("跑步", json.dumps(partner_context(a), ensure_ascii=False))

    def test_parser_preserves_roles_multiline_and_rejects_ambiguity(self):
        self.assertEqual(parse_transcript("我：周六去看展？\n她: 好呀\n  下午可以"),
                         [("me", "周六去看展？"), ("her", "好呀\n下午可以")])
        for text in ("你好", "小雨：好呀", "她：", "她：好呀\n小青：一起去", "x" * 24001):
            with self.assertRaises(ValueError):
                parse_transcript(text)

    def test_observations_require_verbatim_evidence(self):
        result = validate_observations(json.dumps({"observations": [
            {"subject":"对方", "note":"可能愿意看展", "evidence":"下次也叫上我", "confidence":"较有依据"},
            {"subject":"对方", "note":"喜欢你", "evidence":"模型编造的证据"},
            {"subject":"对方", "note":"开心", "evidence":"好"}]}), "她：下次也叫上我")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["note"], "可能愿意看展")

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_real_dpapi_has_no_plaintext_and_context_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.dpapi"
            store = ProfileStore(path)
            p = self.profile()
            store.save([p])
            raw = path.read_bytes()
            self.assertNotIn("测试小雨".encode(), raw)
            self.assertNotIn(b'"profiles"', raw)
            loaded = ProfileStore(path)
            self.assertEqual(loaded.profiles[0]["name"], p["name"])
            self.assertEqual(loaded.profiles[0]["reference_dialogue"], "")
            self.assertEqual(store.profiles[0]["reference_dialogue"], p["reference_dialogue"])
            p["persist_reference"] = True
            store.save([p])
            self.assertEqual(ProfileStore(path).profiles[0]["reference_dialogue"], p["reference_dialogue"])

    def test_encryption_failure_preserves_existing_ciphertext(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.dpapi"
            path.write_bytes(b"ORIGINAL CIPHERTEXT")
            store = ProfileStore(Path(temp) / "fresh.dpapi", encrypt=lambda _: (_ for _ in ()).throw(RuntimeError()))
            store.path = path
            with self.assertRaises(RuntimeError):
                store.save([self.profile()])
            self.assertEqual(path.read_bytes(), b"ORIGINAL CIPHERTEXT")
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_corrupt_store_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "profiles.dpapi"
            path.write_bytes(b"corrupt")
            store = ProfileStore(path, decrypt=lambda _: (_ for _ in ()).throw(ValueError()))
            self.assertTrue(store.error)
            with self.assertRaises(ValueError):
                store.save([])
            self.assertEqual(path.read_bytes(), b"corrupt")

    def test_duplicate_bindings_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProfileStore(Path(temp) / "profiles.dpapi", encrypt=lambda raw: raw)
            with self.assertRaises(ValueError):
                store.save([self.profile(), self.profile()])
            self.assertFalse(store.path.exists())

    def test_context_reaches_judge_draft_and_rank(self):
        context = partner_context(self.profile())
        with patch("core.engine.ask", return_value={"answers":{}, "usage":{}}) as judge, \
             patch("core.engine.draft_candidates", return_value=["一起去看展？", "周六下午见？", "约个展？"]) as draft:
            result = analyze([("her", "周六可以")], "暧昧了解", partner_context=context)
            self.assertEqual(len(result["candidates"]), 3)
            self.assertEqual(judge.call_count, 2)
            for call in judge.call_args_list:
                self.assertEqual(call.args[0]["partner_context"], context)
            self.assertEqual(draft.call_args.kwargs["partner_context"], context)
            self.assertIn("partner_context", judge.call_args.args[1]["best_reply"]["instructions"])

    def test_context_reaches_fallback_and_single_candidate(self):
        with patch("core.engine.ask", side_effect=[JevError("offline"), {"answers":{}}]) as judge, \
             patch("core.engine.draft_candidates", return_value=["那就周六下午？"]):
            analyze([("her", "可以呀")], "朋友", partner_context=partner_context(self.profile()))
            self.assertEqual(judge.call_count, 2)
            self.assertIn("partner_context", judge.call_args.args[0])

    def test_draft_prompt_has_distinct_facts_style_goal_and_history(self):
        with patch("core.draft._api_key", return_value="FAKE"), \
             patch("core.draft.chat", return_value='["那就周六下午", "一起去看看", "展览见？"]') as chat:
            draft_candidates([("her", "周六可以")], "暧昧了解", partner_context=partner_context(self.profile()))
            system, user = chat.call_args.args[4:6]
            self.assertIn("人设描述只决定措辞", system)
            self.assertIn("普通上班族", user[0])
            self.assertIn("周六下午去看展", user[0])
            self.assertIn("补充历史对话", user[0])

    def test_request_credentials_are_snapshotted_for_both_stages(self):
        with patch("core.engine.ask", return_value={"answers":{}}) as judge, \
             patch("core.engine.draft_candidates", return_value=["那就周六", "周六见？"]) as draft:
            analyze([("her", "周六可以")], "朋友", jev_api_key="SNAPSHOT-JUDGE", llm_api_key="SNAPSHOT-DRAFT")
            self.assertTrue(all(call.kwargs["api_key"] == "SNAPSHOT-JUDGE" for call in judge.call_args_list))
            self.assertEqual(draft.call_args.kwargs["api_key"], "SNAPSHOT-DRAFT")
        with patch("core.draft._api_key", side_effect=AssertionError("must not read changed environment")), \
             patch("core.draft.chat", return_value='["周六下午吧", "我查个近的展", "行 我确认下位置"]') as chat:
            draft_candidates([("her", "周六可以")], "朋友", api_key="SNAPSHOT-DRAFT")
            self.assertEqual(chat.call_args.args[2], "SNAPSHOT-DRAFT")

if __name__ == "__main__":
    unittest.main()
