import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from qfluentwidgets import PrimaryPushButton
from app.overlay import Overlay
from app import i18n, settings
from core.partner import new_profile
from core.partner_memory import normalize_todo

class HomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_profile_browsing_never_fakes_active_wechat_and_cards_scroll(self):
        ov = Overlay(on_fill=lambda text:None)
        self.assertFalse(hasattr(ov, "captureSwitch"))
        self.assertEqual(ov.regenerateButton.text(), "对方已说完 生成回复")
        self.assertIsInstance(ov.regenerateButton, PrimaryPushButton)
        p = new_profile()
        p.update(binding="小雨", goal="邀约见面 / 活动", goal_detail="周六看展")
        p["todos"] = [normalize_todo({"event":"看展", "when":"周六下午"})]
        ov.register_profile_chats(["小雨"])
        self.assertEqual(ov.current_chat(), "小雨")
        self.assertEqual(ov._chat, "")
        ov.set_partner_profile(p)
        self.assertEqual(ov.goalBox.currentText(), "邀约见面 / 活动")
        ov.show({"candidates":["周六一起去看展？", "我们周六去？", "看个展吧？"]})
        ov.invalidate_replies()
        for _ in range(6):
            self.app.processEvents()
        self.assertGreaterEqual(ov.regenerateButton.y(), ov.goalCard.y() + ov.goalCard.height())
        self.assertTrue(all(not c.fillButton.isEnabled() for c in ov.cards))
        self.assertTrue(all(c.height() > 75 for c in ov.cards))
        self.assertGreater(ov.home.verticalScrollBar().maximum(), 0)
        ov.win.close()
        ov.win.deleteLater()
        self.app.processEvents()

    def test_simple_model_page_saves_and_returns_without_resetting_hidden_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.json"
            before = {"lang":"ko", "relationship":"friends", "context":8,
                      "style":"短句", "debug_view":True, "check_update":False,
                      "reply_target":False}
            config.write_text(json.dumps(before), encoding="utf-8")
            with patch.object(settings, "_CONFIG", str(config)), \
                 patch.object(settings, "_read_env", return_value="synthetic-key"), \
                 patch.object(settings, "_set_key") as set_key, \
                 patch.dict(os.environ, {"JEVCHAT_LANG":"ko"}):
                i18n.reload("ko")
                self.assertEqual(i18n.language(), "zh")
                self.assertEqual(settings.language(), "zh")
                ov = Overlay(on_fill=lambda text:None)
                self.assertIn("Chinese Man 聊天情商拯救器", ov.win.windowTitle())
                self.assertEqual(ov.languageBox.count(), 1)
                self.assertEqual(ov.languageBox.currentText(), "简体中文")
                for removed in ("relationshipBox", "contextBox", "styleEdit", "targetSwitch", "updateSwitch", "debugSwitch"):
                    self.assertFalse(hasattr(ov, removed))
                ov.open_settings()
                ov._save()
                self.assertIs(ov.pages.currentWidget(), ov.home)
                after = json.loads(config.read_text(encoding="utf-8"))
                for key, value in before.items():
                    self.assertEqual(after[key], "zh" if key == "lang" else value)
                self.assertNotIn("synthetic-key", config.read_text(encoding="utf-8"))
                set_key.assert_not_called()
                ov.win.close()
                ov.win.deleteLater()
                self.app.processEvents()

    def test_start_selection_returns_only_on_confirm_and_cancel_returns_none(self):
        ov = Overlay(on_fill=lambda text:None)
        choices = []
        rows = [{"id":"one", "who":"her", "name":None, "text":"昨天的消息"},
                {"id":"two", "who":"her", "name":None, "text":"今天的新消息"}]
        ov.select_chat_start("虚构联系人", rows, choices.append)
        self.assertEqual(choices, [])
        ov._start_dialog.list.setCurrentRow(1)
        ov._start_dialog.accept()
        self.assertEqual(choices, ["two"])
        self.assertIsNone(ov._start_dialog)
        ov.select_chat_start("虚构联系人", rows, choices.append)
        ov.close_start_dialog()
        self.assertEqual(choices, ["two", None])
        ov.win.close()
        ov.win.deleteLater()
        self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
