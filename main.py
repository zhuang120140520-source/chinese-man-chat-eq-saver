# -*- coding: utf-8 -*-
"""父进程：点击按钮后才截图 + OCR，首次先在本机选择聊天起点，确认后才调模型。
回复由人确认发送；不启动后台自动采集。
上下文、结果、聊天记录都按会话名（子进程 OCR 头部标题得来）分开存，切会话不串味。

    pip install rapidocr-onnxruntime numpy windows-capture PySide6-Fluent-Widgets
两个模型（判断 Jev / 起草语言模型）的来源和 key 在独立设置页填写，不用改代码。IDE 里直接 Run。
"""
import ctypes
import copy
import multiprocessing
import queue
import threading
import traceback
import time
import uuid
from datetime import datetime
from collections import deque

from app import settings, update, worker
from app.capture import find_chat_hwnd
from app.fill import fill
from app.overlay import Overlay
from app.version import VERSION
from core.engine import analyze
from core.partner import partner_context
from core.partner_memory import merge_review, normalize_todo
from core.profile_analysis import review_dialogue
from core.chat_history import forget_profile, from_start
from app.partner_store import ProfileStore
from app.partner_runtime import model_options
from app.i18n import T

# {会话名: {history, result, rev, target, senders}}：每个会话各自的上下文、上次结果和版本号，互不串味
# history 里是 [(who, text, name)]，engine 只认 her/me，name 是群里的发言人（单聊/自己说的是 None）；
# 只是缓冲区，实际喂模型条数使用保留的参考上下文设置（默认 10 条）
# senders：这个群里发过言的人，去重、最近的排最前；target：用户挑的回复对象（None = 跟着最近那个走）
chats = {}
state = {"area": None, "busy": False, "rerun": None, "hwnd": None, "chat": ""}
results = queue.Queue()
update_result = queue.Queue()  # 独立小队列，别跟 results 的 (kind, r, title, revision) 形状搅在一起
partner_store = None
partner_panel = None
review_results = queue.Queue()


def refresh_partner_label():
    if partner_store:
        ov.register_profile_chats([p["binding"] for p in partner_store.profiles])
    title = ov.current_chat() or state["chat"]
    profile = partner_store.for_chat(title) if partner_store else None
    if profile:
        flag = "点击后整理记忆与待办" if profile["auto"] else "点击生成回复，记忆整理未开启"
        ov.partnerLabel.setText(f"档案：{profile['name']} · {flag}")
    else:
        ov.partnerLabel.setText("先进入准备资料，在「对方与关系」填微信聊天名并保存，完成联系人绑定。")
    ov.set_partner_profile(profile)


def on_profiles_saved():
    # An in-flight result for old facts/goals must never be used after edits.
    for chat in chats.values():
        chat["rev"] += 1
        chat["result"] = None
        if "review" in chat:
            chat["review"]["token"] += 1
            chat["review"]["due"] = None
    state["rerun"] = None
    cancel_analysis()
    state["snapshot"] = state["selection"] = None
    ov.close_start_dialog()
    ov.set_snapshot_pending(False)
    ov.invalidate_replies()
    ov.show_cached(None)
    refresh_partner_label()


def open_partner_panel():
    global partner_panel
    if partner_panel is None:
        from app.partner_panel import PartnerPanel
        partner_panel = PartnerPanel(partner_store, current_chat=lambda: state["chat"],
            current_messages=lambda: list(chat_of(state["chat"])["history"]),
            on_saved=on_profiles_saved, parent=ov.win)
    else:
        partner_panel.sync_from_store()
    partner_panel.show()
    partner_panel.raise_()
    partner_panel.activateWindow()


def chat_of(title):
    return chats.setdefault(title, {"history": deque(maxlen=60), "result": None, "rev": 0,
                                    "target": None, "senders": [], "records": deque(maxlen=60), "forgotten": set(), "started": False,
                                    "review": {"busy": False, "due": None, "last": 0, "token": 0}})

