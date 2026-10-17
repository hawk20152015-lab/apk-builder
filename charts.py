# -*- coding: utf-8 -*-
"""Simple bar chart drawn with the Kivy canvas (no matplotlib needed)."""
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import ListProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

INCOME_COLOR = (0.18, 0.65, 0.40, 1)
OUT_COLOR = (0.88, 0.30, 0.30, 1)


def short_num(v):
    v = float(v)
    if abs(v) >= 1_000_000:
        return "%.1fM" % (v / 1_000_000)
    if abs(v) >= 1_000:
        return "%dK" % round(v / 1_000)
    return "%d" % round(v)


class BarChart(Widget):
    """data = [(label, income, outgoing), ...]"""
    data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self.redraw, size=self.redraw, data=self.redraw)

    def redraw(self, *args):
        self.canvas.clear()
        self.clear_widgets()
        if not self.data or self.width < 10:
            return
        pad_b, pad_t = dp(28), dp(22)
        x0, y0 = self.x + dp(6), self.y + pad_b
        w, h = self.width - dp(12), self.height - pad_b - pad_t
        top = max([max(d[1], d[2]) for d in self.data] + [1])
        n = len(self.data)
        group_w = w / n
        bar_w = min(group_w * 0.32, dp(26))
        with self.canvas:
            Color(0.6, 0.6, 0.6, 0.5)
            Line(points=[x0, y0, x0 + w, y0], width=1)
            for i, (lbl, inc, out) in enumerate(self.data):
                cx = x0 + group_w * i + group_w / 2
                for j, (val, col) in enumerate(((inc, INCOME_COLOR), (out, OUT_COLOR))):
                    bh = h * (val / top)
                    bx = cx - bar_w - dp(1) if j == 0 else cx + dp(1)
                    Color(*col)
                    Rectangle(pos=(bx, y0), size=(bar_w, bh))
        for i, (lbl, inc, out) in enumerate(self.data):
            cx = x0 + group_w * i + group_w / 2
            self._label(lbl, cx, self.y + dp(4), sp(11))
            for j, val in enumerate((inc, out)):
                if val <= 0:
                    continue
                bx = cx - bar_w / 2 - dp(1) if j == 0 else cx + bar_w / 2 + dp(1)
                self._label(short_num(val), bx, y0 + h * (val / top) + dp(1), sp(9))

    def _label(self, text, cx, y, size):
        lab = Label(text=text, font_size=size, color=(0.4, 0.4, 0.4, 1),
                    size_hint=(None, None), size=(dp(48), dp(18)))
        lab.pos = (cx - lab.width / 2, y)
        self.add_widget(lab)
