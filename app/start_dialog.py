"""Local-only preview for selecting the first message of a conversation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                              QPushButton, QVBoxLayout)


class StartDialog(QDialog):
    def __init__(self, title, records, parent=None):
        super().__init__(parent)
        self.records = records
        self.setWindowTitle("选择本轮聊天起点 · " + title)
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.resize(660, 560)
        self.setStyleSheet("QDialog {background:#f4f7f5;} QLabel {color:#233c32;} "
                          "QListWidget {background:white;border:1px solid #c9dcd0;} "
                          "QPushButton {padding:8px;color:#174e36;}")
        layout = QVBoxLayout(self)
        note = QLabel("请选择本轮第一条消息。从这条及下面的消息开始，前面的旧聊天不录入。\n"
                      "这些文字目前只在本机预览；确认后才生成回复。每位联系人本次打开软件时只需选一次。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        for record in records:
            speaker = "对方" if record["who"] == "her" else "我"
            item = QListWidgetItem(speaker + "：" + record["text"])
            item.setData(Qt.UserRole, record["id"])
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        self.summary = QLabel("点击一条消息选择起点。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        cancel = QPushButton("返回，不录入")
        cancel.clicked.connect(self.reject)
        all_button = QPushButton("本页全部参与")
        all_button.clicked.connect(lambda: self.list.setCurrentRow(0))
        self.confirm = QPushButton("从这条开始并生成")
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(all_button)
        row.addWidget(self.confirm)
        layout.addLayout(row)
        self.list.currentRowChanged.connect(self._changed)

    def start_id(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _changed(self, index):
        self.confirm.setEnabled(index >= 0)
        for i in range(self.list.count()):
            self.list.item(i).setForeground(QColor("#84918a" if i < index else "#233c32"))
        self.summary.setText(f"忽略前面 {index} 条旧消息；录入 {len(self.records) - index} 条消息。"
                             if index >= 0 else "点击一条消息选择起点。")