def on_goal_changed(title, goal, detail):
    profile = partner_store.for_chat(title)
    if not profile:
        return
    try:
        partner_store.replace_profile({**profile, "goal": goal, "goal_detail": detail})
    except Exception:
        ov.set_status("目标保存失败，原档案已保留。", "error")
        return
    on_profiles_saved()
    ov.set_status("目标已切换并加密保存；对方说完后，点击按钮生成。")

def regenerate(title):
    msgs = list(chat_of(title)["history"])
    if not msgs or msgs[-1][0] != "her":
        ov.set_status("等待对方的新消息后再生成回复。")
        return
    if state["busy"]:
        state["rerun"] = (title, msgs, True)
        ov.set_busy(True)
    else:
        start_analyze(title, msgs, force=True)

def cancel_analysis():
    if state.get("cancel"):
        state["cancel"].set()
    state.update(busy=False, job=None, rerun=None)
    ov.set_busy(False)

def capture_and_generate(title):
    global child
    if state.get("snapshot") or state.get("selection"):
        return
    try:
        hwnd, found = find_chat_hwnd()
    except RuntimeError:
        ov.set_status("未找到微信窗口，请打开后再生成。", "warning")
        return
    state.update(hwnd=hwnd, app=found.key)
    if child is None or not child.is_alive():
        # Occurrence IDs are local to this reader process. Reconfirm the start
        # if it must be recreated, rather than admitting old visible messages.
        for c in chats.values():
            c["started"] = False
        child = spawn_worker()
    profile = partner_store.for_chat(title)
    request_id = uuid.uuid4().hex
    cancel_analysis()
    if title:
        chat_of(title)["rev"] += 1
        chat_of(title)["result"] = None
    state["snapshot"] = {"id": request_id, "expected": title,
                         "profile_id": profile["id"] if profile else None,
                         "started": time.monotonic(), "hwnd": hwnd}
    ov.invalidate_replies()
    ov.set_snapshot_pending(True)
    ov.set_status("正在截图…", "busy")
    commands.put(("snapshot", request_id, hwnd, found.key))


def accept_snapshot(request_id, start_id=None):
    request = state.get("selection")
    if not request or request["id"] != request_id:
        return  # A profile edit or forgetting operation invalidated this preview.
    title, rows = request["title"], request["rows"]
    c = chat_of(title)
    profile = partner_store.for_chat(title)
    if not profile or profile["id"] != request["profile_id"]:
        state["selection"] = None
        ov.set_snapshot_pending(False)
        ov.set_status("联系人档案已变化，请重新点击生成。", "warning")
        return
    if not c["started"]:
        if start_id is None:
            state["selection"] = None
            ov.set_snapshot_pending(False)
            ov.set_status("已返回，本次截图未录入，也未调用模型。")
            return
        try:
            rows, ignored = from_start(rows, start_id)
        except ValueError:
            return
        c["forgotten"].update(ignored)
        c["records"].clear()
        c["history"].clear()
        c["started"] = True
    state["selection"] = None
    ov.set_snapshot_pending(False)
    ingest_records(title, rows, manual=True)
    queue_memory_review(title, manual=True)
    regenerate(title)

def ingest_records(title, records, manual=False):
    c = chat_of(title)
    profile = partner_store.for_chat(title)
    ignored = c["forgotten"] | set(profile.get("forgotten_sources", []) if profile else [])
    records = [copy.deepcopy(r) for r in records if r["id"] not in ignored]
    previous = list(c["records"])
    known = {r["id"] for r in previous}
    if manual:
        positions = [i for i, r in enumerate(previous) if r["id"] in {v["id"] for v in records}]
        previous = previous[:min(positions)] if positions else previous
    combined = previous + [r for r in records if manual or r["id"] not in known]
    c["records"] = deque(combined[-60:], maxlen=60)
    c["history"] = deque([(r["who"], r["text"], r["name"]) for r in c["records"]], maxlen=60)
    existing_feed = {e[4] for e in ov.feeds.get(title, []) if not isinstance(e, str) and len(e) > 4}
    added = [r for r in records if r["id"] not in existing_feed]
    for r in added:
        ov.log_message(r["who"], r["text"], r["name"], chat=title, message_id=r["id"])
    c["senders"] = list(dict.fromkeys(r["name"] for r in reversed(c["records"]) if r["who"] == "her" and r["name"]))
    if manual or added:
        c["rev"] += 1
        c["result"] = None
        if title == ov.current_chat():
            ov.invalidate_replies()
    ov.set_targets(title, c["senders"], target_of(title))
    return added

