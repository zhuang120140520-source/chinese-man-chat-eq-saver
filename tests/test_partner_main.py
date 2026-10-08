import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import main
from app.partner_store import ProfileStore
from core.partner import new_profile

class MainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.temp.name) / "test.dpapi")
        self.profile = new_profile()
        self.profile.update(name="小雨", binding="小雨", auto=True, preferences="喜欢摄影展")
        self.store.profiles = [self.profile]
        for name, value in [("chats", {}), ("state", {"chat":"小雨", "busy":False, "rerun":None}),
                            ("partner_store", self.store), ("ov", Mock())]:
            p = patch.object(main, name, value, create=True)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_unbound_disabled_or_group_chat_never_calls_network(self):
        with patch.object(main.threading, "Thread") as thread:
            main.start_analyze("小青", [("her", "你好", None)])
            self.profile["auto"] = False
            main.start_analyze("小雨", [("her", "你好", None)])
            self.profile["auto"] = True
            main.start_analyze("小雨", [("her", "你好", "群里某人")])
            thread.assert_not_called()

    def test_explicit_request_gets_immutable_personal_context(self):
        with patch.object(main.settings, "has_jev_key", return_value=True), \
             patch.object(main.settings, "has_llm_key", return_value=True), \
             patch.object(main, "model_options", return_value={"model":"test"}), \
             patch.object(main.threading, "Thread") as thread:
            main.start_analyze("小雨", [("her", "你好", None)], force=True)
            snapshot = thread.call_args.kwargs["args"][3]
            self.profile["preferences"] = "修改后的偏好"
            self.assertIn("喜欢摄影展", str(snapshot))
            self.assertNotIn("修改后的偏好", str(snapshot))

    def test_saving_new_goal_invalidates_every_cached_result(self):
        chat = main.chat_of("小雨")
        chat["result"] = {"candidates":["旧目标回复"]}
        revision = chat["rev"]
        main.state["rerun"] = ("小雨", [])
        main.on_profiles_saved()
        self.assertIsNone(chat["result"])
        self.assertGreater(chat["rev"], revision)
        self.assertIsNone(main.state["rerun"])
        main.ov.invalidate_replies.assert_called_once()

if __name__ == "__main__":
    unittest.main()
