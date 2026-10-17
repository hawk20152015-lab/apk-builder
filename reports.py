# -*- coding: utf-8 -*-
"""
الصندوق — توليد كشوف الحساب والتقارير (PDF) وملفات إكسل.
PDF يُرسم بـ Pillow مع تشكيل الحروف العربية (يعمل على أندرويد دون مكتبات نظام).
تطوير عمر كريم
"""
import os
from datetime import datetime

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from core import KIND_LABEL, DEV_MARK

HERE = os.path.dirname(os.path.abspath(__file__))
F_REG = os.path.join(HERE, 'ArFont-Regular.ttf')
F_BOLD = os.path.join(HERE, 'ArFont-Bold.ttf')

# A4 بدقة 150 نقطة/إنش
W, H, M = 1240, 1754, 70
NAVY, NAVY2 = (11, 37, 69), (29, 78, 137)
INK, MUTED, LINE, ZEBRA = (15, 23, 42), (100, 116, 139), (226, 232, 240), (248, 250, 252)
KIND_COLOR = {'add': (13, 148, 136), 'nathriya': (225, 29, 72), 'spend': (217, 119, 6),
              'withdraw': (124, 58, 237)}
GOLD = (212, 160, 23)

_fonts = {}
# Pillow على أندرويد 8.4 (LAYOUT_BASIC) — والإصدارات الأحدث (Layout.BASIC)
_BASIC = getattr(getattr(ImageFont, 'Layout', None), 'BASIC', None)
if _BASIC is None:
    _BASIC = ImageFont.LAYOUT_BASIC


def font(size, bold=False):
    k = (size, bold)
    if k not in _fonts:
        # BASIC دائماً: النص يُشكَّل ويُرتَّب مسبقاً بـ arabic_reshaper + bidi،
        # و raqm (إن وُجد على الحاسبة) سيعكسه مرة ثانية
        _fonts[k] = ImageFont.truetype(F_BOLD if bold else F_REG, size, layout_engine=_BASIC)
    return _fonts[k]


def vis(text):
    """تحويل النص العربي للشكل المرئي (حروف متصلة + اتجاه صحيح)."""
    return get_display(arabic_reshaper.reshape(str(text if text is not None else '')))


def money(x):
    try:
        x = float(x or 0)
    except (TypeError, ValueError):
        return str(x)
    s = '{:,.0f}'.format(abs(x))
    return ('-' if x < 0 else '') + s


def fit(text, f, width):
    """قص النص ليتسع للعرض."""
    t = str(text or '')
    if f.getlength(vis(t)) <= width:
        return vis(t)
    while t and f.getlength(vis(t + '…')) > width:
        t = t[:-1]
    return vis(t + '…')