def _selected_entries(title, ids):
    selected = set(ids)
    return [{"id": e[4], "who": e[0], "name": e[1], "text": e[2]}
            for e in ov.feeds.get(title, []) if not isinstance(e, str) and len(e) > 4 and e[4] in selected]

def preview_forget(title, ids):
    entries = _selected_entries(title, ids)
    p = partner_store.for_chat(title)
    counts = forget_profile(p, entries)[1] if p else {"memories":0, "todos":0, "observations":0, "reference":0}
    return {**counts, "messages": len(entries)}

def forget_selected(title, ids):
    entries = _selected_entries(title, ids)
    if not entries:
        return False, "没有找到可忘记的聊天，请重新选择。"
    selected = {e["id"] for e in entries}
    profile = partner_store.for_chat(title)
    if profile:
        updated, _counts = forget_profile(profile, entries)
        try:
            partner_store.replace_profile(updated)
        except Exception:
            return False, "加密保存失败，聊天与原档案已保留。"
    c = chat_of(title)
    c["forgotten"].update(selected)
    c["records"] = deque([r for r in c["records"] if r["id"] not in selected], maxlen=60)
    c["history"] = deque([(r["who"], r["text"], r["name"]) for r in c["records"]], maxlen=60)
    c["rev"] += 1
    c["result"] = None
    c["review"]["token"] += 1
    c["review"]["due"] = None
    cancel_analysis()
    state["snapshot"] = state["selection"] = None
    ov.close_start_dialog()
    ov.set_snapshot_pending(False)
    ov.remove_messages(title, selected)
    if title == ov.current_chat():
        ov.show_cached(None)
    refresh_partner_label()
    # Keep occurrence tombstones, rather than banning the text of future messages.
    if partner_panel is not None:
        partner_panel.forget_messages(title, entries)
    ov.set_status(f"已忘记 {len(entries)} 条聊天及相关自动记录。")
    return True, ""

def on_todo_action(title, action, todo):
    profile = partner_store.for_chat(title)
    if not profile:
        return
    p = copy.deepcopy(profile)
    ident = todo["id"]
    if action == "delete":
        p["todos"] = [t for t in p["todos"] if t["id"] != ident]
        p["dismissed"].append(ident)
    elif action == "add":
        p["todos"].append(normalize_todo(todo))
    elif action == "edit":
        p["todos"] = [normalize_todo(todo) if t["id"] == ident else t for t in p["todos"]]
    else:
        return
    try:
        partner_store.replace_profile(p)
    except Exception:
        ov.set_status("待办保存失败，原档案已保留。", "error")
        return
    # In-flight replies must not promise an old arrangement after a todo is edited.
    on_profiles_saved()
    ov.set_status("待办已在本机加密保存。")

def queue_memory_review(title, manual=False):
    p = partner_store.for_chat(title)
    c = chat_of(title)
    if p and p["auto"] and not c["senders"] and settings.has_llm_key():
        c["review"]["token"] += 1
        c["review"]["due"] = time.monotonic() + 4
        c["review"]["manual"] = manual or c["review"].get("manual", False)

def memory_review_bg(title, profile_id, token, msgs, context, options, anchor, message_ids=None):
    try:
        review = review_dialogue(msgs, context, provider=options["provider"], model=options["model"],
                                base_url=options["base_url"], api_key=options["llm_api_key"], anchor=anchor, message_ids=message_ids)
        review_results.put((title, profile_id, token, review, ""))
    except Exception as e:
        review_results.put((title, profile_id, token, {}, type(e).__name__))

