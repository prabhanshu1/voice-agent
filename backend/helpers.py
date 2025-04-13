import re

def _strip_nones(data: dict[str, any]) -> dict[str, any]:
    return {k: v for k, v in data.items() if v is not None}


def remove_special_characters(text):
    # Keep alphanumeric, whitespace, apostrophes, and allowed punctuation
    cleaned_text = re.sub(r"[^a-zA-Z0-9\s\?\.\,\!']", "", text)
    return cleaned_text