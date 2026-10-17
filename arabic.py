# -*- coding: utf-8 -*-
"""Arabic text helpers: reshaping + bidi, fonts, and ArabicInput."""
import os

import arabic_reshaper
from kivy.core.text import LabelBase
from kivymd.uix.textfield import MDTextField

try:  # python-bidi 0.4.x / 0.5+
    from bidi.algorithm import get_display
except Exception:  # pragma: no cover
    try:
        from bidi import get_display
    except Exception:
        get_display = None


def ar(text):
    """Reshape Arabic text and apply bidi so it shows correctly in Kivy."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    shaped = arabic_reshaper.reshape(text)
    if get_display is not None:
        try:
            return get_display(shaped)
        except Exception:
            return shaped
    return shaped


def register_fonts():
    """Make every KivyMD font style use the Arabic font (font.ttf)."""
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "font.ttf")
    if not os.path.exists(path):
        return False
    for name in ("Roboto", "RobotoMedium", "RobotoBold", "RobotoLight",
                 "RobotoThin", "RobotoBlack"):
        LabelBase.register(name=name, fn_regular=path, fn_bold=path,
                           fn_italic=path, fn_bolditalic=path)
    return True


class ArabicInput(MDTextField):
    """Text field that keeps the raw (logical) Arabic text in `raw`
    and shows the reshaped/bidi version on screen."""

    def __init__(self, **kwargs):
        initial = kwargs.pop("text", "")
        super().__init__(**kwargs)
        self.halign = "right"
        self.raw = initial or ""
        self._show()

    def _show(self):
        self.text = ar(self.raw)
        self.cursor = (len(self.text), 0)

    def insert_text(self, substring, from_undo=False):
        if substring in ("\n", "\r"):
            return
        self.raw += substring
        self._show()

    def do_backspace(self, from_undo=False, mode="bkspc"):
        if self.raw:
            self.raw = self.raw[:-1]
            self._show()

    def set_raw(self, value):
        self.raw = value or ""
        self._show()

    def get_raw(self):
        return self.raw.strip()
