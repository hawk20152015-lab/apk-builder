# -*- coding: utf-8 -*-
"""
أرشيف الكتب — تطبيق موبايل لخزن صور الكتب الرسمية مصنفة حسب الدوائر
Python + Kivy 2.3.0 + KivyMD 1.2.0 + SQLite
"""
import os
import sqlite3
import threading
import uuid
from datetime import datetime

from kivy.utils import platform
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import (StringProperty, NumericProperty, BooleanProperty,
                             ListProperty, ObjectProperty)
from kivy.graphics.texture import Texture
from kivy.utils import get_color_from_hex as hx
from kivy.graphics.transformation import Matrix
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image
from kivy.uix.scatter import Scatter
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.behaviors import ButtonBehavior

from kivymd.app import MDApp
from kivymd.uix.card import MDCard
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFlatButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.toast import toast

import arabic_reshaper
try:
    from bidi.algorithm import get_display
except Exception:          # على الحاسبة بدون python-bidi: reshape فقط
    get_display = None

if platform == 'android':
    from androidstorage4kivy import SharedStorage, Chooser

# ---------------------------------------------------------------- الخط العربي
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_R = os.path.join(HERE, 'ArFont-Regular.ttf')
FONT_B = os.path.join(HERE, 'ArFont-Bold.ttf')
if os.path.exists(FONT_R):
    # استبدال خطوط KivyMD و Kivy الافتراضية بالخط العربي
    for _n in ('Roboto', 'RobotoThin', 'RobotoLight', 'RobotoMedium', 'RobotoBlack'):
        _reg = FONT_B if _n in ('RobotoMedium', 'RobotoBlack') else FONT_R
        LabelBase.register(name=_n, fn_regular=_reg, fn_bold=FONT_B)


def ar(text):
    """تجهيز النص العربي للعرض (سطر واحد)."""
    if not text:
        return ''
    t = arabic_reshaper.reshape(str(text))
    if get_display:
        t = get_display(t)
    return t


def show_toast(msg):
    # التوست على أندرويد أصلي ويعرض العربي بدون معالجة
    toast(msg if platform == 'android' else ar(msg))


# ---------------------------------------------------------------- الألوان
ACCENTS = ['#7C3AED', '#EC4899', '#F59E0B', '#10B981', '#3B82F6', '#EF4444', '#06B6D4', '#8B5CF6']


def gradient(c_left, c_right, n=64):
    """نسيج متدرج أفقي يُستخدم للشريط العلوي والأزرار."""
    a, b = hx(c_left), hx(c_right)
    buf = bytearray()
    for i in range(n):
        t = i / (n - 1.0)
        buf += bytes(int(255 * (a[k] + (b[k] - a[k]) * t)) for k in range(4))
    tex = Texture.create(size=(n, 1), colorfmt='rgba')
    tex.blit_buffer(bytes(buf), colorfmt='rgba', bufferfmt='ubyte')
    tex.wrap = 'clamp_to_edge'
    return tex


# ---------------------------------------------------------------- قاعدة البيانات
class DB:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA foreign_keys = ON')
        self.con.executescript('''
        CREATE TABLE IF NOT EXISTS depts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created TEXT);
        CREATE TABLE IF NOT EXISTS letters(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_id INTEGER NOT NULL REFERENCES depts(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            owner TEXT,
            created TEXT);
        CREATE TABLE IF NOT EXISTS images(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            letter_id INTEGER NOT NULL REFERENCES letters(id) ON DELETE CASCADE,
            file TEXT NOT NULL,
            thumb TEXT,
            pos INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS ix_letters_dept ON letters(dept_id);
        CREATE INDEX IF NOT EXISTS ix_images_letter ON images(letter_id);
        ''')
        cols = [r[1] for r in self.con.execute('PRAGMA table_info(images)')]
        if 'kind' not in cols:      # ترقية قاعدة بيانات الإصدارات السابقة
            self.con.execute("ALTER TABLE images ADD COLUMN kind TEXT DEFAULT 'img'")
        if 'orig' not in cols:
            self.con.execute('ALTER TABLE images ADD COLUMN orig TEXT')
        self.con.commit()

    @staticmethod
    def now():
        return datetime.now().strftime('%Y-%m-%d %H:%M')

    # ---- الدوائر
    def depts(self, q=''):
        return self.con.execute('''
            SELECT d.*, (SELECT COUNT(*) FROM letters l WHERE l.dept_id = d.id) AS n
            FROM depts d WHERE d.name LIKE ? ORDER BY d.name''', ('%' + q + '%',)).fetchall()

    def dept_exists(self, name, exclude_id=0):
        return self.con.execute('SELECT 1 FROM depts WHERE name = ? AND id != ?',
                                (name, exclude_id)).fetchone() is not None

    def add_dept(self, name):
        self.con.execute('INSERT INTO depts(name, created) VALUES(?, ?)', (name, self.now()))
        self.con.commit()

    def rename_dept(self, dept_id, name):
        self.con.execute('UPDATE depts SET name = ? WHERE id = ?', (name, dept_id))
        self.con.commit()

    def delete_dept(self, dept_id):
        files = self.con.execute('''
            SELECT i.file, i.thumb FROM images i JOIN letters l ON l.id = i.letter_id
            WHERE l.dept_id = ?''', (dept_id,)).fetchall()
        self.con.execute('DELETE FROM depts WHERE id = ?', (dept_id,))
        self.con.commit()
        return [f for r in files for f in (r['file'], r['thumb'])]

    # ---- الكتب
    def letters(self, dept_id, q=''):
        like = '%' + q + '%'
        return self.con.execute('''
            SELECT l.*,
              (SELECT COUNT(*) FROM images i WHERE i.letter_id = l.id) AS n,
              (SELECT thumb FROM images i WHERE i.letter_id = l.id AND IFNULL(i.kind, 'img') = 'img'
               ORDER BY pos, id LIMIT 1) AS th
            FROM letters l
            WHERE l.dept_id = ? AND (l.title LIKE ? OR IFNULL(l.owner, '') LIKE ?)
            ORDER BY l.id DESC''', (dept_id, like, like)).fetchall()

    def get_letter(self, letter_id):
        return self.con.execute('SELECT * FROM letters WHERE id = ?', (letter_id,)).fetchone()

    def add_letter(self, dept_id, title, owner):
        cur = self.con.execute(
            'INSERT INTO letters(dept_id, title, owner, created) VALUES(?, ?, ?, ?)',
            (dept_id, title, owner, self.now()))
        self.con.commit()
        return cur.lastrowid

    def update_letter(self, letter_id, title, owner):
        self.con.execute('UPDATE letters SET title = ?, owner = ? WHERE id = ?',
                         (title, owner, letter_id))
        self.con.commit()

    def delete_letter(self, letter_id):
        files = self.con.execute('SELECT file, thumb FROM images WHERE letter_id = ?',
                                 (letter_id,)).fetchall()
        self.con.execute('DELETE FROM letters WHERE id = ?', (letter_id,))
        self.con.commit()
        return [f for r in files for f in (r['file'], r['thumb'])]

    # ---- الصور
    def images(self, letter_id):
        return self.con.execute('SELECT * FROM images WHERE letter_id = ? ORDER BY pos, id',
                                (letter_id,)).fetchall()

    def add_image(self, letter_id, file, thumb, pos, kind='img', orig=None):
        cur = self.con.execute(
            'INSERT INTO images(letter_id, file, thumb, pos, kind, orig) VALUES(?, ?, ?, ?, ?, ?)',
            (letter_id, file, thumb, pos, kind, orig))
        return cur.lastrowid

    def set_image_pos(self, image_id, pos):
        self.con.execute('UPDATE images SET pos = ? WHERE id = ?', (pos, image_id))

    def delete_image(self, image_id):
        self.con.execute('DELETE FROM images WHERE id = ?', (image_id,))

    def commit(self):
        self.con.commit()


