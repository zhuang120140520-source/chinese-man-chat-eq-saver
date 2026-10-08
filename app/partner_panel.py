"""Preparation and historical review; reply suggestions live only on the homepage."""
from __future__ import annotations
import copy
import threading
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)
from app import settings
from app.partner_runtime import model_options
from core.partner import (FIELDS, GOALS, MAX_FIELD, MAX_TRANSCRIPT, format_transcript, new_profile,
                          normalize_profile, parse_transcript, partner_context)
from core.partner_memory import fingerprint, merge_review, normalize_memory
from core.profile_analysis import review_dialogue
from core.chat_history import forget_profile

class PartnerPanel(QDialog):
    completed = Signal(int, object, str)

    def __init__(self, store, current_chat, current_messages, on_saved, parent=None):
        super().__init__(parent)
        self.store, self.current_chat, self.current_messages, self.on_saved = store, current_chat, current_messages, on_saved
        self.baseline = copy.deepcopy(store.profiles)
        self.profiles = copy.deepcopy(store.profiles) or [new_profile()]
        self.index, self.revision, self.busy, self.review = 0, 0, False, {}
        self.setWindowTitle("Chinese Man 聊天情商拯救器 · 准备资料")
        self.setFont(QFont("Microsoft YaHei UI", 10))
        palette = self.palette()
        for role, color in ((QPalette.Window, "#f4f7f5"), (QPalette.Base, "#ffffff"),
                            (QPalette.Text, "#233c32"), (QPalette.WindowText, "#233c32"),
                            (QPalette.Button, "#e4efe8"), (QPalette.ButtonText, "#174e36")):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self.setMinimumSize(680, 560)
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(920, available.width() - 48), min(880, available.height() - 60))
        self.setStyleSheet("""
            QWidget { background:#f4f7f5; color:#233c32; }
            QLabel { background:transparent; }
            QLineEdit, QPlainTextEdit, QComboBox, QListWidget { background:white; color:#233c32;
                border:1px solid #d1ddd5; border-radius:6px; padding:7px; }
            QPushButton { background:#e4efe8; color:#174e36; border:1px solid #c9dcd0;
                border-radius:6px; padding:8px 12px; }
            QPushButton:hover { background:#d2e7db; }
            QPushButton:disabled { color:#8b9991; background:#eef1ef; }
            QTabWidget::pane { border:1px solid #d1ddd5; }
            QTabBar::tab { padding:10px 12px; background:#e8efea; }
            QTabBar::tab:selected { background:white; color:#18794e; }
        """)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        heading = QLabel("更懂你们，才更会接话")
        heading.setStyleSheet("font-size:22px; font-weight:600; padding:6px;")
        row.addWidget(heading, 1)
        self.back_button = self._button("← 返回聊天", self._return)
        row.addWidget(self.back_button)
        layout.addLayout(row)
        intro = QLabel("先补充资料和旧对话，再回主页面聊天。点击 AI 点评或生成回复后，相关文字会发给你配置的模型服务商。")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        self.profile_combo = QComboBox()
        row.addWidget(self.profile_combo, 1)
        row.addWidget(self._button("新增联系人", self._new))
        self.save_button = self._button("保存档案", self._save)
        row.addWidget(self.save_button)
        self.save_return_button = self._button("保存并返回聊天", self._save_return)
        self.save_return_button.setStyleSheet("background:#18794e; color:white; font-weight:600;")
        row.addWidget(self.save_return_button)
        row.addWidget(self._button("删除", self._delete))
        layout.addLayout(row)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.fields = {}
        form = self._form_tab("对方与关系")
        self.name = self._line(form, "称呼 / 档案名称", "例如：小雨（尽量用昵称）")
        self.binding = self._line(form, "微信聊天名 / 备注（完全一致）", "填写微信聊天窗口顶部显示的名称")
        form.addRow("", self._button("绑定当前已识别会话", self._bind_current))
        binding_note = QLabel("先填写微信顶部显示的聊天名，即可绑定；不必先截图。不同联系人请设置不同备注。")
        binding_note.setWordWrap(True)
        form.addRow(binding_note)
        self.gender = self._combo(form, "对方", ["女生", "男生", "其他 / 不指定"])
        self.stage = self._combo(form, "关系阶段", ["关系待确认", "刚认识", "朋友", "暧昧了解", "正在交往", "长期伴侣", "磨合 / 冲突中"])
        for key, hint in [("partner_facts", "背景、职业、作息、确认的性格特点；不确定的请标注"),
                          ("preferences", "喜欢的活动、食物、话题和表达"),
                          ("boundaries", "不喜欢的玩笑、约会限制、称呼边界、明确拒绝过的事"),
                          ("shared_history", "共同经历、笑点、约定和最近的矛盾")]:
            self._area(form, key, hint)
        form = self._form_tab("我与表达风格")
        for key, hint in [("my_facts", "真实身份、经历、性格与生活情况；涉及事实时以这里为准"),
                          ("persona", "想呈现的气质：自信、有主见、幽默、松弛、温柔，或做自己"),
                          ("speech_style", "短句、常用词、表情习惯；贴几句你平时说的话"),
                          ("confirmed_notes", "手动采纳的观察；仍是推测，可以修改或删除")]:
            self._area(form, key, hint)
        form = self._form_tab("这轮目标")
        self.goal = self._combo(form, "本次聊天的目的（主页面也能切换）", GOALS)
        self._area(form, "goal_detail", "邀约可写活动、时间、地点与备选；只填能做到的安排", 140)
        self.auto = QCheckBox("点击生成后，允许 AI 整理本次已录入聊天的原文记忆与待办")
        self.auto.stateChanged.connect(self._changed)
        form.addRow("", self.auto)
        note = QLabel("保存档案 → 返回聊天 → 对方说完后点击生成。首次截图先选择本轮起点；未绑定或群聊不会调用模型。\n邀约、化解误会等目标会适度推进；对方拒绝或不方便时放慢。")
        note.setWordWrap(True)
        form.addRow(note)
        form = self._form_tab("补充历史")
        self.history_page = self.tabs.widget(self.tabs.count() - 1)
        note = QLabel("聊天开始前补充你们以前的对话。可以粘贴文字、导入 TXT，或载入绑定会话记录。\n每条用 我： / 她： 开头；续行缩进。这里仅做点评。截图暂不支持直接导入。")
        note.setWordWrap(True)
        form.addRow(note)
        self.reference = QPlainTextEdit()
        self.reference.setPlaceholderText("我：上次那个展还挺有意思\n她：下次也叫上我")
        self.reference.setMinimumHeight(170)
        self.reference.setMaximumHeight(240)
        self.reference.textChanged.connect(self._changed)
        form.addRow(self.reference)
        row = QHBoxLayout()
        for text, callback in (("导入 TXT", self._import_file), ("载入绑定会话记录", self._import_current), ("清空历史", self.reference.clear)):
            row.addWidget(self._button(text, callback))
        form.addRow(row)
        self.persist_reference = QCheckBox("将完整补充历史加密保存到本机（不勾选则仅留在本次内存）")
        self.persist_reference.stateChanged.connect(self._changed)
        form.addRow(self.persist_reference)
        self.observe_button = self._button("AI 点评双方与对话", self._request)
        self.observe_button.setStyleSheet("background:#18794e; color:white; font-weight:600;")
        form.addRow(self.observe_button)
        self.result_note = QLabel("点评会分别简述你、对方与整体对话，附原文依据。")
        self.result_note.setWordWrap(True)
        self.result_note.setTextFormat(Qt.PlainText)
        self.result_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(self.result_note)
        self.observation_list = QListWidget()
        self.observation_list.setWordWrap(True)
        self.observation_list.setMinimumHeight(110)
        self.observation_list.setMaximumHeight(180)
        form.addRow(self.observation_list)
        form.addRow(self._button("采纳勾选的观察 / 记忆（之后点保存）", self._accept_observations))
        self.todo_button = self._button("将点评中的约定加入待办（之后点保存）", self._accept_todos)
        self.todo_button.setEnabled(False)
        form.addRow(self.todo_button)
        form = self._form_tab("长期记忆")
        note = QLabel("近期上下文：点击截图并确认起点后加入，保留在内存。\n长期记忆：重要事实、偏好、经历存为有原文依据的片段，本机加密。AI 性格猜测需手动采纳。\n可查看、删除或手动补充；删除的原文记忆不会被自动重复加回。")
        note.setWordWrap(True)
        form.addRow(note)
        self.memory_list = QListWidget()
        self.memory_list.setWordWrap(True)
        self.memory_list.setMinimumHeight(240)
        form.addRow(self.memory_list)
        self.memory_input = QPlainTextEdit()
        self.memory_input.setPlaceholderText("手动确认的重要事实或共同经历（最多 500 字）")
        self.memory_input.setMaximumHeight(90)
        form.addRow(self.memory_input)
        row = QHBoxLayout()
        self.memory_subject = QComboBox()
        self.memory_subject.addItems(["对方", "我", "双方"])
        row.addWidget(self.memory_subject)
        row.addWidget(self._button("加入记忆", self._add_memory))
        row.addWidget(self._button("删除选中记忆", self._remove_memory))
        form.addRow(row)
        form = self._form_tab("隐私与使用")
        privacy = QLabel(
            "• 档案、长期原文记忆、待办在 Windows 当前用户 LocalAppData\\JevPartnerChat\\private 中 DPAPI 加密保存。\n"
            "• 实时完整聊天只保留在内存；完整补充历史仅勾选后保存。重要原文片段会作为长期记忆保存，可删。\n"
            "• 仅点击生成时截图。首次选择起点前只在本机预览；确认后将相关文字发给判断和起草模型。\n• 勾选记忆整理后，仅本次已录入聊天参与原文记忆 / 待办整理，另调用起草模型。\n"
            "• 历史点评只发给起草模型。导入 TXT 是本机读文件，点击点评后才调用模型。\n"
            "• 使用时资料在内存，同账户恶意软件可能读取；云端留存取决于服务商与账户条款。\n"
            "• 保留原版模型设置与 API Key 配置；密钥在 Windows 用户环境变量中，未加密。\n"
            "• 截图 / OCR 在本机；复制文字可能受 Windows 剪贴板历史与同步影响。\n"
            "• 回复由你确认发送。待办只在软件内显示，当前没有关闭软件后的系统通知。\n\n"
            "基于 MIT 许可的 jev-chat-windows 修改。加密档案位置：\n" + str(store.path))
        privacy.setWordWrap(True)
        privacy.setTextFormat(Qt.PlainText)
        privacy.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow(privacy)
        self.status = QLabel(store.error or "填完后可点「保存并返回聊天」；资料在本机加密保存。")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status)
        self.completed.connect(self._completed)
        self.profile_combo.currentIndexChanged.connect(self._select)
        self._refresh_profiles()
        self._load()

    @staticmethod
    def _button(text, callback):
        button = QPushButton(text)
        button.clicked.connect(callback)
        return button

    def _form_tab(self, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        form = QFormLayout(page)
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setContentsMargins(20, 16, 20, 16)
        form.setVerticalSpacing(10)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, name)
        return form

    def _line(self, form, label, hint):
        field = QLineEdit()
        field.setMaxLength(120)
        field.setPlaceholderText(hint)
        field.textChanged.connect(self._changed)
        form.addRow(label, field)
        return field

    def _combo(self, form, label, choices):
        field = QComboBox()
        field.addItems(choices)
        field.currentTextChanged.connect(self._changed)
        form.addRow(label, field)
        return field

    def _area(self, form, key, hint, height=95):
        field = QPlainTextEdit()
        field.setPlaceholderText(hint + f"（最多 {MAX_FIELD} 字）")
        field.setMinimumHeight(height)
        field.setMaximumHeight(height + 30)
        field.textChanged.connect(self._changed)
        self.fields[key] = field
        form.addRow(FIELDS[key], field)

    def _changed(self, *_):
        self.revision += 1
        self.review = {}
        if hasattr(self, "observation_list"):
            self.observation_list.clear()
            self.result_note.setText("资料或历史已变化，点击「AI 点评双方与对话」重新点评。")
            self.todo_button.setEnabled(False)

    def _snapshot(self):
        p = copy.deepcopy(self.profiles[self.index])
        p.update(name=self.name.text().strip() or "未命名联系人", gender=self.gender.currentText(),
                 stage=self.stage.currentText(), goal=self.goal.currentText(), binding=self.binding.text().strip(),
                 auto=self.auto.isChecked(), persist_reference=self.persist_reference.isChecked(),
                 reference_dialogue=self.reference.toPlainText())
        for key, field in self.fields.items():
            value = field.toPlainText()
            if len(value) > MAX_FIELD:
                raise ValueError(f"{FIELDS[key]} 超过 {MAX_FIELD} 字，请精简")
            p[key] = value
        if len(p["reference_dialogue"]) > MAX_TRANSCRIPT:
            raise ValueError("补充历史超过 24000 字，请精简")
        return normalize_profile(p)

    def _refresh_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems([p["name"] for p in self.profiles])
        self.profile_combo.setCurrentIndex(self.index)
        self.profile_combo.blockSignals(False)

    def _load(self):
        p = self.profiles[self.index]
        self.name.setText(p["name"])
        self.gender.setCurrentText(p["gender"])
        self.stage.setCurrentText(p["stage"])
        self.goal.setCurrentText(p["goal"])
        self.binding.setText(p["binding"])
        self.auto.setChecked(p["auto"])
        self.reference.setPlainText(p["reference_dialogue"])
        self.persist_reference.setChecked(p["persist_reference"])
        for key, field in self.fields.items():
            field.setPlainText(p[key])
        self.memory_input.clear()
        self._render_memories()
        self._changed()

    def _select(self, index):
        if index < 0 or index == self.index:
            return
        try:
            self.profiles[self.index] = self._snapshot()
        except ValueError as e:
            self.status.setText(str(e))
            self._refresh_profiles()
            return
        self.index = index
        self._load()

    def _new(self):
        try:
            self.profiles[self.index] = self._snapshot()
            if len(self.profiles) >= 30:
                raise ValueError("最多保存 30 位联系人")
        except ValueError as e:
            self.status.setText(str(e))
            return
        self.profiles.append(new_profile())
        self.index = len(self.profiles) - 1
        self._refresh_profiles()
        self._load()

    def _save(self):
        try:
            self.profiles[self.index] = self._snapshot()
            drafts = self.store.merge_drafts(self.profiles, self.baseline)
            for p in drafts:
                partner_context(p)
            self.store.save(drafts)
        except Exception as e:
            self.status.setText(str(e) if isinstance(e, ValueError) else "加密保存失败，资料没有写入明文文件。")
            return False
        self.profiles = copy.deepcopy(self.store.profiles)
        self.baseline = copy.deepcopy(self.store.profiles)
        self._refresh_profiles()
        self._load()
        self.on_saved()
        self.status.setText("档案、采纳的记忆与待办已加密保存。未勾选的完整历史仅留在本次内存。")
        return True

    def sync_from_store(self):
        try:
            self.profiles[self.index] = self._snapshot()
            selected = self.profiles[self.index]["id"]
            self.profiles = self.store.merge_drafts(self.profiles, self.baseline)
            self.baseline = copy.deepcopy(self.store.profiles)
            self.index = next((i for i, p in enumerate(self.profiles) if p["id"] == selected), 0)
            self._refresh_profiles()
            self._load()
        except ValueError as e:
            self.status.setText(str(e))

    def forget_messages(self, title, entries):
        # A hidden preparation draft may contain an unsaved copy of this chat.
        # Preserve other edits, but do not let that copy restore forgotten data.
        self.sync_from_store()
        self.profiles = [forget_profile(p, entries)[0] if p["binding"] == title else p
                         for p in self.profiles]
        self._load()

    def _save_return(self):
        if self._save():
            self._return()

    def _return(self):
        self.hide()
        if self.parentWidget():
            self.parentWidget().raise_()
            self.parentWidget().activateWindow()

    def _delete(self):
        if self.store.error:
            self.status.setText(self.store.error)
            return
        if QMessageBox.question(self, "删除联系人档案", "删除当前联系人保存的资料、记忆与待办？") != QMessageBox.Yes:
            return
        try:
            remaining = self.store.merge_drafts([p for i, p in enumerate(self.profiles) if i != self.index], self.baseline)
            self.store.save(remaining)
        except Exception:
            self.status.setText("删除保存失败，原加密档案已保留。")
            return
        self.profiles, self.baseline = copy.deepcopy(remaining) or [new_profile()], copy.deepcopy(remaining)
        self.index = 0
        self._refresh_profiles()
        self._load()
        self.on_saved()

    def _bind_current(self):
        title = self.current_chat()
        if not title:
            self.status.setText("尚未识别到微信会话。请先在首页点击生成识别名称，或手动填完整会话名称。")
            return
        self.binding.setText(title)
        self.status.setText("请核对会话名称，并确保这是单聊；保存后才生效。")

    def _import_current(self):
        if not self.current_chat() or self.binding.text().strip() != self.current_chat():
            self.status.setText("只能载入本档案绑定的当前会话，先核对绑定名称。")
            return
        messages = self.current_messages()
        if not messages or any(len(m) > 2 and m[2] for m in messages):
            self.status.setText("没有可载入的单聊记录。")
            return
        self.reference.setPlainText(format_transcript(messages))

    def import_history_file(self, path):
        raw = Path(path).read_bytes()
        if len(raw) > 120000:
            raise ValueError("TXT 文件过大，请分段导入（最多 24000 字）")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("gb18030")
        parse_transcript(text)
        self.reference.setPlainText(text)

    def _import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入旧对话 TXT（我： / 她：）", "", "聊天文字 (*.txt)")
        if path:
            try:
                self.import_history_file(path)
                self.status.setText("已在本机读取 TXT；核对说话人后，点击 AI 点评。")
            except Exception as e:
                self.status.setText(str(e) if isinstance(e, ValueError) else "无法读取 TXT 文件。")

    def _request(self):
        if self.busy:
            return
        try:
            p = self._snapshot()
            messages = parse_transcript(p["reference_dialogue"])
            context = partner_context({**p, "reference_dialogue": ""})
            if not settings.has_llm_key():
                raise ValueError("请先在主页面设置中填写起草模型 API Key。")
            options = model_options()
        except ValueError as e:
            self.status.setText(str(e))
            return
        self.busy = True
        revision = self.revision
        self.observe_button.setEnabled(False)
        self.status.setText("正在点评双方与整体对话…")
        def work():
            try:
                result = review_dialogue(messages, context, provider=options["provider"], model=options["model"],
                    base_url=options["base_url"], api_key=options["llm_api_key"])
                self.completed.emit(revision, result, "")
            except Exception as e:
                self.completed.emit(revision, {}, f"点评失败（{type(e).__name__}），请检查网络和模型设置。")
        threading.Thread(target=work, daemon=True).start()

    def _completed(self, revision, result, error):
        self.busy = False
        self.observe_button.setEnabled(True)
        if revision != self.revision:
            self.status.setText("资料或历史已变，旧点评已丢弃，请重新点评。")
            return
        if error:
            self.status.setText(error)
            return
        self.review = result
        lines = []
        for subject in ("我", "对方", "整体对话"):
            item = result.get("summary", {}).get(subject)
            lines.append(f"{subject}：{item['note']}\n依据：{item['evidence']}" if item else f"{subject}：依据不足，暂不评价。")
        self.result_note.setText("\n\n".join(lines))
        self.observation_list.clear()
        for kind, entries in (("observe", result.get("observations", [])), ("memory", result.get("memories", []))):
            for i, entry in enumerate(entries):
                text = (f"观察 · {entry['subject']} · {entry['confidence']}\n{entry['note']}\n依据：{entry['evidence']}"
                        if kind == "observe" else f"可存原文记忆 · {entry['subject']}\n{entry['text']}")
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, (kind, i))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.observation_list.addItem(item)
        todos = result.get("todos", [])
        self.todo_button.setEnabled(bool(todos))
        self.todo_button.setText(f"将 {len(todos)} 条约定加入待办（之后点保存）" if todos else "没有有依据的约定")
        if todos:
            self.todo_button.setToolTip("\n".join(f"{t['when']} · {t['event']} · {t['location']}" for t in todos))
        self.status.setText("点评完成。观察需勾选采纳；原文记忆和约定可加入档案。")

    def _accept_observations(self):
        selected = [self.observation_list.item(i).data(Qt.UserRole) for i in range(self.observation_list.count())
                    if self.observation_list.item(i).checkState() == Qt.Checked]
        if not selected:
            self.status.setText("先勾选想采纳的观察或原文记忆。")
            return
        reviewed = copy.deepcopy(self.review)
        notes, memories = [], []
        for kind, i in selected:
            if kind == "observe":
                item = self.review["observations"][i]
                notes.append(f"[推测/{item['subject']}] {item['note']}（依据：{item['evidence']}）")
            else:
                memories.append(self.review["memories"][i])
        value = "\n".join(filter(None, [self.fields["confirmed_notes"].toPlainText(), *notes]))
        if len(value) > MAX_FIELD:
            self.status.setText("观察过多，请精简后再加入。")
            return
        self.profiles[self.index], _ = merge_review(self.profiles[self.index], {"memories": memories})
        self.fields["confirmed_notes"].setPlainText(value)
        self._render_memories()
        self._completed(self.revision, reviewed, "")
        self.status.setText("已加入准备资料，点保存后生效。")

    def _accept_todos(self):
        self.profiles[self.index], _ = merge_review(self.profiles[self.index], {"todos": self.review.get("todos", [])})
        self.status.setText("已加入待办草稿，保存后显示在主页面；旧对话的相对日期请手动核对。")
        self.todo_button.setEnabled(False)

    def _render_memories(self):
        self.memory_list.clear()
        for m in self.profiles[self.index].get("memories", []):
            item = QListWidgetItem(f"{m['subject']} · {m['origin']} · {m['created']}\n{m['text']}")
            item.setData(Qt.UserRole, m["id"])
            self.memory_list.addItem(item)

    def _add_memory(self):
        text = self.memory_input.toPlainText().strip()
        if not text or len(text) > 500:
            self.status.setText("请输入 1–500 字的重要事实或经历。")
            return
        subject = self.memory_subject.currentText()
        memory = normalize_memory({"id": fingerprint(subject, text), "subject": subject, "text": text, "origin": "手动确认"})
        p = self.profiles[self.index]
        p["dismissed"] = [x for x in p["dismissed"] if x != memory["id"]]
        self.profiles[self.index], _ = merge_review(p, {"memories": [memory]})
        self.memory_input.clear()
        self._render_memories()
        self._changed()
        self.status.setText("已加入记忆草稿，保存后生效。")

    def _remove_memory(self):
        item = self.memory_list.currentItem()
        if not item:
            return
        ident = item.data(Qt.UserRole)
        p = self.profiles[self.index]
        p["memories"] = [m for m in p["memories"] if m["id"] != ident]
        p["dismissed"].append(ident)
        self._render_memories()
        self._changed()
        self.status.setText("记忆已从草稿移除，保存后生效。")
