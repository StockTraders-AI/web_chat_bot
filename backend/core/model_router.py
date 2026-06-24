from settings import DEFAULT_MODEL, ALLOWED_MODELS

def pick_model(selected: str | None) -> str:
    if not selected:
        return DEFAULT_MODEL
    selected = selected.strip()
    if selected in ALLOWED_MODELS:
        return selected
    return DEFAULT_MODEL