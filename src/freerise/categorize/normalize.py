import re
from collections.abc import Iterable

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


_HE_PREFIX = frozenset("בהוכלמש")


def find_pattern(pattern: str, key: str, desc: str) -> int | None:
    """Position of a contains-pattern in the merchant key (else the description), starting at a
    word start; a trailing space in the pattern also demands a word end. A Hebrew pattern of 4+
    letters may also follow one attached prefix letter ("לקרן השתלמות"). None if absent."""
    pat = pattern.lower()
    loose = len(pat.strip()) >= 4 and "א" <= pat[0] <= "ת"
    for s in (key, desc):
        s = " " + s + " "
        i = s.find(pat)
        while i > 0:
            if s[i - 1] == " " or (loose and s[i - 1] in _HE_PREFIX and s[i - 2] == " "):
                return i
            i = s.find(pat, i + 1)
    return None


def best_match[T](pairs: Iterable[tuple[str, T]], key: str, desc: str) -> T | None:
    """The value of the matching pattern that starts earliest, then the longest one."""
    found = [
        ((i, -len(p)), v) for p, v in pairs if p and (i := find_pattern(p, key, desc)) is not None
    ]
    return min(found, key=lambda f: f[0])[1] if found else None
