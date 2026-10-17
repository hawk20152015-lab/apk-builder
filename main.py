# -*- coding: utf-8 -*-
"""ميزانيتي - تطبيق الميزانية الشخصية: الدخل، المصاريف، القروض، التقارير.
تصميم وبرمجة: عمر كريم
"""
import os
from datetime import date, datetime

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.toast import toast
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import (MDFlatButton, MDFloatingActionButton,
                               MDIconButton, MDRaisedButton)
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

from arabic import ArabicInput, ar, register_fonts
from charts import INCOME_COLOR, OUT_COLOR, BarChart
from database import BudgetDB, month_key, shift_month

MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز",
          "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]
INCOME_SOURCES = ["راتب", "أرباح الكابينات", "تداول", "عمل إضافي", "هدية", "أخرى"]
EXPENSE_CATS = ["بيت", "طعام", "سيارة ووقود", "فواتير", "إنترنت وموبايل",
                "صحة", "تعليم", "ملابس", "عائلة", "مناسبات", "ترفيه", "أخرى"]

GREEN = INCOME_COLOR
RED = OUT_COLOR
BLUE = (0.20, 0.45, 0.80, 1)
GREY = (0.45, 0.45, 0.45, 1)


def money(v):
    return ar("%s د.ع" % "{:,.0f}".format(v))


def lbl(text, style="Body1", color=None, halign="right", bold=False, **kw):
    l = MDLabel(text=ar(text), font_style=style, halign=halign, bold=bold, **kw)
    if color:
        l.theme_text_color = "Custom"
        l.text_color = color
    return l


def valid_date(s):
    try:
        datetime.strptime(s.strip(), "%Y-%m-%d")
        return True
    except Exception:
        return False


def parse_amount(s):
    try:
        v = float(str(s).replace(",", "").strip())
        return v if v > 0 else None
    except Exception:
        return None


class ChoiceGrid(MDGridLayout):
    """Grid of buttons acting as a single-choice selector."""

    def __init__(self, choices, selected=None, **kw):
        super().__init__(cols=3, spacing=dp(6), size_hint_y=None, **kw)
        self.value = selected or choices[0]
        self.buttons = {}
        rows = (len(choices) + 2) // 3
        self.height = rows * dp(42) + (rows - 1) * dp(6)
        # RTL: fill each row from the right
        ordered = []
        for r in range(rows):
            chunk = choices[r * 3:(r + 1) * 3]
            chunk = chunk + [None] * (3 - len(chunk))
            ordered.extend(reversed(chunk))
        for c in ordered:
            if c is None:
                self.add_widget(Widget())
                continue
            b = MDRaisedButton(text=ar(c), size_hint=(1, None), height=dp(40),
                               elevation=0)
            b.bind(on_release=lambda btn, c=c: self.select(c))
            self.buttons[c] = b
            self.add_widget(b)
        self.select(self.value)

    def select(self, c):
        self.value = c
        app = MDApp.get_running_app()
        for name, b in self.buttons.items():
            if name == c:
                b.md_bg_color = app.theme_cls.primary_color
                b.theme_text_color = "Custom"
                b.text_color = (1, 1, 1, 1)
            else:
                b.md_bg_color = (0.92, 0.92, 0.92, 1)
                b.theme_text_color = "Custom"
                b.text_color = (0.2, 0.2, 0.2, 1)