# ---------------------------------------------------------------- معالجة الصور والملفات
IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
DOC_EXTS = {'.pdf': 'pdf', '.doc': 'word', '.docx': 'word'}
MIMES = {'.pdf': 'application/pdf',
         '.doc': 'application/msword',
         '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}


def import_any(src, store_dir, mode):
    """mode = 'img' للصور، 'doc' لملفات وورد و PDF. يرجع dict أو يرفع خطأ."""
    base = os.path.basename(src)
    ext = os.path.splitext(base)[1].lower()
    if mode == 'doc':
        if ext not in DOC_EXTS:
            raise ValueError('unsupported: ' + base)
        import shutil
        name = uuid.uuid4().hex + ext
        shutil.copyfile(src, os.path.join(store_dir, name))
        return {'id': None, 'file': name, 'thumb': None, 'kind': DOC_EXTS[ext], 'orig': base}
    big, th = import_image(src, store_dir)
    return {'id': None, 'file': big, 'thumb': th, 'kind': 'img', 'orig': base}


def import_image(src, img_dir):
    """نسخ الصورة لمجلد التطبيق: تصحيح الاتجاه، تصغير معقول، ومصغّرة للقوائم."""
    name = uuid.uuid4().hex
    big, th = name + '.jpg', name + '_t.jpg'
    try:
        from PIL import Image as PImage, ImageOps
    except ImportError:
        import shutil
        ext = os.path.splitext(src)[1] or '.jpg'
        shutil.copy(src, os.path.join(img_dir, name + ext))
        return name + ext, name + ext
    im = PImage.open(src)
    im = ImageOps.exif_transpose(im)
    if im.mode != 'RGB':
        im = im.convert('RGB')
    if max(im.size) > 3000:                    # يبقى واضحاً للقراءة ويوفر المساحة
        im.thumbnail((3000, 3000))
    im.save(os.path.join(img_dir, big), 'JPEG', quality=90)
    im.thumbnail((360, 360))
    im.save(os.path.join(img_dir, th), 'JPEG', quality=80)
    return big, th


# ---------------------------------------------------------------- عناصر الواجهة
class ArabicInput(TextInput):
    """حقل إدخال عربي: النص الحقيقي في raw، والمعروض مُعالج."""
    raw = StringProperty('')
    hint_raw = StringProperty('')

    def __init__(self, **kw):
        super().__init__(**kw)
        self.multiline = False
        self.write_tab = False
        self.halign = 'right'
        self.keyboard_suggestions = False
        self.font_size = sp(17)
        self.bind(hint_raw=self._hint)
        self._hint()

    def _hint(self, *a):
        self.hint_text = ar(self.hint_raw)

    def insert_text(self, substring, from_undo=False):
        substring = substring.replace('\n', '').replace('\r', '')
        if substring:
            self.raw += substring
            self._show()

    def do_backspace(self, from_undo=False, mode='bkspc'):
        if self.raw:
            self.raw = self.raw[:-1]
            self._show()

    def set_raw(self, text):
        self.raw = text or ''
        self._show()

    def _show(self):
        self.text = ar(self.raw)
        Clock.schedule_once(lambda dt: setattr(self, 'cursor', (0, 0)), 0)


class ActionBtn(MDCard):
    text = StringProperty('')
    bg = ListProperty([0.49, 0.23, 0.93, 1])
    use_grad = BooleanProperty(False)


class DeptCard(MDCard):
    dept_id = NumericProperty(0)
    name_raw = StringProperty('')
    count = NumericProperty(0)
    accent = ListProperty([0.49, 0.23, 0.93, 1])


class LetterCard(MDCard):
    letter_id = NumericProperty(0)
    title_raw = StringProperty('')
    owner_raw = StringProperty('')
    date = StringProperty('')
    n = NumericProperty(0)
    thumb = StringProperty('')
    accent = ListProperty([0.49, 0.23, 0.93, 1])


class IconBadge(RelativeLayout):
    accent = ListProperty([0.49, 0.23, 0.93, 1])
    icon = StringProperty('folder')


class ThumbButton(ButtonBehavior, Image):
    pass


class DocTile(ButtonBehavior, RelativeLayout):
    kind = StringProperty('pdf')
    fname = StringProperty('')


class ZoomScatter(Scatter):
    """تكبير بإصبعين، نقرتان للتكبير/الإرجاع، سحب جانبي للتنقل."""
    viewer = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        self._busy = False
        super().__init__(**kw)
        self.do_rotation = False
        self.scale_min = 1
        self.scale_max = 6
        self.auto_bring_to_front = False
        self.do_translation = False
        self.bind(scale=self._on_scale)

    def _on_scale(self, *a):
        if self._busy:
            return
        self._busy = True
        try:
            zoomed = self.scale > 1.02
            self.do_translation = zoomed
            if not zoomed and self.parent is not None \
                    and tuple(self.pos) != tuple(self.parent.pos):
                self.pos = self.parent.pos
        finally:
            self._busy = False

    def reset(self):
        self._busy = True
        try:
            self.transform = Matrix()
            if self.parent is not None:
                self.pos = self.parent.pos
            self.do_translation = False
        finally:
            self._busy = False

    def on_touch_down(self, touch):
        if self.parent is None or not self.parent.collide_point(*touch.pos):
            return False
        if touch.is_double_tap:
            if self.scale > 1.02:
                self.reset()
            else:
                self.apply_transform(Matrix().scale(2.5, 2.5, 2.5), anchor=touch.pos)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self and self.scale <= 1.02 and self.viewer:
            dx, dy = touch.x - touch.ox, touch.y - touch.oy
            if abs(dx) > dp(60) and abs(dx) > abs(dy) * 1.5:
                self.viewer.step(1 if dx > 0 else -1)
        return super().on_touch_up(touch)


# ---------------------------------------------------------------- الشاشات
class DeptScreen(Screen):
    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self, *a):
        app = MDApp.get_running_app()
        q = self.ids.search.raw.strip()
        box = self.ids.box
        box.clear_widgets()
        rows = app.db.depts(q)
        for r in rows:
            box.add_widget(DeptCard(dept_id=r['id'], name_raw=r['name'], count=r['n'],
                                   accent=app.accent_for(r['id'])))
        self.ids.empty.text = '' if rows else ar(
            'لا توجد نتائج' if q else 'لا توجد دوائر بعد — اضغط + للإضافة')

    def add_dept(self):
        app = MDApp.get_running_app()

        def ok(name):
            if app.db.dept_exists(name):
                show_toast('هذه الدائرة موجودة مسبقاً')
                return
            app.db.add_dept(name)
            self.refresh()
        app.ask_text('دائرة جديدة', '', 'اسم الدائرة', ok)

    def rename_dept(self, dept_id, name):
        app = MDApp.get_running_app()

        def ok(new):
            if app.db.dept_exists(new, dept_id):
                show_toast('هذه الدائرة موجودة مسبقاً')
                return
            app.db.rename_dept(dept_id, new)
            self.refresh()
        app.ask_text('تعديل اسم الدائرة', name, 'اسم الدائرة', ok)

    def delete_dept(self, dept_id, name):
        app = MDApp.get_running_app()

        def ok():
            app.remove_files(app.db.delete_dept(dept_id))
            self.refresh()
            show_toast('تم حذف الدائرة')
        app.confirm('حذف الدائرة وكل كتبها؟', name, ok)