class PdfDoc:
    def __init__(self, title, subtitle=''):
        self.title, self.subtitle = title, subtitle
        self.pages = []
        self._new_page()

    # ---------------------------------------------------------------- صفحات
    def _new_page(self):
        self.img = Image.new('RGB', (W, H), 'white')
        self.d = ImageDraw.Draw(self.img)
        self.pages.append(self.img)
        if len(self.pages) == 1:
            self._header()
        else:
            self.d.rectangle([0, 0, W, 90], fill=NAVY)
            self.text_r(W - M, 26, self.title, font(30, True), (255, 255, 255))
            self.y = 130

    def _header(self):
        d = self.d
        # شريط علوي متدرج
        for i in range(230):
            t = i / 229
            c = tuple(int(NAVY[k] + (NAVY2[k] - NAVY[k]) * t) for k in range(3))
            d.line([(0, i), (W, i)], fill=c)
        d.rectangle([0, 226, W, 232], fill=GOLD)
        self.text_r(W - M, 52, 'الصندوق', font(30, True), (191, 219, 254))
        self.text_r(W - M, 96, self.title, font(50, True), (255, 255, 255))
        if self.subtitle:
            self.text_r(W - M, 168, self.subtitle, font(26), (203, 213, 225))
        stamp = datetime.now().strftime('%Y-%m-%d  %H:%M')
        d.text((M, 60), stamp, font=font(24), fill=(203, 213, 225))
        d.text((M, 100), vis('تاريخ الإصدار'), font=font(22), fill=(148, 163, 184))
        self.y = 270

    def ensure(self, h):
        if self.y + h > H - 110:
            self._new_page()

    # ---------------------------------------------------------------- أدوات رسم
    def text_r(self, x_right, y, text, f, fill, width=None):
        v = fit(text, f, width) if width else vis(text)
        self.d.text((x_right - f.getlength(v), y), v, font=f, fill=fill)

    def text_c(self, x_center, y, text, f, fill, width=None):
        v = fit(text, f, width) if width else vis(text)
        self.d.text((x_center - f.getlength(v) / 2, y), v, font=f, fill=fill)

    def section(self, title):
        self.ensure(80)
        self.d.rectangle([W - M - 8, self.y + 6, W - M, self.y + 42], fill=GOLD)
        self.text_r(W - M - 22, self.y, title, font(32, True), INK)
        self.y += 66

    def info_rows(self, pairs):
        """أزواج (عنوان، قيمة) في عمودين."""
        f_l, f_v = font(24), font(28, True)
        col_w = (W - 2 * M) / 2
        for i in range(0, len(pairs), 2):
            self.ensure(84)
            for j, (k, v) in enumerate(pairs[i:i + 2]):
                xr = W - M - j * col_w
                self.text_r(xr, self.y, k, f_l, MUTED)
                self.text_r(xr, self.y + 32, v or '—', f_v, INK, width=col_w - 30)
            self.y += 84
        self.y += 10

    def stat_boxes(self, items):
        """بطاقات أرقام: [(العنوان، القيمة، اللون)]"""
        self.ensure(150)
        n = len(items)
        gap = 18
        bw = (W - 2 * M - gap * (n - 1)) / n
        for i, (label, value, color) in enumerate(items):
            xr = W - M - i * (bw + gap)
            x0 = xr - bw
            self.d.rounded_rectangle([x0, self.y, xr, self.y + 128], 18, fill=ZEBRA, outline=LINE, width=2)
            self.d.rounded_rectangle([x0, self.y, xr, self.y + 10], 5, fill=color)
            self.text_c(x0 + bw / 2, self.y + 28, money(value), font(38, True), color)
            self.text_c(x0 + bw / 2, self.y + 84, label, font(22, True), MUTED, width=bw - 16)
        self.y += 160

    def table(self, cols, rows, colors=None, total=None):
        """cols: [(العنوان، النسبة، المحاذاة 'r'|'c')] من اليمين لليسار.
           rows: قوائم نصية. colors: لون لكل صف (يُطبَّق على عمود المبلغ إن وُجد)."""
        width = W - 2 * M
        ws = [c[1] * width for c in cols]
        f_h, f_r = font(23, True), font(23)
        rh = 54

        def head():
            self.ensure(rh * 2)
            self.d.rounded_rectangle([M, self.y, W - M, self.y + rh], 10, fill=NAVY)
            xr = W - M
            for (title, _, al), w in zip(cols, ws):
                if al == 'c':
                    self.text_c(xr - w / 2, self.y + 12, title, f_h, (255, 255, 255), w - 12)
                else:
                    self.text_r(xr - 14, self.y + 12, title, f_h, (255, 255, 255), w - 20)
                xr -= w
            self.y += rh

        head()
        for n, row in enumerate(rows):
            if self.y + rh > H - 110:
                self._new_page()
                head()
            if n % 2:
                self.d.rectangle([M, self.y, W - M, self.y + rh], fill=ZEBRA)
            xr = W - M
            rc = colors[n] if colors else None
            for ci, ((title, _, al), w) in enumerate(zip(cols, ws)):
                val = row[ci]
                fill = INK
                f = f_r
                if isinstance(val, tuple):          # (نص، لون)
                    val, fill = val
                    f = font(23, True)
                if al == 'c':
                    self.text_c(xr - w / 2, self.y + 13, val, f, fill, w - 12)
                else:
                    self.text_r(xr - 14, self.y + 13, val, f, fill, w - 20)
                xr -= w
            self.d.line([(M, self.y + rh), (W - M, self.y + rh)], fill=LINE, width=1)
            self.y += rh
        if total:
            self.ensure(rh + 10)
            self.d.rounded_rectangle([M, self.y + 6, W - M, self.y + 6 + rh], 10, fill=(241, 245, 249),
                                     outline=NAVY, width=2)
            xr = W - M
            for ci, ((title, _, al), w) in enumerate(zip(cols, ws)):
                val = total[ci] if ci < len(total) else ''
                fill = NAVY
                if isinstance(val, tuple):
                    val, fill = val
                if al == 'c':
                    self.text_c(xr - w / 2, self.y + 19, val, font(23, True), fill, w - 12)
                else:
                    self.text_r(xr - 14, self.y + 19, val, font(23, True), fill, w - 20)
                xr -= w
            self.y += rh + 16
        self.y += 24

    def note(self, text):
        self.ensure(50)
        self.text_r(W - M, self.y, text, font(22), MUTED)
        self.y += 44

    # ---------------------------------------------------------------- حفظ
    def save(self, path):
        total = len(self.pages)
        for i, p in enumerate(self.pages, 1):
            d = ImageDraw.Draw(p)
            d.line([(M, H - 86), (W - M, H - 86)], fill=LINE, width=2)
            v = vis(DEV_MARK + '  ·  جميع الحقوق محفوظة © 2026')
            d.text((W - M - font(21, True).getlength(v), H - 70), v, font=font(21, True), fill=NAVY2)
            d.text((M, H - 70), '%d / %d' % (i, total), font=font(21), fill=MUTED)
        self.pages[0].save(path, 'PDF', resolution=150.0, save_all=True,
                           append_images=self.pages[1:])
        return path