class BudgetApp(MDApp):
    title = "ميزانيتي"

    # ------------------------------------------------------------------ build
    def build(self):
        register_fonts()
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"
        self.db = BudgetDB(os.path.join(self.user_data_dir, "budget.db"))
        today = date.today()
        self.year, self.month = today.year, today.month
        self.dialog = None

        root = MDBoxLayout(orientation="vertical")
        bar = MDTopAppBar(title=ar("ميزانيتي"), anchor_title="right", elevation=2)
        root.add_widget(bar)

        mbar = MDBoxLayout(size_hint_y=None, height=dp(48), padding=(dp(8), 0))
        mbar.add_widget(MDIconButton(icon="chevron-left",
                                     on_release=lambda *_: self.change_month(1)))
        self.month_label = lbl("", "H6", halign="center")
        mbar.add_widget(self.month_label)
        mbar.add_widget(MDIconButton(icon="chevron-right",
                                     on_release=lambda *_: self.change_month(-1)))
        root.add_widget(mbar)

        self.nav = MDBottomNavigation(panel_color=(1, 1, 1, 1),
                                      selected_color_background=(0, 0, 0, 0))
        self.boxes = {}
        tabs = [("reports", "التقارير", "chart-bar", False),
                ("loans", "القروض", "bank", True),
                ("expenses", "المصاريف", "cart", True),
                ("income", "الدخل", "cash-plus", True),
                ("home", "الرئيسية", "home", False)]
        for name, title, icon, fab in tabs:
            item = MDBottomNavigationItem(name=name, text=ar(title), icon=icon)
            item.add_widget(self._tab_body(name, fab))
            self.nav.add_widget(item)
        root.add_widget(self.nav)
        Clock.schedule_once(lambda *_: self._start(), 0)
        return root

    def _start(self):
        try:
            self.nav.switch_tab("home")
        except Exception:
            pass
        self.refresh()

    def _tab_body(self, name, fab):
        holder = MDFloatLayout()
        scroll = MDScrollView(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        box = MDBoxLayout(orientation="vertical", adaptive_height=True,
                          padding=(dp(12), dp(8), dp(12), dp(90)), spacing=dp(8))
        scroll.add_widget(box)
        holder.add_widget(scroll)
        self.boxes[name] = box
        if fab:
            actions = {"income": self.dlg_income, "expenses": self.dlg_expense,
                       "loans": self.dlg_loan}
            holder.add_widget(MDFloatingActionButton(
                icon="plus", pos_hint={"x": 0.04, "y": 0.03},
                on_release=lambda *_: actions[name]()))
        return holder

    # ---------------------------------------------------------------- helpers
    @property
    def mk(self):
        return month_key(self.year, self.month)

    def default_date(self):
        t = date.today()
        if (t.year, t.month) == (self.year, self.month):
            return t.isoformat()
        return "%s-01" % self.mk

    def change_month(self, delta):
        self.year, self.month = shift_month(self.year, self.month, delta)
        self.refresh()

    def refresh(self, *_):
        self.month_label.text = ar("%s %d" % (MONTHS[self.month - 1], self.year))
        self.build_home()
        self.build_income()
        self.build_expenses()
        self.build_loans()
        self.build_reports()

    def card(self, height, orientation="vertical", **kw):
        return MDCard(orientation=orientation, size_hint_y=None, height=height,
                      padding=dp(10), spacing=dp(4), radius=[dp(12)],
                      elevation=1, **kw)

    def row(self, title, subtitle, amount, color, on_delete):
        c = self.card(dp(66), orientation="horizontal")
        c.add_widget(MDIconButton(icon="trash-can-outline", theme_icon_color="Custom",
                                  icon_color=GREY, on_release=lambda *_: on_delete()))
        c.add_widget(MDLabel(text=money(amount), halign="left", bold=True,
                             theme_text_color="Custom", text_color=color,
                             size_hint_x=0.45))
        texts = MDBoxLayout(orientation="vertical")
        texts.add_widget(lbl(title, "Subtitle1", bold=True))
        texts.add_widget(lbl(subtitle, "Caption", GREY))
        c.add_widget(texts)
        return c

    def empty(self, box, text):
        box.add_widget(lbl(text, "Body2", GREY, halign="center",
                           size_hint_y=None, height=dp(60)))

    def header(self, box, text, total=None, color=None):
        h = MDBoxLayout(size_hint_y=None, height=dp(36))
        h.add_widget(MDLabel(text=money(total) if total is not None else "",
                             halign="left", bold=True, theme_text_color="Custom",
                             text_color=color or GREY))
        h.add_widget(lbl(text, "H6"))
        box.add_widget(h)

    def show(self, title, content, ok_text, on_ok, height):
        self.close()
        content.size_hint_y = None
        content.height = height
        self.dialog = MDDialog(
            title=ar(title), type="custom", content_cls=content,
            buttons=[MDFlatButton(text=ar("إلغاء"), on_release=self.close),
                     MDRaisedButton(text=ar(ok_text), on_release=lambda *_: on_ok())])
        self.dialog.open()

    def close(self, *_):
        if self.dialog:
            self.dialog.dismiss()
            self.dialog = None

    def confirm(self, text, on_yes):
        def yes():
            self.close()
            on_yes()
            self.refresh()
        box = MDBoxLayout(orientation="vertical")
        box.add_widget(lbl(text))
        self.show("تأكيد الحذف", box, "حذف", yes, dp(60))

    @staticmethod
    def num_field(hint, text=""):
        return MDTextField(hint_text=ar(hint), text=text, input_filter="float",
                           input_type="number", halign="right")

    @staticmethod
    def date_field(text):
        return MDTextField(hint_text=ar("التاريخ (سنة-شهر-يوم)"), text=text,
                           halign="right")

    # ------------------------------------------------------------------- home
    def build_home(self):
        box = self.boxes["home"]
        box.clear_widgets()
        t = self.db.totals(self.mk)
        grid = MDGridLayout(cols=2, spacing=dp(8), size_hint_y=None,
                            height=dp(2 * 86 + 8))
        items = [("المصاريف", t["expenses"], RED), ("الدخل", t["income"], GREEN),
                 ("المتبقي (الصافي)", t["net"], GREEN if t["net"] >= 0 else RED),
                 ("الأقساط المسددة", t["installments"], BLUE)]
        for title, val, col in items:
            c = self.card(dp(86))
            c.add_widget(lbl(title, "Body2", GREY))
            c.add_widget(MDLabel(text=money(val), halign="right", font_style="H6",
                                 bold=True, theme_text_color="Custom", text_color=col))
            grid.add_widget(c)
        box.add_widget(grid)

        if t["income"] > 0:
            spent = t["expenses"] + t["installments"]
            pct = min(spent / t["income"] * 100, 100)
            c = self.card(dp(74))
            c.add_widget(lbl("صُرف %d%% من الدخل" % round(spent / t["income"] * 100),
                             "Body2"))
            pb = MDProgressBar(value=pct, size_hint_y=None, height=dp(8))
            if pct >= 90:
                pb.color = RED
            c.add_widget(pb)
            box.add_widget(c)

        due = self.db.due_loans(self.mk)
        self.header(box, "أقساط غير مسددة هذا الشهر",
                    sum(min(l["installment"], l["remaining"]) for l in due), RED)
        if not due:
            self.empty(box, "لا توجد أقساط مستحقة غير مسددة")
        for l in due:
            c = self.card(dp(62), orientation="horizontal")
            c.add_widget(MDRaisedButton(text=ar("تسديد"), pos_hint={"center_y": .5},
                                        on_release=lambda *_, l=l: self.dlg_pay(l)))
            c.add_widget(MDLabel(text=money(min(l["installment"], l["remaining"])),
                                 halign="left", theme_text_color="Custom",
                                 text_color=RED, bold=True))
            c.add_widget(lbl(l["name"], "Subtitle1", bold=True))
            box.add_widget(c)

    # ----------------------------------------------------------------- income
    def build_income(self):
        box = self.boxes["income"]
        box.clear_widgets()
        rows = self.db.list_income(self.mk)
        self.header(box, "دخل الشهر", sum(r["amount"] for r in rows), GREEN)
        if not rows:
            self.empty(box, "لا يوجد دخل مسجل لهذا الشهر — اضغط + للإضافة")
        for r in rows:
            sub = r["date"] + ("  •  " + r["note"] if r["note"] else "")
            box.add_widget(self.row(r["source"], sub, r["amount"], GREEN,
                                    lambda r=r: self.confirm(
                                        "حذف هذا الدخل؟",
                                        lambda: self.db.delete_income(r["id"]))))

    def dlg_income(self):
        content = MDBoxLayout(orientation="vertical", spacing=dp(6))
        content.add_widget(lbl("المصدر", "Caption", GREY, size_hint_y=None,
                               height=dp(20)))
        grid = ChoiceGrid(INCOME_SOURCES)
        content.add_widget(grid)
        amount = self.num_field("المبلغ")
        d = self.date_field(self.default_date())
        note = ArabicInput(hint_text=ar("ملاحظة (اختياري)"))
        for w in (amount, d, note):
            content.add_widget(w)

        def save():
            v = parse_amount(amount.text)
            if v is None:
                toast(ar("أدخل مبلغاً صحيحاً"))
                return
            if not valid_date(d.text):
                toast(ar("صيغة التاريخ: 2026-10-17"))
                return
            self.db.add_income(grid.value, v, d.text.strip(), note.get_raw())
            self.close()
            self.refresh()
            toast(ar("تم حفظ الدخل"))
        self.show("إضافة دخل", content, "حفظ", save, grid.height + dp(230))

    # --------------------------------------------------------------- expenses
    def build_expenses(self):
        box = self.boxes["expenses"]
        box.clear_widgets()
        rows = self.db.list_expenses(self.mk)
        self.header(box, "مصاريف الشهر", sum(r["amount"] for r in rows), RED)
        if not rows:
            self.empty(box, "لا توجد مصاريف لهذا الشهر — اضغط + للإضافة")
        for r in rows:
            sub = r["date"] + ("  •  " + r["note"] if r["note"] else "")
            box.add_widget(self.row(r["category"], sub, r["amount"], RED,
                                    lambda r=r: self.confirm(
                                        "حذف هذا المصروف؟",
                                        lambda: self.db.delete_expense(r["id"]))))

    def dlg_expense(self):
        content = MDBoxLayout(orientation="vertical", spacing=dp(6))
        content.add_widget(lbl("الصنف", "Caption", GREY, size_hint_y=None,
                               height=dp(20)))
        grid = ChoiceGrid(EXPENSE_CATS)
        content.add_widget(grid)
        amount = self.num_field("المبلغ")
        d = self.date_field(self.default_date())
        note = ArabicInput(hint_text=ar("ملاحظة (اختياري)"))
        for w in (amount, d, note):
            content.add_widget(w)

        def save():
            v = parse_amount(amount.text)
            if v is None:
                toast(ar("أدخل مبلغاً صحيحاً"))
                return
            if not valid_date(d.text):
                toast(ar("صيغة التاريخ: 2026-10-17"))
                return
            self.db.add_expense(grid.value, v, d.text.strip(), note.get_raw())
            self.close()
            self.refresh()
            toast(ar("تم حفظ المصروف"))
        self.show("إضافة مصروف", content, "حفظ", save, grid.height + dp(230))

    # ------------------------------------------------------------------ loans
    def build_loans(self):
        box = self.boxes["loans"]
        box.clear_widgets()
        loans = self.db.list_loans()
        self.header(box, "إجمالي المتبقي من القروض",
                    sum(l["remaining"] for l in loans), BLUE)
        if not loans:
            self.empty(box, "لا توجد قروض — اضغط + لإضافة قرض")
        for l in loans:
            box.add_widget(self.loan_card(l))

    def loan_card(self, l):
        c = self.card(dp(196))
        top = MDBoxLayout(size_hint_y=None, height=dp(36))
        top.add_widget(MDIconButton(icon="trash-can-outline", theme_icon_color="Custom",
                                    icon_color=GREY, on_release=lambda *_: self.confirm(
                                        "حذف القرض وكل تسديداته؟",
                                        lambda: self.db.delete_loan(l["id"]))))
        top.add_widget(lbl(l["name"], "H6", bold=True))
        c.add_widget(top)
        pct = (l["paid"] / l["total"] * 100) if l["total"] else 0
        c.add_widget(MDProgressBar(value=min(pct, 100), size_hint_y=None, height=dp(8),
                                   color=GREEN if l["closed"] else BLUE))
        c.add_widget(lbl("المدفوع %s من %s (%d%%)" % (
            "{:,.0f}".format(l["paid"]), "{:,.0f}".format(l["total"]), pct), "Body2"))
        if l["closed"]:
            c.add_widget(lbl("مُسدَّد بالكامل", "Subtitle1", GREEN, bold=True))
        else:
            c.add_widget(lbl("المتبقي %s د.ع — باقي %d قسط" % (
                "{:,.0f}".format(l["remaining"]), l["left_count"]), "Body2", RED))
            paid_now = self.db.paid_in_month(l["id"], self.mk) > 0
            c.add_widget(lbl("القسط الشهري %s د.ع — %s" % (
                "{:,.0f}".format(l["installment"]),
                "مسدد لهذا الشهر" if paid_now else "غير مسدد لهذا الشهر"),
                "Caption", GREEN if paid_now else GREY))
        btns = MDBoxLayout(size_hint_y=None, height=dp(40), spacing=dp(8))
        btns.add_widget(MDFlatButton(text=ar("سجل التسديد"),
                                     on_release=lambda *_: self.dlg_history(l)))
        btns.add_widget(Widget())
        if not l["closed"]:
            btns.add_widget(MDRaisedButton(text=ar("تسديد قسط"),
                                           on_release=lambda *_: self.dlg_pay(l)))
        c.add_widget(btns)
        return c

    def dlg_loan(self):
        content = MDBoxLayout(orientation="vertical", spacing=dp(4))
        name = ArabicInput(hint_text=ar("اسم القرض / الجهة"))
        total = self.num_field("المبلغ الكلي")
        inst = self.num_field("القسط الشهري")
        start = self.date_field(self.default_date())
        start.hint_text = ar("تاريخ أول قسط (سنة-شهر-يوم)")
        note = ArabicInput(hint_text=ar("ملاحظة (اختياري)"))
        for w in (name, total, inst, start, note):
            content.add_widget(w)

        def save():
            if not name.get_raw():
                toast(ar("أدخل اسم القرض"))
                return
            t, i = parse_amount(total.text), parse_amount(inst.text)
            if t is None or i is None:
                toast(ar("أدخل المبلغ الكلي والقسط"))
                return
            if not valid_date(start.text):
                toast(ar("صيغة التاريخ: 2026-10-17"))
                return
            self.db.add_loan(name.get_raw(), t, i, start.text.strip(), note.get_raw())
            self.close()
            self.refresh()
            toast(ar("تمت إضافة القرض"))
        self.show("إضافة قرض", content, "حفظ", save, dp(330))

    def dlg_pay(self, l):
        content = MDBoxLayout(orientation="vertical", spacing=dp(4))
        default = min(l["installment"], l["remaining"])
        amount = self.num_field("مبلغ التسديد", "%g" % default)
        d = self.date_field(self.default_date())
        content.add_widget(lbl("المتبقي: %s د.ع" % "{:,.0f}".format(l["remaining"]),
                               "Body2", GREY, size_hint_y=None, height=dp(24)))
        content.add_widget(amount)
        content.add_widget(d)

        def save():
            v = parse_amount(amount.text)
            if v is None:
                toast(ar("أدخل مبلغاً صحيحاً"))
                return
            if not valid_date(d.text):
                toast(ar("صيغة التاريخ: 2026-10-17"))
                return
            self.db.add_payment(l["id"], v, d.text.strip())
            self.close()
            self.refresh()
            toast(ar("تم تسجيل التسديد"))
        self.show("تسديد: " + l["name"], content, "تسديد", save, dp(170))

    def dlg_history(self, l):
        pays = self.db.list_payments(l["id"])
        scroll = MDScrollView()
        box = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(4))
        scroll.add_widget(box)
        if not pays:
            box.add_widget(lbl("لا توجد تسديدات بعد", "Body2", GREY, halign="center",
                               size_hint_y=None, height=dp(40)))
        for p in pays:
            r = MDBoxLayout(size_hint_y=None, height=dp(44))
            r.add_widget(MDIconButton(icon="close", theme_icon_color="Custom",
                                      icon_color=GREY,
                                      on_release=lambda *_, p=p: self.confirm(
                                          "حذف هذا التسديد؟",
                                          lambda: self.db.delete_payment(p["id"]))))
            r.add_widget(MDLabel(text=money(p["amount"]), halign="left", bold=True))
            r.add_widget(MDLabel(text=p["date"], halign="right"))
            box.add_widget(r)
        self.show("سجل تسديد: " + l["name"], scroll, "تم", self.close, dp(300))

    # ---------------------------------------------------------------- reports
    def build_reports(self):
        box = self.boxes["reports"]
        box.clear_widgets()
        box.add_widget(lbl("آخر 6 أشهر", "H6", size_hint_y=None, height=dp(32)))
        legend = MDBoxLayout(size_hint_y=None, height=dp(22))
        legend.add_widget(lbl("الخارج (مصاريف + أقساط)", "Caption", RED,
                              halign="center", bold=True))
        legend.add_widget(lbl("الدخل", "Caption", GREEN, halign="center", bold=True))
        box.add_widget(legend)
        c = self.card(dp(230))
        c.add_widget(BarChart(data=self.db.monthly_series(self.year, self.month, 6)))
        box.add_widget(c)

        cats = self.db.expenses_by_category(self.mk)
        total = sum(r["total"] for r in cats)
        self.header(box, "المصاريف حسب الصنف", total, RED)
        if not cats:
            self.empty(box, "لا توجد مصاريف لهذا الشهر")
        for r in cats:
            pct = r["total"] / total * 100 if total else 0
            cc = self.card(dp(64))
            top = MDBoxLayout()
            top.add_widget(MDLabel(text=money(r["total"]), halign="left", bold=True))
            top.add_widget(lbl("%s  (%d%%)" % (r["category"], round(pct)), "Body1"))
            cc.add_widget(top)
            cc.add_widget(MDProgressBar(value=pct, size_hint_y=None, height=dp(6),
                                        color=RED))
            box.add_widget(cc)

        t = self.db.totals(self.mk)
        loans = self.db.list_loans()
        self.header(box, "ملخص الشهر")
        s = self.card(dp(150))
        for title, v in (("الدخل", t["income"]), ("المصاريف", t["expenses"]),
                         ("الأقساط", t["installments"]), ("الصافي", t["net"]),
                         ("الديون المتبقية", sum(l["remaining"] for l in loans))):
            r = MDBoxLayout()
            r.add_widget(MDLabel(text=money(v), halign="left", bold=True))
            r.add_widget(lbl(title, "Body1"))
            s.add_widget(r)
        box.add_widget(s)
        box.add_widget(lbl("© عمر كريم", "Caption", GREY, halign="center",
                           size_hint_y=None, height=dp(30)))


if __name__ == "__main__":
    BudgetApp().run()