class LettersScreen(Screen):
    dept_id = NumericProperty(0)
    dept_name = StringProperty('')

    def on_pre_enter(self, *a):
        self.refresh()

    def refresh(self, *a):
        app = MDApp.get_running_app()
        q = self.ids.search.raw.strip()
        box = self.ids.box
        box.clear_widgets()
        rows = app.db.letters(self.dept_id, q)
        for r in rows:
            box.add_widget(LetterCard(
                letter_id=r['id'], title_raw=r['title'], owner_raw=r['owner'] or '',
                date=(r['created'] or '')[:10], n=r['n'],
                thumb=app.path(r['th']) if r['th'] else '', accent=app.accent_for(self.dept_id)))
        self.ids.empty.text = '' if rows else ar(
            'لا توجد نتائج' if q else 'لا توجد كتب — اضغط + لإضافة كتاب')

    def delete_letter(self, letter_id, title):
        app = MDApp.get_running_app()

        def ok():
            app.remove_files(app.db.delete_letter(letter_id))
            self.refresh()
            show_toast('تم حذف الكتاب')
        app.confirm('حذف الكتاب وصوره؟', title, ok)


class LetterScreen(Screen):
    def on_kv_post(self, base):
        self.items, self.removed = [], []
        self.dirty = self.busy = False
        self.dept_id, self.letter_id = 0, None
        self.ids.title.bind(raw=self._mark)
        self.ids.owner.bind(raw=self._mark)

    def _mark(self, *a):
        self.dirty = True

    def load(self, dept_id, letter_id=None):
        app = MDApp.get_running_app()
        self.dept_id, self.letter_id = dept_id, letter_id
        self.items, self.removed = [], []
        self.set_busy(False)
        if letter_id:
            r = app.db.get_letter(letter_id)
            self.ids.title.set_raw(r['title'])
            self.ids.owner.set_raw(r['owner'] or '')
            self.ids.date_lbl.text = ar('تاريخ الإضافة: ' + (r['created'] or ''))
            self.items = [{'id': i['id'], 'file': i['file'], 'thumb': i['thumb'],
                           'kind': i['kind'] or 'img', 'orig': i['orig'] or ''}
                          for i in app.db.images(letter_id)]
            self.ids.hdr.text = ar('تفاصيل الكتاب')
        else:
            self.ids.title.set_raw('')
            self.ids.owner.set_raw('')
            self.ids.date_lbl.text = ''
            self.ids.hdr.text = ar('كتاب جديد')
        self.dirty = False
        self.render_images()

    def render_images(self):
        app = MDApp.get_running_app()
        grid = self.ids.grid
        grid.clear_widgets()
        for idx, it in enumerate(self.items):
            cell = RelativeLayout(size_hint_y=None, height=dp(130))
            if it['kind'] == 'img':
                cell.add_widget(ThumbButton(source=app.path(it['thumb']), fit_mode='cover',
                                            on_release=lambda w, i=idx: self.open_viewer(i)))
            else:
                cell.add_widget(DocTile(kind=it['kind'], fname=it['orig'] or it['file'],
                                        on_release=lambda w, i=idx: self.open_doc(i)))
            cell.add_widget(MDIconButton(icon='close-circle', theme_icon_color='Custom',
                                         icon_color=(.85, .15, .15, 1) if it['kind'] == 'img'
                                         else (1, 1, 1, 1),
                                         pos_hint={'x': 0, 'top': 1},
                                         on_release=lambda w, i=idx: self.remove_image(i)))
            grid.add_widget(cell)
        n = len(self.items)
        ni = sum(1 for it in self.items if it['kind'] == 'img')
        self.ids.img_count.text = ar('المرفقات: %d صورة  •  %d ملف' % (ni, n - ni))
        self.ids.no_imgs.text = '' if n else ar('لا توجد مرفقات بعد')

    def set_busy(self, busy):
        self.busy = busy
        self.ids.busy.text = ar('جاري إضافة المرفقات...') if busy else ''
        self.ids.busy.height = dp(30) if busy else 0

    def add_images(self):
        if not self.busy:
            MDApp.get_running_app().pick_files(self, 'img')

    def add_docs(self):
        if not self.busy:
            MDApp.get_running_app().pick_files(self, 'doc')

    def add_imported(self, done, total, mode='img'):
        self.items.extend(done)
        if done:
            self.dirty = True
        self.set_busy(False)
        self.render_images()
        if len(done) < total:
            show_toast('تعذرت إضافة بعض الصور' if mode == 'img'
                       else 'يُقبل فقط ملفات PDF و Word')

    def open_doc(self, idx):
        it = self.items[idx]
        MDApp.get_running_app().doc_actions(it['file'], it['orig'] or it['file'])

    def remove_image(self, idx):
        app = MDApp.get_running_app()
        it = self.items.pop(idx)
        if it['id'] is None:
            app.remove_files([it['file'], it['thumb']])
        else:
            self.removed.append(it)
        self.dirty = True
        self.render_images()

    def open_viewer(self, idx):
        app = MDApp.get_running_app()
        imgs = [i for i, it in enumerate(self.items) if it['kind'] == 'img']
        app.open_viewer([app.path(self.items[i]['file']) for i in imgs], imgs.index(idx))

    def save(self):
        if self.busy:
            return
        app = MDApp.get_running_app()
        db = app.db
        title = self.ids.title.raw.strip()
        owner = self.ids.owner.raw.strip()
        if not title:
            show_toast('اكتب عنوان الكتاب')
            return
        if self.letter_id is None:
            self.letter_id = db.add_letter(self.dept_id, title, owner)
        else:
            db.update_letter(self.letter_id, title, owner)
        for it in self.removed:
            db.delete_image(it['id'])
        for pos, it in enumerate(self.items):
            if it['id'] is None:
                it['id'] = db.add_image(self.letter_id, it['file'], it['thumb'], pos,
                                        it['kind'], it['orig'])
            else:
                db.set_image_pos(it['id'], pos)
        db.commit()
        app.remove_files([f for it in self.removed for f in (it['file'], it['thumb'])])
        self.removed = []
        self.dirty = False
        show_toast('تم الحفظ')
        app.switch('letters', forward=False)

    def try_close(self):
        if self.busy:
            return
        if self.dirty:
            MDApp.get_running_app().confirm('الخروج بدون حفظ؟', 'ستفقد التغييرات الأخيرة',
                                            self._discard, ok_text='خروج')
        else:
            self._discard()

    def _discard(self):
        app = MDApp.get_running_app()
        app.remove_files([f for it in self.items if it['id'] is None
                          for f in (it['file'], it['thumb'])])
        self.items, self.removed, self.dirty = [], [], False
        app.switch('letters', forward=False)


