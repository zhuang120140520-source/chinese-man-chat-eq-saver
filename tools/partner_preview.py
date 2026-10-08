"""Synthetic visual checks, never opens the user's private store."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
from pathlib import Path
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.partner_panel import PartnerPanel
from app.partner_store import ProfileStore
from app.overlay import Overlay
from app.forget_dialog import ForgetDialog
from app.start_dialog import StartDialog
from core.partner import new_profile
from core.partner_memory import normalize_todo

app = QApplication([])
QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
out = Path("qa-output")
out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    store = ProfileStore(Path(temp) / "synthetic.dpapi")
    p = new_profile()
    p.update(name="小雨（虚构示例）", stage="暧昧了解", binding="小雨", auto=True,
             preferences="喜欢摄影展、小咖啡馆，周末通常有空", goal="邀约见面 / 活动",
             goal_detail="周六下午看摄影展，先问意愿；时间不合适可改周日",
             my_facts="普通上班族，周六下午有空", persona="自然、自信、稍微幽默", speech_style="短句，不用表情")
    p["todos"] = [normalize_todo({"event":"一起看摄影展", "when":"周六下午三点", "day":"2026-10-10", "location":"展览馆", "status":"confirmed"}),
                  normalize_todo({"event":"去吃新开的火锅", "when":"下周时间再定", "status":"pending"})]
    store.profiles = [p]
    panel = PartnerPanel(store, lambda:"小雨", lambda:[], lambda:None)
    panel.show()
    app.processEvents()
    panel.grab().save(str(out / "profile-0.6.1.png"))
    panel.tabs.setCurrentWidget(panel.history_page)
    panel.reference.setPlainText("我：上次那个展还挺有意思\n她：是呀 下次有新展也叫我\n我：周六下午三点在展览馆看展？\n她：好呀，周六下午三点可以，展览馆见")
    panel._completed(panel.revision, {"summary":{
        "我":{"note":"主动提出具体安排，表达直接自然。", "evidence":"周六下午三点在展览馆看展？"},
        "对方":{"note":"回应积极，也明确了时间与地点。", "evidence":"好呀，周六下午三点可以，展览馆见"},
        "整体对话":{"note":"话题围绕共同兴趣展开，已落实一次邀约。", "evidence":"好呀，周六下午三点可以，展览馆见"}},
        "observations":[{"subject":"双方", "note":"可能喜欢通过共同活动增进了解", "confidence":"待确认", "evidence":"下次有新展也叫我"}],
        "memories":[], "todos":p["todos"][:1]}, "")
    app.processEvents()
    panel.grab().save(str(out / "history-0.6.1.png"))
    panel.history_page.widget().grab().save(str(out / "history-full-0.6.1.png"))
    panel.close()
    ov = Overlay(on_fill=lambda text:None)
    ov.set_chat("小雨")
    ov.partnerLabel.setText("档案：小雨 · 点击后整理记忆与待办")
    ov.set_partner_profile(p)
    ov.log_message("me", "周六一起看摄影展？", chat="小雨", message_id="one")
    ov.log_message("her", "周六下午应该可以 别太远就行", chat="小雨", message_id="two")
    ov._empty_text()
    app.processEvents()
    ov.win.grab().save(str(out / "idle-0.6.1.png"))
    ov.home.widget().grab().save(str(out / "idle-full-0.6.1.png"))
    ov.show({"candidates":["那就周六下午，我找个近点的展，你哪个区域比较方便？", "行，我看看你附近有什么展。", "不折腾你，就在附近看看？"],
             "best_index":0, "answers":{"danger_level":{"score":4}, "best_action":{"choice":"make_plan"}}})
    for _ in range(8):
        app.processEvents()
    ov.win.grab().save(str(out / "home-0.6.1.png"))
    ov.home.widget().grab().save(str(out / "home-full-0.6.1.png"))
    ov.open_settings()
    app.processEvents()
    ov.win.grab().save(str(out / "settings-0.6.1.png"))
    ov.settingsPage.widget().grab().save(str(out / "settings-full-0.6.1.png"))
    ov._back_home()
    start = StartDialog("小雨（虚构示例）", [
        {"id":"old", "who":"her", "text":"昨天的消息：明天再聊"},
        {"id":"one", "who":"me", "text":"周六一起看摄影展？"},
        {"id":"two", "who":"her", "text":"周六下午应该可以 别太远就行"}], parent=ov.win)
    start.list.setCurrentRow(1)
    start.show()
    app.processEvents()
    start.grab().save(str(out / "start-0.6.1.png"))
    start.close()
    forget = ForgetDialog(ov.feeds["小雨"],
        preview=lambda ids:{"messages":len(ids), "memories":1 if ids else 0, "todos":1 if ids else 0},
        forget=lambda ids:(True, ""), parent=ov.win)
    forget.select_all(True)
    forget.show()
    app.processEvents()
    forget.grab().save(str(out / "forget-0.6.1.png"))
    forget.close()
    ov.win.close()
print("Synthetic profile, history and homepage previews saved.")
