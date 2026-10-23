import re

_QUOTES = str.maketrans("", "", "\"'״׳")
_SEPS = str.maketrans(dict.fromkeys("*/-_.,", " "))
_CODE = re.compile(r"^[a-z0-9]{6,}$")


def _is_ref(tok: str) -> bool:
    digits = sum(c.isdigit() for c in tok)
    return digits >= 3 or (bool(_CODE.match(tok)) and digits > 0 and not tok.isdigit())


def normalize_merchant(description: str) -> str:
    toks = description.lower().translate(_QUOTES).translate(_SEPS).split()
    # Fall back to unfiltered tokens so an all-reference description doesn't collapse to "".
    return " ".join(t for t in toks if not _is_ref(t)) or " ".join(toks)