# ====================================================================== كشوف
def member_statement(db, mid, path):
    m = db.member(mid)
    tot = db.member_totals(mid)
    txs = list(reversed(db.transactions(mid)))          # الأقدم أولاً لحساب الرصيد التراكمي
    doc = PdfDoc('كشف حساب', '%s — %s' % (m['name'], m.get('division_name') or ''))
    doc.info_rows([('الاسم', m['name']), ('الشعبة', m.get('division_name') or '—'),
                   ('الهاتف', m.get('phone') or '—'), ('ماستر كارد', m.get('mastercard') or '—')])
    doc.stat_boxes([('الرصيد الحالي', m['balance'], NAVY2),
                    ('مجموع الإضافات', tot['added'], KIND_COLOR['add']),
                    ('خصم للنثرية', tot['nathriya'], KIND_COLOR['nathriya']),
                    ('المصروف', tot['spent'], KIND_COLOR['spend'])])
    doc.section('الحركات (%d)' % len(txs))
    run, rows = 0, []
    for t in txs:
        run += t['amount'] or 0
        k = t.get('kind') or ('add' if (t['amount'] or 0) >= 0 else 'nathriya')
        rows.append([(t['created_at'] or '')[:16], (KIND_LABEL.get(k, k), KIND_COLOR.get(k, INK)),
                     (money(t['amount']), KIND_COLOR.get(k, INK)), money(run), t.get('note') or ''])
    if not rows:
        doc.note('لا توجد حركات مسجّلة')
    else:
        doc.table([('التاريخ', .22, 'c'), ('النوع', .17, 'c'), ('المبلغ', .17, 'c'),
                   ('الرصيد', .17, 'c'), ('ملاحظة', .27, 'r')], rows,
                  total=['الرصيد النهائي', '', '', (money(m['balance']), NAVY2), ''])
    return doc.save(path)


def division_statement(db, did, path):
    d = db.division(did)
    members = db.members(did)
    doc = PdfDoc('كشف شعبة', d['name'])
    doc.stat_boxes([('المبلغ الأصلي', d['base_amount'], NAVY2),
                    ('النثرية', d['nathriya'], KIND_COLOR['nathriya']),
                    ('التبرع', d['donation'], KIND_COLOR['spend']),
                    ('الصافي', d['net'], KIND_COLOR['add'])])
    doc.note('الصافي = المبلغ الأصلي − النثرية − التبرع   ·   عدد الأفراد: %d' % len(members))
    doc.section('الأفراد وأرصدتهم')
    rows = []
    for i, m in enumerate(members, 1):
        rows.append([str(i), m['name'], m.get('phone') or '—', m.get('mastercard') or '—',
                     (money(m['balance']), NAVY2 if (m['balance'] or 0) >= 0 else KIND_COLOR['nathriya'])])
    if rows:
        doc.table([('ت', .07, 'c'), ('الاسم', .35, 'r'), ('الهاتف', .19, 'c'),
                   ('ماستر كارد', .21, 'c'), ('الرصيد', .18, 'c')], rows,
                  total=['', 'المجموع', '', '', (money(d['total']), NAVY2)])
    else:
        doc.note('لا يوجد أفراد في هذه الشعبة')
    return doc.save(path)


