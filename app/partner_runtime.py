"""Capture an immutable model/configuration snapshot before starting a request."""
from app import settings

def model_options():
    judge_key = settings.jev_key()
    draft_key = settings.llm_key()
    return dict(model=settings.draft_model() or None, provider=settings.draft_provider(),
                base_url=settings.draft_base_url() or None, thinking=settings.thinking(),
                jev_provider=settings.jev_provider(), jev_model=settings.jev_model() or None,
                style=settings.style(), context=settings.context(),
                jev_api_key=judge_key, llm_api_key=draft_key)
