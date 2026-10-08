"""Review selected messages and related records before local forgetting."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

class ForgetDialog(QDialog):
    def __init__(self, entries, preview, forget, parent=None):
        super().__init__(parent)
        self.preview, self.forget = preview, forget
        self.setWindowTitle("忘记选中聊天")
        self.resize(660, 560)
        self.setStyleSheet("QDialog {background:#f4f7f5;} QLabel {color:#233c32;} QListWidget {background:white;color:#233c32;border:1px solid #c9dcd0;} QPushButton {padding:8px;color:#174e36;}")
        box = QVBoxLayout(self)
        note = QLabel("勾选这次想忘记的消息。相关自动记忆、观察、待办及相同的补充历史原文会一起移除；手动填写的背景资料保留。")
        note.setWordWrap(True)
        box.addWidget(note)
        row = QHBoxLayout()
        all_button, none_button = QPushButton("全选"), QPushButton("取消选择")
        all_button.clicked.connect(lambda: self.select_all(True))
        none_button.clicked.connect(lambda: self.select_all(False))
        row.addWidget(all_button)
        row.addWidget(none_button)
        row.addStretch(1)
        box.addLayout(row)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        for entry in entries:
            who, name, text, timestamp, ident = entry
            item = QListWidgetItem(f"{timestamp} · {name or ('对方' if who == 'her' else '我')}\n{text}")
            item.setData(Qt.UserRole, ident)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list.addItem(item)
        box.addWidget(self.list, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.PlainText)
        box.addWidget(self.summary)
        row = QHBoxLayout()
        cancel = QPushButton("返回")
        cancel.clicked.connect(self.reject)
        self.confirm = QPushButton("忘记选中聊天")
        self.confirm.clicked.connect(self._forget)
        row.addWidget(cancel)
        row.addWidget(self.confirm)
        box.addLayout(row)
        self.list.itemChanged.connect(self._changed)
        self._changed()

    def selected_ids(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def select_all(self, checked):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.list.blockSignals(False)
        self._changed()

    def _changed(self, *_):
        ids = self.selected_ids()
        counts = self.preview(ids)
        self.confirm.setEnabled(bool(ids))
        self.summary.setText(f"选中 {counts.get('messages', len(ids))} 条聊天；关联记忆 {counts.get('memories', 0)} 条、待办 {counts.get('todos', 0)} 条、观察 {counts.get('observations', 0)} 条、补充历史 {counts.get('reference', 0)} 条。\n从当前上下文和本地相关记录中移除；不会删除微信原消息或撤回已发给模型服务商的内容。")

    def _forget(self):
        ok, error = self.forget(self.selected_ids())
        if ok:
            self.accept()
        else:
            self.summary.setText(error)