class ViewerScreen(Screen):
    def on_kv_post(self, base):
        self.paths, self.idx = [], 0
        self.ids.sc.viewer = self

    def show(self, paths, idx):
        self.paths, self.idx = paths, idx
        self._load()

    def _load(self):
        if not self.paths:
            return
        self.ids.img.source = self.paths[self.idx]
        self.ids.sc.reset()
        self.ids.counter.text = '%d / %d' % (self.idx + 1, len(self.paths))

    def step(self, d):
        new = self.idx + d
        if 0 <= new < len(self.paths):
            self.idx = new
            self._load()

    def on_leave(self, *a):
        self.ids.img.source = ''


# ---------------------------------------------------------------- KV
KV = r'''
#:import hx kivy.utils.get_color_from_hex

<RLabel@Label>:
    color: app.c_text
    font_size: sp(15)
    halign: 'right'
    valign: 'middle'
    size_hint_y: None
    height: dp(26)
    text_size: self.size
    shorten: True
    shorten_from: 'left'

<BarTitle@Label>:
    font_size: sp(19)
    bold: True
    color: 1, 1, 1, 1
    halign: 'right'
    valign: 'middle'
    text_size: self.size
    shorten: True
    shorten_from: 'left'

<TopBar@BoxLayout>:
    size_hint_y: None
    height: dp(60)
    padding: dp(6), 0, dp(10), 0
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 1
        Rectangle:
            pos: self.pos
            size: self.size
            texture: app.grad

<WhiteIcon@MDIconButton>:
    theme_icon_color: 'Custom'
    icon_color: 1, 1, 1, 1
    pos_hint: {'center_y': .5}

<EmptyLabel@Label>:
    color: app.c_muted
    font_size: sp(16)
    size_hint: None, None
    size: self.texture_size
    pos_hint: {'center_x': .5, 'center_y': .5}

<AppFab@MDFloatingActionButton>:
    icon: 'plus'
    icon_color: 1, 1, 1, 1
    theme_icon_color: 'Custom'
    md_bg_color: app.c_pink
    pos_hint: {}

<ArabicInput>:
    background_normal: ''
    background_active: ''
    background_color: 1, 1, 1, 1
    foreground_color: app.c_text
    hint_text_color: .62, .6, .72, 1
    cursor_color: app.c_violet
    padding: [dp(12), max(0, (self.height - self.line_height) / 2.0), dp(12), 0]
    canvas.after:
        Color:
            rgba: app.c_violet if self.focus else (.84, .8, .95, 1)
        Line:
            rounded_rectangle: self.x, self.y, self.width, self.height, dp(12)
            width: 1.6 if self.focus else 1.2

<ActionBtn>:
    size_hint_y: None
    height: dp(50)
    radius: [dp(14)]
    ripple_behavior: True
    md_bg_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: (1, 1, 1, 1) if root.use_grad else root.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
            texture: app.grad if root.use_grad else None
    Label:
        text: app.ar(root.text)
        bold: True
        font_size: sp(17)
        color: 1, 1, 1, 1

<IconBadge>:
    size_hint: None, None
    size: dp(48), dp(48)
    pos_hint: {'center_y': .5}
    canvas.before:
        Color:
            rgba: self.accent[0], self.accent[1], self.accent[2], .15
        Ellipse:
            pos: 0, 0
            size: self.size
    MDIcon:
        icon: root.icon
        halign: 'center'
        theme_text_color: 'Custom'
        text_color: root.accent
        font_size: sp(26)
        size_hint: None, None
        size: self.texture_size
        pos_hint: {'center_x': .5, 'center_y': .5}

<DocTile>:
    canvas.before:
        Color:
            rgba: app.c_pdf if root.kind == 'pdf' else app.c_word
        RoundedRectangle:
            pos: 0, 0
            size: self.size
            radius: [dp(12)]
    MDIcon:
        icon: 'file-pdf-box' if root.kind == 'pdf' else 'file-word-box'
        theme_text_color: 'Custom'
        text_color: 1, 1, 1, 1
        font_size: sp(46)
        halign: 'center'
        size_hint: None, None
        size: self.texture_size
        pos_hint: {'center_x': .5, 'center_y': .62}
    Label:
        text: app.ar(root.fname)
        font_size: sp(12)
        color: 1, 1, 1, 1
        halign: 'center'
        valign: 'middle'
        size_hint: None, None
        size: root.width - dp(10), dp(34)
        pos: dp(5), dp(6)
        text_size: self.size
        shorten: True
        shorten_from: 'right'

<DeptCard>:
    size_hint_y: None
    height: dp(80)
    radius: [dp(16)]
    elevation: 1
    padding: dp(4), 0, dp(16), 0
    spacing: dp(6)
    md_bg_color: 1, 1, 1, 1
    ripple_behavior: True
    on_release: app.open_dept(root.dept_id, root.name_raw)
    canvas.after:
        Color:
            rgba: root.accent
        RoundedRectangle:
            pos: self.right - dp(6), self.y
            size: dp(6), self.height
            radius: [0, dp(16), dp(16), 0]
    MDIconButton:
        icon: 'delete-outline'
        theme_icon_color: 'Custom'
        icon_color: app.c_red
        pos_hint: {'center_y': .5}
        on_release: app.root.get_screen('depts').delete_dept(root.dept_id, root.name_raw)
    MDIconButton:
        icon: 'pencil-outline'
        theme_icon_color: 'Custom'
        icon_color: app.c_violet
        pos_hint: {'center_y': .5}
        on_release: app.root.get_screen('depts').rename_dept(root.dept_id, root.name_raw)
    BoxLayout:
        orientation: 'vertical'
        padding: 0, dp(13)
        Label:
            text: app.ar(root.name_raw)
            font_size: sp(18)
            bold: True
            color: app.c_text
            halign: 'right'
            valign: 'middle'
            text_size: self.size
            shorten: True
            shorten_from: 'left'
        Label:
            text: app.ar('عدد الكتب: ' + str(root.count))
            font_size: sp(14)
            bold: True
            color: root.accent
            halign: 'right'
            valign: 'middle'
            text_size: self.size
    IconBadge:
        accent: root.accent
        icon: 'folder'

<LetterCard>:
    size_hint_y: None
    height: dp(96)
    radius: [dp(16)]
    elevation: 1
    padding: dp(4), dp(10), dp(16), dp(10)
    spacing: dp(8)
    md_bg_color: 1, 1, 1, 1
    ripple_behavior: True
    on_release: app.open_letter(root.letter_id)
    canvas.after:
        Color:
            rgba: root.accent
        RoundedRectangle:
            pos: self.right - dp(6), self.y
            size: dp(6), self.height
            radius: [0, dp(16), dp(16), 0]
    MDIconButton:
        icon: 'delete-outline'
        theme_icon_color: 'Custom'
        icon_color: app.c_red
        pos_hint: {'center_y': .5}
        on_release: app.root.get_screen('letters').delete_letter(root.letter_id, root.title_raw)
    BoxLayout:
        orientation: 'vertical'
        Label:
            text: app.ar(root.title_raw)
            font_size: sp(17)
            bold: True
            color: app.c_text
            halign: 'right'
            valign: 'middle'
            text_size: self.size
            shorten: True
            shorten_from: 'left'
        Label:
            text: app.ar('صاحب الشأن: ' + (root.owner_raw or '-'))
            font_size: sp(14)
            color: .32, .3, .45, 1
            halign: 'right'
            valign: 'middle'
            text_size: self.size
            shorten: True
            shorten_from: 'left'
        Label:
            text: app.ar(root.date + '   |   المرفقات: ' + str(root.n))
            font_size: sp(13)
            bold: True
            color: root.accent
            halign: 'right'
            valign: 'middle'
            text_size: self.size
    RelativeLayout:
        size_hint_x: None
        width: dp(70)
        canvas.before:
            Color:
                rgba: root.accent[0], root.accent[1], root.accent[2], .14
            RoundedRectangle:
                pos: 0, 0
                size: self.size
                radius: [dp(12)]
        MDIcon:
            icon: 'file-document-outline'
            halign: 'center'
            theme_text_color: 'Custom'
            text_color: root.accent
            opacity: 0 if root.thumb else 1
        Image:
            source: root.thumb
            fit_mode: 'cover'
            opacity: 1 if root.thumb else 0

<DeptScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: app.c_bg
            Rectangle:
                pos: self.pos
                size: self.size
        TopBar:
            BarTitle:
                text: app.ar('أرشيف الكتب')
            MDIcon:
                icon: 'archive'
                theme_text_color: 'Custom'
                text_color: 1, 1, 1, 1
                size_hint_x: None
                width: dp(34)
                pos_hint: {'center_y': .5}
        BoxLayout:
            size_hint_y: None
            height: dp(66)
            padding: dp(12), dp(8)
            ArabicInput:
                id: search
                hint_raw: 'ابحث عن دائرة...'
                on_raw: root.refresh()
        ScrollView:
            do_scroll_x: False
            MDBoxLayout:
                id: box
                orientation: 'vertical'
                adaptive_height: True
                padding: dp(12), dp(4), dp(12), dp(96)
                spacing: dp(10)
        BoxLayout:
            size_hint_y: None
            height: dp(40)
            spacing: dp(6)
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
                Rectangle:
                    pos: self.x, self.top - dp(3)
                    size: self.width, dp(3)
                    texture: app.grad
            Widget
            Label:
                text: app.ar('تصميم عمر كريم')
                bold: True
                font_size: sp(14)
                color: app.c_violet
                size_hint_x: None
                width: self.texture_size[0]
            MDIcon:
                icon: 'pencil-ruler'
                theme_text_color: 'Custom'
                text_color: app.c_pink
                font_size: sp(20)
                size_hint_x: None
                width: dp(24)
                pos_hint: {'center_y': .5}
            Widget
    EmptyLabel:
        id: empty
    AppFab:
        pos: dp(18), dp(58)
        on_release: root.add_dept()

<LettersScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: app.c_bg
            Rectangle:
                pos: self.pos
                size: self.size
        TopBar:
            BarTitle:
                text: app.ar(root.dept_name)
            WhiteIcon:
                icon: 'arrow-right'
                on_release: app.go_back()
        BoxLayout:
            size_hint_y: None
            height: dp(66)
            padding: dp(12), dp(8)
            ArabicInput:
                id: search
                hint_raw: 'ابحث بالعنوان أو صاحب الشأن...'
                on_raw: root.refresh()
        ScrollView:
            do_scroll_x: False
            MDBoxLayout:
                id: box
                orientation: 'vertical'
                adaptive_height: True
                padding: dp(12), dp(4), dp(12), dp(96)
                spacing: dp(10)
    EmptyLabel:
        id: empty
    AppFab:
        pos: dp(18), dp(22)
        on_release: app.new_letter()

<LetterScreen>:
    BoxLayout:
        orientation: 'vertical'
        canvas.before:
            Color:
                rgba: app.c_bg
            Rectangle:
                pos: self.pos
                size: self.size
        TopBar:
            BarTitle:
                id: hdr
            WhiteIcon:
                icon: 'arrow-right'
                on_release: root.try_close()
        ScrollView:
            do_scroll_x: False
            MDBoxLayout:
                orientation: 'vertical'
                adaptive_height: True
                padding: dp(14)
                spacing: dp(8)
                RLabel:
                    text: app.ar('عنوان الكتاب')
                    bold: True
                    color: app.c_violet
                ArabicInput:
                    id: title
                    size_hint_y: None
                    height: dp(50)
                    hint_raw: 'مثال: كتاب رقم 125 بخصوص...'
                RLabel:
                    text: app.ar('اسم صاحب الشأن')
                    bold: True
                    color: app.c_violet
                ArabicInput:
                    id: owner
                    size_hint_y: None
                    height: dp(50)
                    hint_raw: 'الاسم الكامل'
                RLabel:
                    id: date_lbl
                    color: app.c_muted
                    font_size: sp(13)
                BoxLayout:
                    size_hint_y: None
                    height: dp(46)
                    spacing: dp(10)
                    ActionBtn:
                        text: 'إضافة ملف Word / PDF'
                        bg: app.c_violet
                        height: dp(44)
                        pos_hint: {'center_y': .5}
                        on_release: root.add_docs()
                    ActionBtn:
                        text: 'إضافة صور'
                        bg: app.c_pink
                        size_hint_x: .7
                        height: dp(44)
                        pos_hint: {'center_y': .5}
                        on_release: root.add_images()
                RLabel:
                    id: img_count
                    bold: True
                    color: app.c_violet
                    height: dp(30)
                Label:
                    id: busy
                    size_hint_y: None
                    height: 0
                    bold: True
                    color: app.c_pink
                    font_size: sp(15)
                GridLayout:
                    id: grid
                    cols: 3
                    spacing: dp(8)
                    size_hint_y: None
                    height: self.minimum_height
                RLabel:
                    id: no_imgs
                    halign: 'center'
                    color: app.c_muted
        BoxLayout:
            size_hint_y: None
            height: dp(74)
            padding: dp(14), dp(12)
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            ActionBtn:
                text: 'حفظ'
                use_grad: True
                on_release: root.save()

<ViewerScreen>:
    canvas.before:
        Color:
            rgba: .06, .04, .12, 1
        Rectangle:
            pos: self.pos
            size: self.size
    BoxLayout:
        orientation: 'vertical'
        TopBar:
            Label:
                id: counter
                color: 1, 1, 1, 1
                bold: True
                font_size: sp(16)
                halign: 'left'
                valign: 'middle'
                padding: dp(8), 0
                text_size: self.size
            WhiteIcon:
                icon: 'arrow-right'
                on_release: app.go_back()
        StencilView:
            id: stage
            ZoomScatter:
                id: sc
                size: stage.size
                pos: stage.pos
                Image:
                    id: img
                    size: sc.size
                    fit_mode: 'contain'
                    nocache: True
        BoxLayout:
            size_hint_y: None
            height: dp(64)
            padding: dp(10), 0
            WhiteIcon:
                icon: 'chevron-left'
                icon_size: sp(34)
                on_release: root.step(1)
            Label:
                text: app.ar('نقرتان للتكبير')
                color: .75, .72, .85, 1
                font_size: sp(13)
            WhiteIcon:
                icon: 'chevron-right'
                icon_size: sp(34)
                on_release: root.step(-1)
'''