def period_report_pdf(db, date_from, date_to, path):
    rows, tot = db.period_report(date_from, date_to)
    doc = PdfDoc('تقرير الصندوق', 'من %s إلى %s' % (date_from, date_to))
    ov = db.overview()
    doc.stat_boxes([('الإضافات', tot['added'], KIND_COLOR['add']),
                    ('خصم للنثرية', tot['nathriya'], KIND_COLOR['nathriya']),
                    ('المصروف', tot['spent'], KIND_COLOR['spend']),
                    ('سحب من النثرية', tot['withdrawn'], KIND_COLOR['withdraw'])])
    doc.info_rows([('إجمالي أرصدة الأفراد الآن', money(ov['balance'])),
                   ('النثرية المتاحة الآن', money(ov['nathriya'])),
                   ('عدد الشعب', str(ov['divisions'])), ('عدد الأفراد', str(ov['members']))])
    doc.section('حسب الشعبة')
    data = [[r['name'], (money(r['added']), KIND_COLOR['add']), (money(r['nathriya']), KIND_COLOR['nathriya']),
             (money(r['spent']), KIND_COLOR['spend']), str(r['n'])] for r in rows]
    doc.table([('الشعبة', .32, 'r'), ('الإضافات', .18, 'c'), ('النثرية', .18, 'c'),
               ('المصروف', .18, 'c'), ('الحركات', .14, 'c')], data,
              total=['المجموع', money(tot['added']), money(tot['nathriya']), money(tot['spent']), str(tot['n'])])
    return doc.save(path)


# ====================================================================== إكسل
def _xl_style(ws, widths):
    from openpyxl.styles import Font, PatternFill, Alignment
    try:
        ws.sheet_view.rightToLeft = True
    except Exception:
        pass
    fill = PatternFill('solid', fgColor='0B2545')
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = fill
        c.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 24
    for i, w in enumerate(widths):
        ws.column_dimensions[chr(65 + i)].width = w
    ws.freeze_panes = 'A2'


def _sheet_title(name, used):
    t = ''.join(ch for ch in name if ch not in '[]:*?/\\')[:28] or 'شعبة'
    base, n = t, 2
    while t in used:
        t = '%s %d' % (base[:25], n)
        n += 1
    used.add(t)
    return t


def export_division_xlsx(db, did, path):
    import openpyxl
    d = db.division(did)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _sheet_title(d['name'], set())
    ws.append(['الاسم', 'الهاتف', 'ماستر كارد', 'الرصيد', 'ملاحظات'])
    for m in db.members(did):
        ws.append([m['name'], m.get('phone') or '', m.get('mastercard') or '', m['balance'] or 0,
                   m.get('notes') or ''])
    _xl_style(ws, (28, 16, 22, 14, 24))
    wb.save(path)
    return path


