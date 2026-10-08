import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from app.partner_panel import PartnerPanel
from app.partner_store import ProfileStore
from app.forget_dialog import ForgetDialog
from app.start_dialog import StartDialog

class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.temp.name) / "test.dpapi")
        self.panel = PartnerPanel(self.store, lambda:"小雨", lambda:[("her", "明天可以", None)], lambda:None)

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_unsaved_history_draft_does_not_restore_forgotten_messages(self):
        self.panel.binding.setText("小雨")
        self.panel.reference.setPlainText("她：我喜欢摄影展\n我：周六见")
        self.panel.fields["my_facts"].setPlainText("其他未保存的资料")
        self.panel.forget_messages("小雨", [{"id":"selected", "who":"her", "text":"我喜欢摄影展"}])
        self.assertEqual(self.panel.reference.toPlainText(), "我：周六见")
        self.assertEqual(self.panel.fields["my_facts"].toPlainText(), "其他未保存的资料")
        self.assertEqual(self.panel.review, {})

    def test_forget_dialog_checks_selection_and_keeps_it_when_save_fails(self):
        calls = []
        dialog = ForgetDialog([("her", None, "虚构消息", "12:00", "one")],
            preview=lambda ids:{"messages":len(ids), "memories":len(ids)},
            forget=lambda ids:(calls.append(ids) or False, "保存失败"))
        self.assertFalse(dialog.confirm.isEnabled())
        dialog.select_all(True)
        self.assertTrue(dialog.confirm.isEnabled())
        self.assertIn("关联记忆 1 条", dialog.summary.text())
        dialog._forget()
        self.assertEqual(calls, [["one"]])
        self.assertEqual(dialog.selected_ids(), ["one"])
        self.assertEqual(dialog.summary.text(), "保存失败")
        dialog.close()
        dialog.deleteLater()

    def test_start_dialog_requires_a_local_selection_before_accepting(self):
        dialog = StartDialog("虚构联系人", [
            {"id":"old", "who":"her", "text":"昨天的消息"},
            {"id":"new", "who":"her", "text":"今天的新消息"}])
        self.assertFalse(dialog.confirm.isEnabled())
        self.assertIsNone(dialog.start_id())
        dialog.list.setCurrentRow(1)
        self.assertTrue(dialog.confirm.isEnabled())
        self.assertEqual(dialog.start_id(), "new")
        self.assertIn("忽略前面 1 条", dialog.summary.text())
        dialog.close()
        dialog.deleteLater()

    def test_removed_reply_tabs_and_history_is_isolated(self):
        tabs = [self.panel.tabs.tabText(i) for i in range(self.panel.tabs.count())]
        self.assertNotIn("粘贴与生成", tabs)
        self.assertNotIn("回复与观察", tabs)
        self.panel.reference.setPlainText("她：小雨的私密消息")
        self.panel._new()
        self.assertEqual(self.panel.reference.toPlainText(), "")

    def test_import_requires_matching_contact_and_single_chat(self):
        self.panel._import_current()
        self.assertEqual(self.panel.reference.toPlainText(), "")
        self.panel.binding.setText("小雨")
        self.panel._import_current()
        self.assertIn("明天可以", self.panel.reference.toPlainText())
        self.panel.reference.clear()
        self.panel.current_messages = lambda:[("her", "群聊", "某人")]
        self.panel._import_current()
        self.assertEqual(self.panel.reference.toPlainText(), "")

    def test_file_is_local_only_and_requires_roles(self):
        path = Path(self.temp.name) / "history.txt"
        path.write_text("我：周六一起看展？\n她：好呀可以", encoding="utf-8-sig")
        self.panel.import_history_file(path)
        self.assertIn("周六一起看展", self.panel.reference.toPlainText())
        self.assertFalse(self.store.path.exists())
        path.write_text("未知名字：消息", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.panel.import_history_file(path)

    def test_changed_goal_discards_old_assessment(self):
        revision = self.panel.revision
        self.panel.goal.setCurrentText("增加感情")
        self.panel._completed(revision, {"summary":{"我":{"note":"旧评价", "evidence":"原文"}}}, "")
        self.assertNotIn("旧评价", self.panel.result_note.text())
        self.assertIn("丢弃", self.panel.status.text())

    def test_balanced_review_observations_require_selection(self):
        result = {"summary":{s:{"note":s + "简评", "evidence":"下次也叫上我"} for s in ("我", "对方", "整体对话")},
                  "observations":[{"subject":"对方", "confidence":"待确认", "note":"可能喜欢看展", "evidence":"下次也叫上我"}],
                  "memories":[], "todos":[]}
        self.panel._completed(self.panel.revision, result, "")
        for subject in result["summary"]:
            self.assertIn(subject + "简评", self.panel.result_note.text())
        self.panel._accept_observations()
        self.assertEqual(self.panel.fields["confirmed_notes"].toPlainText(), "")
        self.panel.observation_list.item(0).setCheckState(Qt.Checked)
        self.panel._accept_observations()
        self.assertIn("推测/对方", self.panel.fields["confirmed_notes"].toPlainText())
        self.assertFalse(self.store.path.exists())

    def test_save_and_return_hides_only_after_success(self):
        self.panel.show()
        with patch.object(self.store, "save", side_effect=RuntimeError("encryption failed")):
            self.panel._save_return()
        self.assertTrue(self.panel.isVisible())
        self.assertFalse(self.store.path.exists())
        self.panel._save_return()
        self.assertFalse(self.panel.isVisible())
        self.assertTrue(self.store.path.exists())

    def test_return_preserves_unsaved_draft(self):
        self.panel.show()
        self.panel.name.setText("未保存昵称")
        self.panel._return()
        self.assertFalse(self.panel.isVisible())
        self.assertEqual(self.panel.name.text(), "未保存昵称")
        self.assertFalse(self.store.path.exists())

if __name__ == "__main__":
    unittest.main()