def memory_tick():
    day = datetime.now().date().isoformat()
    if state.get("todo_day") != day:
        state["todo_day"] = day
        ov.todoBoard.set_profile(partner_store.for_chat(ov.current_chat()))
    while not review_results.empty():
        title, profile_id, token, review, error = review_results.get()
        job = chat_of(title)["review"]
        job["busy"] = False
        p = partner_store.for_chat(title)
        if not p or p["id"] != profile_id or not p["auto"] or job["token"] != token:
            continue
        if error:
            if title == ov.current_chat():
                ov.set_status("回复功能可继续使用；本次记忆 / 待办整理失败，稍后新消息会再尝试。", "warning")
            continue
        merged, changed = merge_review(p, review)
        if changed:
            try:
                partner_store.replace_profile(merged)
            except Exception:
                ov.set_status("记忆 / 待办加密保存失败，原档案已保留。", "warning")
                continue
            # Update todo strips without invalidating the replies currently in use.
            if title == ov.current_chat():
                ov.todoBoard.set_profile(merged)
    now = time.monotonic()
    for title, c in chats.items():
        job, p = c["review"], partner_store.for_chat(title)
        if not job.get("manual"):
            continue
        if not job["due"] or job["busy"] or now < max(job["due"], job["last"] + 20):
            continue
        job["due"] = None
        if not p or not p["auto"] or c["senders"] or not settings.has_llm_key():
            continue
        try:
            context, options = partner_context(p), model_options()
        except ValueError:
            continue
        job.update(busy=True, last=now, manual=False)
        threading.Thread(target=memory_review_bg, args=(title, p["id"], job["token"],
            list(c["history"]), context, options, datetime.now().date().isoformat(),
            [r["id"] for r in c["records"]]), daemon=True).start()


def target_of(title):
    """这个会话现在的回复对象：用户挑过且人还在就用它，否则用最近说话的那个；单聊没有发言人 → None。"""
    chat = chat_of(title)
    if chat["target"] in chat["senders"]:
        return chat["target"]
    return chat["senders"][0] if chat["senders"] else None


def fill_reply(text):
    if ov.current_chat() != state["chat"] or not partner_store.for_chat(state["chat"]):
        raise RuntimeError("当前微信会话与档案不匹配，请核对后复制回复")
    if state["hwnd"] is None:  # 子进程重开过，hwnd 可能换了，用最新的
        raise RuntimeError(T("未找到聊天窗口，请确认已经打开"))
    if state["area"] is None:
        raise RuntimeError(T("输入区域尚不可用，请确认聊天窗口可见（不要最小化）"))
    if settings.reply_target() and ov.at_prefix_enabled():
        target = target_of(ov.current_chat())  # 填进去的是界面上正看着的那个会话的对象
        if target:
            text = f"@{target} " + text  # 纯文本，微信不认成真正的 @，只是让群里看得出在跟谁说
    fill(state["hwnd"], state["area"], text)


def spawn_worker():
    """Start an idle reader; it captures only after a snapshot command."""
    p = multiprocessing.Process(target=worker.run, args=(q, debug_on, commands), daemon=True)
    p.start()
    return p

def set_debug(on):
    """调试视图开关：开 → 开窗 + 置位（子进程这才开始送帧，一帧 2~3MB）；关 → 清掉 + 收窗。"""
    global dbg
    if not on:
        debug_on.clear()
        if dbg is not None:
            dbg.hide()
        return
    if dbg is None:
        from app.debugwin import DebugWindow

        dbg = DebugWindow(on_close=on_debug_closed)
    dbg.show()
    debug_on.set()


def on_debug_closed():
    """用户直接关了调试窗 = 把开关也关了，否则设置页显示开着但没窗。"""
    debug_on.clear()
    ov.set_debug_switch(False)
    settings.save(debug_view_on=False)