def export_all_xlsx(db, path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'ملخص الشعب'
    ws.append(['الشعبة', 'الأفراد', 'المبلغ الأصلي', 'النثرية', 'التبرع', 'الصافي', 'مجموع الأرصدة',
               'المصروف'])
    for d in db.divisions():
        ws.append([d['name'], d['cnt'], d['base_amount'], d['nathriya'], d['donation'], d['net'],
                   d['total'], d['spent']])
    _xl_style(ws, (26, 10, 16, 14, 14, 16, 16, 14))
    allm = wb.create_sheet('كل الأفراد')
    allm.append(['الاسم', 'الهاتف', 'الشعبة', 'ماستر كارد', 'الرصيد', 'ملاحظات'])
    used = {'ملخص الشعب', 'كل الأفراد', 'سجل الحركات'}
    for d in db.divisions():
        for m in db.members(d['id']):
            allm.append([m['name'], m.get('phone') or '', d['name'], m.get('mastercard') or '',
                         m['balance'] or 0, m.get('notes') or ''])
    _xl_style(allm, (28, 16, 22, 22, 14, 24))
    lg = wb.create_sheet('سجل الحركات')
    lg.append(['التاريخ', 'النوع', 'الاسم', 'الشعبة', 'المبلغ', 'ملاحظة'])
    for r in db.ledger(limit=100000):
        lg.append([r['created_at'], KIND_LABEL.get(r['kind'], 'سحب من النثرية'), r['member_name'],
                   r.get('division_name') or '', r['amount'], r.get('note') or ''])
    _xl_style(lg, (18, 16, 26, 22, 14, 28))
    wb.save(path)
    return path


def template_xlsx(path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'الأفراد'
    ws.append(['الاسم', 'الهاتف', 'الشعبة', 'ماستر كارد', 'الرصيد'])
    ws.append(['علي حسن', '07701234567', 'الشعبة الأولى', '', 0])
    ws.append(['حسن جاسم', '', 'الشعبة الثانية', '', 25000])
    _xl_style(ws, (28, 16, 22, 22, 14))
    wb.save(path)
    return path


def _cell(v):
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _num(v):
    try:
        return float(str(v).replace(',', '').strip() or 0)
    except (TypeError, ValueError):
        return 0.0


HEADER_WORDS = {'الاسم': 'name', 'اسم': 'name', 'اسم الفرد': 'name', 'الاسم الكامل': 'name', 'name': 'name',
                'الهاتف': 'phone', 'رقم الهاتف': 'phone', 'phone': 'phone', 'الموبايل': 'phone',
                'الشعبة': 'division', 'شعبة': 'division', 'division': 'division',
                'ماستر كارد': 'mastercard', 'الماستر كارد': 'mastercard', 'ماستر': 'mastercard',
                'mastercard': 'mastercard', 'الرصيد': 'balance', 'balance': 'balance',
                'ملاحظات': 'notes', 'notes': 'notes'}


def import_xlsx(db, path, division_id=None):
    """يستورد الأفراد. يتعرّف على الأعمدة من سطر العناوين إن وُجد،
    وإلا يعتمد الترتيب: الاسم | الهاتف | الشعبة | ماستر كارد | الرصيد.
    الرصيد (إن وُجد) يُسجَّل كحركة «رصيد افتتاحي». يعيد (المضاف، المتخطّى)."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    added = skipped = 0
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            header = [HEADER_WORDS.get(_cell(c).lower(), HEADER_WORDS.get(_cell(c))) for c in rows[0]]
            if 'name' in header:
                cols = {k: header.index(k) for k in set(header) if k}
                data = rows[1:]
            else:
                cols = {'name': 0, 'phone': 1, 'division': 2, 'mastercard': 3, 'balance': 4}
                if division_id:      # داخل شعبة: الاسم | الهاتف | ماستر كارد
                    cols = {'name': 0, 'phone': 1, 'mastercard': 2, 'balance': 3}
                data = rows
            # ملفات التصدير السابقة (ملخص الشعب / السجل) ليست قوائم أفراد
            if ws.title in ('ملخص الشعب', 'سجل الحركات'):
                continue
            for row in data:
                if not row:
                    continue
                get = lambda k: _cell(row[cols[k]]) if k in cols and cols[k] < len(row) else ''
                name = get('name')
                if not name:
                    continue
                did = division_id
                if not did:
                    dname = get('division') or (ws.title if ws.title not in ('Sheet', 'الأفراد', 'كل الأفراد')
                                                else '') or 'غير مصنّف'
                    did = db.division_id_by_name(dname)
                if not did:
                    skipped += 1
                    continue
                mid = db.add_member(name, did, get('phone'), get('mastercard'), get('notes'))
                bal = _num(get('balance')) if 'balance' in cols else 0
                if bal:
                    db.add_transaction(mid, 'add' if bal > 0 else 'spend', abs(bal), 'رصيد افتتاحي')
                    db.conn.commit()
                added += 1
    finally:
        try:
            wb.close()
        except Exception:
            pass
    return added, skipped
