"""Pins the Turkish pack set and the Turkish output labels for the existing Turkish test modules (issue #2).

The default selection is automatic (packs from the chat text, English labels); these suites assert the Turkish
behaviour, so their setUpModule() calls pin() and their tearDownModule() calls unpin().
"""
import os

_KEYS = ("WA2MD_LANG", "WA2MD_PACKS")
_SAVED = []


def pin():
    _SAVED.append({k: os.environ.get(k) for k in _KEYS})
    for k in _KEYS:
        os.environ[k] = "tr"


def unpin():
    for k, v in _SAVED.pop().items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