def on_language_changed():
    """主界面切换语言后，同步刷新已经打开过的调试窗。"""
    if dbg is not None:
        dbg.retranslate()




def analyze_bg(msgs, title, revision, context_snapshot, options, job_id, cancel):
    """后台线程只跑网络调用，结果丢队列；UI 只在主线程的 tick 里动（Qt 不能跨线程碰）。"""
    try:
        results.put(("ok", analyze(msgs, context_snapshot["关系阶段"],
                                   partner_context=context_snapshot, cancelled=cancel.is_set,
                                   on_progress=lambda phase: results.put(("progress", phase, title, revision, job_id)), **options),
                     title, revision, job_id))
    except Exception as e:
        results.put(("err", f"分析失败（{type(e).__name__}），请检查模型服务设置", title, revision, job_id))


def check_update_bg():
    """启动时后台查一次新版本，跟 analyze_bg 一个套路：网络调用在线程里，UI 只在 tick() 里动。"""
    r = update.check_latest(VERSION)
    if r:
        update_result.put(r)


def start_analyze(title, msgs, force=False):
    if not force or state.get("snapshot") or state.get("selection"):
        return
    profile = partner_store.for_chat(title) if partner_store else None
    if not profile or any(len(m) > 2 and m[2] for m in msgs):
        if not state["busy"]:
            ov.set_busy(False)
            ov.set_status("请先绑定单聊档案，再点击生成回复。")
        return
    if not settings.has_jev_key():
        ov.set_status("请先在设置中配置模型", "warning")
        return
    if not settings.has_llm_key():
        ov.set_status(lambda name=settings.draft_provider_name():
                      f"{T('起草来源 ')}{name}{T(' 没填密钥，去设置里补上')}", "warning")
        return
    try:
        snapshot = partner_context(profile)
        options = model_options()
    except ValueError:
        ov.set_status("补充历史的格式有误，请在档案里检查", "warning")
        return
    state["busy"] = True
    state["job"], state["cancel"] = uuid.uuid4().hex, threading.Event()
    ov.set_busy(True)
    threading.Thread(target=analyze_bg, args=(msgs, title, chat_of(title)["rev"], snapshot, options, state["job"], state["cancel"]),
                     daemon=True).start()


def on_target_change(title, name):
    chat = chat_of(title)
    chat["target"] = name
    chat["rev"] += 1
    chat["result"] = None
    cancel_analysis()
    ov.invalidate_replies()

def drain():
    """Only explicit snapshot results can admit dialogue; legacy auto packets are ignored."""
    while True:
        try:
            msg = q.get_nowait()
        except queue.Empty:
            return
        kind = msg[0]
        if kind == "debug":
            if dbg is not None:
                dbg.show_packet(msg[1])
            continue
        if kind not in ("snapshot_status", "snapshot_error", "snapshot"):
            continue
        request = state.get("snapshot")
        if not request or request["id"] != msg[1]:
            continue
        if kind == "snapshot_status":
            ov.set_status(msg[2], "busy")
            continue
        state["snapshot"] = None
        if kind == "snapshot_error":
            ov.set_snapshot_pending(False)
            ov.set_status(msg[2], "error")
            continue
        _, _, title, visible, rect, _ocr_ms = msg
        state.update(chat=title, area=rect, hwnd=request["hwnd"])
        ov.set_chat(title)
        refresh_partner_label()
        profile = partner_store.for_chat(title)
        error = ""
        if request["expected"] and title != request["expected"]:
            error = "当前微信会话与刚才选择的联系人不同，请核对后重新点击。"
        elif not profile:
            error = "已识别会话名称，请在准备页绑定联系人档案后再点击。"
        elif request["profile_id"] and profile["id"] != request["profile_id"]:
            error = "联系人档案已变化，请重新点击生成。"
        elif not visible:
            error = "没有识别到聊天文字，请让最新消息显示在微信窗口中。"
        elif any(r["name"] for r in visible):
            error = "识别到群聊发言人，当前伴侣档案仅用于单聊。"
        if error:
            ov.set_snapshot_pending(False)
            ov.set_status(error, "warning")
            continue
        c = chat_of(title)
        ignored = c["forgotten"] | set(profile.get("forgotten_sources", []))
        rows = [r for r in visible if r["id"] not in ignored]
        if not rows:
            ov.set_snapshot_pending(False)
            ov.set_status("当前画面里的消息已忽略，请显示新消息后再点击。")
            continue
        state["selection"] = {**request, "title": title, "rows": rows, "profile_id": profile["id"]}
        if not c["started"]:
            ov.set_status("首次截图：请选择本轮第一条消息，确认后才录入和生成。")
            ov.select_chat_start(title, rows, lambda start_id, rid=request["id"]: accept_snapshot(rid, start_id))
        else:
            accept_snapshot(request["id"])