# ---------------------------------------------------------------- التطبيق
class ArchiveApp(MDApp):
    def build(self):
        self.title = 'أرشيف الكتب'
        self.theme_cls.primary_palette = 'DeepPurple'
        self.theme_cls.theme_style = 'Light'
        if os.path.exists(os.path.join(HERE, 'icon.png')):
            self.icon = os.path.join(HERE, 'icon.png')
        self.c_violet = hx('#7C3AED')
        self.c_pink = hx('#EC4899')
        self.c_red = hx('#EF4444')
        self.c_bg = hx('#F5F3FF')
        self.c_text = hx('#1E1B4B')
        self.c_muted = hx('#8B87A8')
        self.c_pdf = hx('#E11D48')
        self.c_word = hx('#2563EB')
        self.grad = gradient('#EC4899', '#7C3AED')
        Window.softinput_mode = 'below_target'

        self.img_dir = os.path.join(self.user_data_dir, 'images')
        os.makedirs(self.img_dir, exist_ok=True)
        self.db = DB(os.path.join(self.user_data_dir, 'archive.db'))
        self._pick_screen = None
        self.chooser = None

        Builder.load_string(KV)
        sm = ScreenManager(transition=SlideTransition(duration=.18))
        sm.add_widget(DeptScreen(name='depts'))
        sm.add_widget(LettersScreen(name='letters'))
        sm.add_widget(LetterScreen(name='letter'))
        sm.add_widget(ViewerScreen(name='viewer'))
        Window.bind(on_keyboard=self._on_key)
        return sm

    def on_start(self):
        self.root.get_screen('depts').refresh()
        if platform == 'android':
            self.chooser = Chooser(self._on_chosen)

    def on_pause(self):
        return True

    # ---- أدوات
    def ar(self, text):
        return ar(text)

    def accent_for(self, dept_id):
        return hx(ACCENTS[int(dept_id) % len(ACCENTS)])

    def path(self, name):
        return os.path.join(self.img_dir, name)

    def remove_files(self, names):
        for n in set(filter(None, names)):
            try:
                os.remove(self.path(n))
            except OSError:
                pass

    # ---- التنقل
    def switch(self, name, forward=True):
        self.root.transition.direction = 'right' if forward else 'left'
        self.root.current = name

    def open_dept(self, dept_id, name):
        s = self.root.get_screen('letters')
        s.dept_id, s.dept_name = int(dept_id), name
        s.ids.search.set_raw('')
        self.switch('letters')

    def open_letter(self, letter_id):
        dept_id = self.root.get_screen('letters').dept_id
        self.root.get_screen('letter').load(dept_id, int(letter_id))
        self.switch('letter')

    def new_letter(self):
        dept_id = self.root.get_screen('letters').dept_id
        self.root.get_screen('letter').load(dept_id, None)
        self.switch('letter')

    def open_viewer(self, paths, idx):
        self.root.get_screen('viewer').show(paths, idx)
        self.switch('viewer')

    def go_back(self):
        cur = self.root.current
        if cur == 'viewer':
            self.switch('letter', forward=False)
        elif cur == 'letter':
            self.root.get_screen('letter').try_close()
        elif cur == 'letters':
            self.switch('depts', forward=False)
        else:
            return False
        return True

    def _on_key(self, window, key, *args):
        if key == 27:              # زر الرجوع في أندرويد / Esc
            return self.go_back()
        return False

    # ---- الحوارات
    def _align_dialog(self, dlg):
        for key in ('title', 'text'):
            try:
                dlg.ids[key].halign = 'right'
            except Exception:
                pass

    def ask_text(self, title, initial, hint, on_ok):
        field = ArabicInput(size_hint_y=None, height=dp(50), hint_raw=hint)
        field.set_raw(initial)
        box = MDBoxLayout(orientation='vertical', size_hint_y=None, height=dp(62),
                          padding=(0, dp(6), 0, dp(6)))
        box.add_widget(field)

        def submit(*a):
            val = field.raw.strip()
            if not val:
                show_toast('الحقل فارغ')
                return
            dlg.dismiss()
            on_ok(val)

        field.bind(on_text_validate=submit)
        dlg = MDDialog(title=ar(title), type='custom', content_cls=box, buttons=[
            MDFlatButton(text=ar('إلغاء'), on_release=lambda *a: dlg.dismiss()),
            MDRaisedButton(text=ar('حفظ'), md_bg_color=self.c_violet, on_release=submit)])
        self._align_dialog(dlg)
        dlg.open()
        Clock.schedule_once(lambda dt: setattr(field, 'focus', True), .35)

    def confirm(self, title, text, on_ok, ok_text='حذف'):
        def go(*a):
            dlg.dismiss()
            on_ok()
        dlg = MDDialog(title=ar(title), text=ar(text), buttons=[
            MDFlatButton(text=ar('إلغاء'), on_release=lambda *a: dlg.dismiss()),
            MDRaisedButton(text=ar(ok_text), md_bg_color=self.c_red, on_release=go)])
        self._align_dialog(dlg)
        dlg.open()

    # ---- اختيار الصور والملفات
    def pick_files(self, screen, mode):
        self._pick_screen, self._pick_mode = screen, mode
        if platform == 'android':
            # application/* يشمل PDF و Word بنوعيه
            self.chooser.choose_content('image/*' if mode == 'img' else 'application/*',
                                        multiple=True)
        else:
            self._desktop_picker(screen, mode)

    def _on_chosen(self, uri_list):
        if uri_list and self._pick_screen is not None:
            self._run_import(self._pick_screen, uris=uri_list,
                             mode=getattr(self, '_pick_mode', 'img'))

    def _desktop_picker(self, screen, mode='img'):
        from kivy.uix.popup import Popup
        from kivy.uix.filechooser import FileChooserIconView
        exts = IMG_EXTS if mode == 'img' else tuple(DOC_EXTS)
        pats = ['*' + e for e in exts]
        fc = FileChooserIconView(path=os.path.expanduser('~'), multiselect=True,
                                 filters=pats + [p.upper() for p in pats])
        lay = BoxLayout(orientation='vertical', spacing=dp(6))
        lay.add_widget(fc)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        pop = Popup(title=ar('اختر الصور' if mode == 'img' else 'اختر ملفات Word أو PDF'),
                    title_align='right', content=lay,
                    size_hint=(.95, .95))

        def ok(*a):
            sel = list(fc.selection)
            pop.dismiss()
            if sel:
                self._run_import(screen, paths=sel, mode=mode)
        row.add_widget(MDFlatButton(text=ar('إلغاء'), on_release=lambda *a: pop.dismiss()))
        row.add_widget(MDRaisedButton(text=ar('إضافة المحدد'), on_release=ok))
        lay.add_widget(row)
        pop.open()

    def _run_import(self, screen, uris=None, paths=None, mode='img'):
        Clock.schedule_once(lambda dt: screen.set_busy(True))

        def work():
            done, temps, srcs = [], [], list(paths or [])
            try:
                if uris:
                    ss = SharedStorage()
                    for u in uris:
                        try:
                            p = ss.copy_from_shared(u)
                            if p:
                                srcs.append(p)
                                temps.append(p)
                        except Exception as e:
                            print('copy failed:', e)
                for s in srcs:
                    try:
                        done.append(import_any(s, self.img_dir, mode))
                    except Exception as e:
                        print('import failed:', s, e)
                for t in temps:
                    try:
                        os.remove(t)
                    except OSError:
                        pass
            finally:
                if platform == 'android':
                    try:
                        from jnius import detach
                        detach()
                    except Exception:
                        pass
                total = max(len(srcs), len(uris or []))
                Clock.schedule_once(lambda dt: screen.add_imported(done, total, mode))

        threading.Thread(target=work, daemon=True).start()

    # ---- فتح ومشاركة ملفات Word و PDF
    def doc_actions(self, name, orig):
        def act(share):
            dlg.dismiss()
            self.open_doc(name, orig, share)
        dlg = MDDialog(title=ar(orig), buttons=[
            MDFlatButton(text=ar('مشاركة'), on_release=lambda *a: act(True)),
            MDRaisedButton(text=ar('فتح'), md_bg_color=self.c_violet,
                           on_release=lambda *a: act(False))])
        self._align_dialog(dlg)
        dlg.open()

    def open_doc(self, name, orig, share=False):
        path = self.path(name)
        ext = os.path.splitext(name)[1].lower()
        mime = MIMES.get(ext, '*/*')
        if platform != 'android':
            import subprocess
            import sys
            try:
                if sys.platform.startswith('win'):
                    os.startfile(path)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
            except Exception:
                show_toast('تعذر فتح الملف')
            return
        try:
            uri = self._shared_uri(path, orig, ext)
            if share:
                from androidstorage4kivy import ShareSheet
                ShareSheet().share_file(uri)
                return
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            String = autoclass('java.lang.String')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, mime)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            PythonActivity.mActivity.startActivity(
                Intent.createChooser(intent, String('فتح الملف')))
        except Exception as e:
            print('open doc failed:', e)
            show_toast('لا يوجد تطبيق لفتح هذا الملف — ثبّت قارئ PDF أو Word')

    def _shared_uri(self, path, orig, ext):
        """نسخ الملف إلى Documents باسمه الأصلي مرة واحدة في الجلسة للحصول على رابط يفتحه تطبيق آخر."""
        cache = getattr(self, '_uri_cache', None)
        if cache is None:
            cache = self._uri_cache = {}
        if path in cache:
            return cache[path]
        import shutil
        base = os.path.splitext(orig)[0] or 'file'
        safe = ''.join(c for c in base if c not in '\\/:*?"<>|') + ext
        tmp_dir = os.path.join(self.user_data_dir, 'share_tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        tmp = os.path.join(tmp_dir, safe)
        shutil.copyfile(path, tmp)
        try:
            uri = SharedStorage().copy_to_shared(tmp)
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        cache[path] = uri
        return uri


if __name__ == '__main__':
    ArchiveApp().run()
