"""Tokenisation helpers shared by retrieval and routing."""
import re

STOP = set("""a an the and or but if then of to in on at for from by with about as is are was were be been being am do does did
doing have has had having i me my we our you your he she it its they them their this that these those there here what which
who whom when where why how can could should would will shall may might must not no yes so than too very just also into
out up down over under again further once any all both each few more most other some such only own same s t get got need
want please tell know like help us let""".split())

_word = re.compile(r"[a-z0-9]+")


def stem(w: str) -> str:
    for suf in ("ations", "ation", "ingly", "ings", "ing", "edly", "ed", "ies", "es", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def tokens(text: str, keep_stop=False):
    out = []
    for w in _word.findall(text.lower()):
        if not keep_stop and w in STOP:
            continue
        out.append(stem(w))
    return out