def tick():
    try:
        drain()
        memory_tick()
        if state.get("snapshot") and time.monotonic() - state["snapshot"]["started"] > 25:
            state["snapshot"] = None
            ov.set_snapshot_pending(False)
            ov.set_status("截图识别超时，请保持微信窗口可见后重试。", "warning")
        while not update_result.empty():
            latest, url = update_result.get()
            ov.set_update(latest, url)
        while not results.empty():
            kind, r, title, revision, job_id = results.get()
            if job_id != state.get("job"):
                continue
            if kind == "progress":
                if title == ov.current_chat():
                    ov.set_status(r, "busy")
                continue
            state["busy"] = False
            if state["rerun"]:  # 分析期间又来了新消息，接着跑最新的
                (t, msgs, force), state["rerun"] = state["rerun"], None
                start_analyze(t, msgs, force=force)
                continue
            if revision != chat_of(title)["rev"]:  # 这个会话后来又说话了，这份结果过期了
                ov.set_busy(False)
                continue
            if kind == "ok":
                chat_of(title)["result"] = r  # 先存着；正看着这个会话才立刻贴上去
                if title == ov.current_chat():
                    ov.show(r)
                else:
                    ov.set_busy(False)
            else:
                ov.set_busy(False)
                ov.set_status("生成失败，请检查网络和服务设置后，点击按钮重试。", "error")
                ov.log(r)
    except Exception:
        traceback.print_exc()  # 一帧出错不退出
    ov.after(50, tick)


def initialize():
    """Build the UI without locating WeChat, capturing frames or starting readers."""
    global q, commands, debug_on, child, dbg, partner_store, ov
    q = multiprocessing.Queue()
    commands = multiprocessing.Queue()
    debug_on = multiprocessing.Event()  # 同上，置位=子进程往队列里送整帧给调试窗
    child = dbg = None
    partner_store = ProfileStore()
    ov = Overlay(on_fill=fill_reply,
                 on_target_change=on_target_change, on_toggle_debug=set_debug,
                 on_language_changed=on_language_changed,
                 on_partner_open=open_partner_panel, on_config_saved=on_profiles_saved,
                 on_goal_changed=on_goal_changed, on_todo_action=on_todo_action,
                 on_context_view=refresh_partner_label, on_regenerate=capture_and_generate,
                 on_forget=forget_selected, on_forget_preview=preview_forget,
                 result_of=lambda t: chats.get(t, {}).get("result"))
    ov.set_status("对方说完后，点击按钮截图并生成回复。启动时不会读取聊天。")
    refresh_partner_label()
    if settings.debug_view():  # 上次开着就直接开回来
        set_debug(True)
    if not settings.has_jev_key() or not settings.has_llm_key():
        ov.set_status("请先在设置中配置模型", "warning")
        ov.after(0, ov.open_settings)
    if settings.check_update() and update.parse_version(VERSION):  # 开发版没有版本号，不查也不烦源码用户
        threading.Thread(target=check_update_bg, daemon=True).start()
    ov.after(50, tick)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    ctypes.windll.user32.SetProcessDPIAware()
    initialize()
    try:
        ov.run()
    finally:
        if child is not None:
            child.terminate()
