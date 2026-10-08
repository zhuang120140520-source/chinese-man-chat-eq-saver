"""Explicit live integration check using fictional data only; never writes chat output."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.partner_runtime import model_options
from core.engine import analyze
from core.partner import new_profile, partner_context
from core.profile_analysis import review_dialogue

p = new_profile()
p.update(name="虚构测试对象", stage="暧昧了解", preferences="喜欢小型摄影展，不喜欢很吵的活动",
         shared_history="上次一起看过摄影展，她说下次有新展也可以叫她",
         my_facts="普通上班族，周六下午有空", persona="自信、自然、有主见",
         speech_style="短句，用词自然，不叫宝宝，不用表情", goal="邀约见面 / 活动",
         goal_detail="想约周六下午看摄影展，不逼她确定，日期不合适就留备选")
messages = [("me", "上次那个展还挺有意思"), ("her", "是呀 下次有新展也叫我"),
            ("me", "这周六有个新的 想不想去看看"), ("her", "周六下午应该可以 别太远就行")]
options = model_options()
options["context"] = len(messages)
result = analyze(messages, p["stage"], partner_context=partner_context(p), timeout=45, **options)
assert 1 <= len(result["candidates"]) <= 3
print("Fictional reply integration: OK")
for reply in result["candidates"]:
    print(reply)
review = review_dialogue(messages + [("her", "我喜欢小型摄影展"),
    ("me", "2026年10月10日下午在展览馆看展？"), ("her", "好呀，2026年10月10日下午可以，展览馆见")],
    partner_context(p), provider=options["provider"],
    model=options["model"], base_url=options["base_url"], timeout=45, api_key=options["llm_api_key"])
assert all(s in review["summary"] for s in ("我", "对方", "整体对话")), "Missing balanced summaries"
assert review["memories"], "No evidence-bound memories returned"
assert review["todos"], "No evidence-bound arrangements returned"
print("Fictional balanced review: OK; memories:", len(review["memories"]), "; todos:", len(review["todos"]))
