"""Small colored todo strips with local editing; no external calendar."""
import copy
from datetime import date
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLayout,
    QLineEdit, QPushButton, QVBoxLayout, QWidget)
from core.partner_memory import normalize_todo, todo_color
from app.forget_dialog import ForgetDialog

class TodoEditor(QDialog):
    def __init__(self, todo, parent=None):
        super().__init__(parent)
        self.todo = copy.deepcopy(todo)
        self.setWindowTitle("编辑约定与待办")
        self.setMinimumWidth(360)
        self.setStyleSheet("QDialog {background:#f4f7f5;} QLabel {color:#233c32;} QLineEdit,QComboBox {background:white;color:#233c32;padding:6px;} QPushButton {padding:7px;color:#174e36;}")
        form = QFormLayout(self)
        self.fields = {}
        for key, label in (("event", "事情"), ("when", "时间（原文或自己填写）"), ("day", "日期 YYYY-MM-DD（可留空）"), ("location", "地点（可留空）")):
            field = QLineEdit(todo.get(key, ""))
            field.setMaxLength(10 if key == "day" else 120)
            self.fields[key] = field
            form.addRow(label, field)
        self.status = QComboBox()
        self.status.addItem("待确认", "pending")
        self.status.addItem("已确认", "confirmed")
        self.status.addItem("已完成", "completed")
        self.status.setCurrentIndex(self.status.findData(todo.get("status", "pending")))
        form.addRow("状态", self.status)
        evidence = QLabel("原文依据：\n" + todo.get("evidence", "手动添加"))
        evidence.setWordWrap(True)
        evidence.setTextFormat(Qt.PlainText)
        form.addRow(evidence)
        self.error = QLabel("")
        form.addRow(self.error)
        row = QHBoxLayout()
        cancel, save = QPushButton("取消"), QPushButton("保存")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(save)
        form.addRow(row)

    def _save(self):
        values = {k: f.text().strip() for k, f in self.fields.items()}
        if not values["event"]:
            self.error.setText("请填写事情。")
            return
        try:
            if values["day"]:
                date.fromisoformat(values["day"])
        except ValueError:
            self.error.setText("日期请使用 YYYY-MM-DD，例如 2026-10-10。")
            return
        self.todo.update(values, status=self.status.currentData(), manual=True)
        self.todo = normalize_todo(self.todo)
        self.accept()

class TodoBoard(QWidget):
    action = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)
        self.profile = None
        self.set_profile(None)

    def set_profile(self, profile):
        self.profile = copy.deepcopy(profile)
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        head = QWidget()
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 0, 0)
        title = QLabel("约定与待办")
        title.setStyleSheet("font-weight:600;color:#304c3c;")
        row.addWidget(title, 1)
        add = QPushButton("+ 添加")
        add.setEnabled(bool(profile))
        add.clicked.connect(lambda: self._edit(normalize_todo({}), True))
        row.addWidget(add)
        self.layout.addWidget(head)
        todos = profile.get("todos", []) if profile else []
        if not todos:
            label = QLabel("双方聊定的安排会自动整理到这里。" if profile else "绑定联系人档案后，在这里管理约定。")
            label.setWordWrap(True)
            label.setStyleSheet("color:#768578;font-size:12px;")
            self.layout.addWidget(label)
        order = sorted(todos, key=lambda t: (t["status"] == "completed", t.get("day") or "9999", t["created"]))
        for todo in order:
            bg, color, status = todo_color(todo)
            strip = QWidget()
            strip.setObjectName("todoStrip")
            strip.setStyleSheet(f"QWidget#todoStrip {{background:{bg};border-left:4px solid {color};border-radius:6px;}} QLabel {{background:transparent;color:{color};}} QPushButton {{background:transparent;color:{color};padding:4px;border:0;}}")
            box = QVBoxLayout(strip)
            box.setSizeConstraint(QLayout.SetMinimumSize)
            box.setContentsMargins(10, 8, 8, 6)
            box.setSpacing(3)
            date_text = f" · {todo['day']}" if todo.get("day") else ""
            if todo.get("day") == date.today().isoformat():
                status = "今天 · " + status
            text = f"{status} · {todo['when']}{date_text}\n{todo['event']}"
            if todo["location"]:
                text += " · " + todo["location"]
            label = QLabel(text)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            box.addWidget(label)
            buttons = QHBoxLayout()
            buttons.addStretch(1)
            edit = QPushButton("编辑")
            edit.clicked.connect(lambda _, t=todo: self._edit(t))
            buttons.addWidget(edit)
            complete = QPushButton("恢复" if todo["status"] == "completed" else "完成")
            complete.clicked.connect(lambda _, t=todo: self._complete(t))
            buttons.addWidget(complete)
            delete = QPushButton("删除")
            delete.clicked.connect(lambda _, t=todo: self.action.emit("delete", t))
            buttons.addWidget(delete)
            box.addLayout(buttons)
            self.layout.addWidget(strip)

    def _edit(self, todo, new=False):
        dialog = TodoEditor(todo, self)
        if dialog.exec() == QDialog.Accepted:
            self.action.emit("add" if new else "edit", dialog.todo)

    def _complete(self, todo):
        updated = {**todo, "status": "pending" if todo["status"] == "completed" else "completed", "manual": True}
        self.action.emit("edit", updated)
