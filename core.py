# -*- coding: utf-8 -*-
"""منطق نظام إدارة الاجازات والدوام — منقول حرفياً من النسخة المكتبية (تطوير وتصميم عمر كريم)."""
import sqlite3
import calendar
import hashlib
import os
import sys
from datetime import datetime, date, timedelta
# ═══════════════════════════════════════════════════════════
#  لوحة الألوان
# ═══════════════════════════════════════════════════════════
C = {
    'canvas':    '#eef2f7',
    'surface':   '#ffffff',
    'sidebar':   '#1e293b',
    'sidebar2':  '#334155',
    'accent':    '#4f46e5',
    'accent_dk': '#4338ca',
    'teal':      '#0d9488',
    'teal_dk':   '#0f766e',
    'amber':     '#d97706',
    'rose':      '#be123c',
    'text':      '#0f172a',
    'muted':     '#64748b',
    'border':    '#cbd5e1',
    'row_alt':   '#f1f5f9',
    'head_bg':   '#1e293b',
    's_duty':    '#dcfce7',
    's_off':     '#e2e8f0',
    's_leave':   '#fee2e2',
    's_holiday': '#fef3c7',
}

AR_DAYS = ['الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']

DUTY, OFF, LEAVE, HOLIDAY, WEEKEND = 'دوام', 'نزول', 'إجازة', 'عطلة رسمية', 'عطلة أسبوعية'
SCHED = 'مقرر'
ALL_EMPS = '— جميع الموظفين —'

# تاريخ بدء العمل بالنظام — كل الحقول الزمنية تبدأ منه
SYSTEM_START = date(2026, 9, 18)
DEV_MARK = "تطوير وتصميم عمر كريم"
DEFAULT_PIN = "1234"


# ═══════════════════════════════════════════════════════════
#  قاعدة البيانات
# ═══════════════════════════════════════════════════════════
def resolve_db_path(filename="leave_management.db"):
    """
    يحدّد مكان قاعدة البيانات:
      • بجانب البرنامج إن كان المجلد قابلاً للكتابة (تشغيل محمول)
      • وإلا في %APPDATA%\\DawamSystem  (بعد التثبيت في Program Files)
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    local = os.path.join(base, filename)
    if os.path.exists(local):
        return local
    try:
        probe = os.path.join(base, ".write_test")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return local
    except OSError:
        pass

    data_dir = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), 'DawamSystem')
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        return local
    return os.path.join(data_dir, filename)


class DB:
    def __init__(self, path=None):
        self.conn = sqlite3.connect(path or resolve_db_path())
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position TEXT,
            hire_date TEXT,
            shift_type TEXT,
            backup_id INTEGER,
            created_at TEXT,
            rotation_days INTEGER DEFAULT 10,
            rotation_start TEXT,
            rotation_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'نشط'
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS leave_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type TEXT,
            start_date TEXT,
            end_date TEXT,
            days REAL,
            notes TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            holiday_name TEXT,
            holiday_type TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')
        self.conn.commit()
        self._migrate()
        self._drop_legacy_holidays()

    # ---------- الرمز السري ----------
    @staticmethod
    def _hash(pin):
        return hashlib.sha256(("omar-karim-salt::" + str(pin)).encode('utf-8')).hexdigest()

    def get_setting(self, key, default=None):
        c = self.conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        r = c.fetchone()
        return r['value'] if r else default

    def set_setting(self, key, value):
        c = self.conn.cursor()
        c.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    def check_pin(self, pin):
        stored = self.get_setting('pin')
        if not stored:
            return str(pin) == DEFAULT_PIN
        return stored == self._hash(pin)

    def set_pin(self, pin):
        self.set_setting('pin', self._hash(pin))

    def _drop_legacy_holidays(self):
        """حذف العطل التي كانت تُضاف تلقائياً في النسخ السابقة — العطل تُضاف يدوياً فقط"""
        c = self.conn.cursor()
        legacy = ("رأس السنة الميلادية", "يوم الشهيد", "نوروز",
                  "ذكرى ثورة 14 تموز", "عيد الاستقلال", "عيد الفلاح",
                  "عيد الحب", "عيد العمال", "عيد الأم")
        try:
            c.execute("DELETE FROM holidays WHERE holiday_name IN (%s)"
                      % ",".join("?" * len(legacy)), legacy)
            self.conn.commit()
        except Exception:
            pass

    def _migrate(self):
        c = self.conn.cursor()
        cols = [r[1] for r in c.execute("PRAGMA table_info(employees)").fetchall()]
        for col, ddl in [('backup_id', 'INTEGER'),
                         ('created_at', 'TEXT'),
                         ('rotation_days', 'INTEGER DEFAULT 10'),
                         ('rotation_start', 'TEXT'),
                         ('rotation_order', 'INTEGER DEFAULT 0')]:
            if col not in cols:
                try:
                    c.execute("ALTER TABLE employees ADD COLUMN %s %s" % (col, ddl))
                except Exception:
                    pass
        self.conn.commit()

    # ---------- الموظفون ----------
    def add_employee(self, name, position, shift, hire_date=None):
        c = self.conn.cursor()
        now = max(datetime.now().date(), SYSTEM_START).strftime('%Y-%m-%d')
        try:
            c.execute("INSERT INTO employees (name, position, hire_date, shift_type, created_at) "
                      "VALUES (?,?,?,?,?)", (name, position, hire_date or now, shift, now))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_employee(self, emp_id, name, position, shift, hire_date=None):
        c = self.conn.cursor()
        try:
            c.execute("UPDATE employees SET name=?, position=?, shift_type=?, hire_date=? WHERE id=?",
                      (name, position, shift, hire_date, emp_id))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def employees(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM employees ORDER BY name")
        return [dict(r) for r in c.fetchall()]

    def employee(self, emp_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM employees WHERE id=?", (emp_id,))
        r = c.fetchone()
        return dict(r) if r else None

    def delete_employee(self, emp_id):
        c = self.conn.cursor()
        c.execute("DELETE FROM leave_requests WHERE employee_id=?", (emp_id,))
        c.execute("UPDATE employees SET backup_id=NULL WHERE backup_id=?", (emp_id,))
        c.execute("DELETE FROM employees WHERE id=?", (emp_id,))
        self.conn.commit()

    # ---------- التناوب ----------
    def link_pair(self, a_id, b_id, days, start):
        c = self.conn.cursor()
        c.execute("UPDATE employees SET backup_id=NULL WHERE backup_id IN (?,?)", (a_id, b_id))
        c.execute("UPDATE employees SET backup_id=?, rotation_days=?, rotation_start=?, rotation_order=0 WHERE id=?",
                  (b_id, days, start, a_id))
        c.execute("UPDATE employees SET backup_id=?, rotation_days=?, rotation_start=?, rotation_order=1 WHERE id=?",
                  (a_id, days, start, b_id))
        self.conn.commit()

    def unlink(self, emp_id):
        c = self.conn.cursor()
        e = self.employee(emp_id)
        if e and e.get('backup_id'):
            c.execute("UPDATE employees SET backup_id=NULL WHERE id=?", (e['backup_id'],))
        c.execute("UPDATE employees SET backup_id=NULL WHERE id=?", (emp_id,))
        self.conn.commit()

    def flip_pair(self, emp_id):
        e = self.employee(emp_id)
        if not e or not e.get('backup_id'):
            return False
        b = self.employee(e['backup_id'])
        c = self.conn.cursor()
        c.execute("UPDATE employees SET rotation_order=? WHERE id=?",
                  (1 - (e.get('rotation_order') or 0), e['id']))
        c.execute("UPDATE employees SET rotation_order=? WHERE id=?",
                  (1 - (b.get('rotation_order') or 0), b['id']))
        self.conn.commit()
        return True

    def set_rotation(self, emp_id, days, start):
        e = self.employee(emp_id)
        if not e:
            return False
        c = self.conn.cursor()
        c.execute("UPDATE employees SET rotation_days=?, rotation_start=? WHERE id=?", (days, start, emp_id))
        if e.get('backup_id'):
            c.execute("UPDATE employees SET rotation_days=?, rotation_start=? WHERE id=?",
                      (days, start, e['backup_id']))
        self.conn.commit()
        return True

    # ---------- الإجازات ----------
    def add_leave(self, emp_id, ltype, start, end, notes):
        s = datetime.strptime(start, '%Y-%m-%d').date()
        e = datetime.strptime(end, '%Y-%m-%d').date()
        if e < s:
            return False
        c = self.conn.cursor()
        c.execute("INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days, notes) "
                  "VALUES (?,?,?,?,?,?)", (emp_id, ltype, start, end, (e - s).days + 1, notes))
        self.conn.commit()
        return True

    def leaves(self):
        c = self.conn.cursor()
        c.execute("SELECT l.*, e.name, e.shift_type FROM leave_requests l "
                  "JOIN employees e ON e.id = l.employee_id ORDER BY l.start_date DESC")
        return [dict(r) for r in c.fetchall()]

    def leave(self, lid):
        c = self.conn.cursor()
        c.execute("SELECT * FROM leave_requests WHERE id=?", (lid,))
        r = c.fetchone()
        return dict(r) if r else None

    def update_leave(self, lid, emp_id, ltype, start, end, notes):
        s = datetime.strptime(start, '%Y-%m-%d').date()
        e = datetime.strptime(end, '%Y-%m-%d').date()
        if e < s:
            return False
        c = self.conn.cursor()
        c.execute("UPDATE leave_requests SET employee_id=?, leave_type=?, start_date=?, "
                  "end_date=?, days=?, notes=? WHERE id=?",
                  (emp_id, ltype, start, end, (e - s).days + 1, notes, lid))
        self.conn.commit()
        return True

    def leaves_of(self, emp_id):
        c = self.conn.cursor()
        c.execute("SELECT * FROM leave_requests WHERE employee_id=? ORDER BY start_date", (emp_id,))
        return [dict(r) for r in c.fetchall()]

    def leave(self, lid):
        c = self.conn.cursor()
        c.execute("SELECT * FROM leave_requests WHERE id=?", (lid,))
        r = c.fetchone()
        return dict(r) if r else None

    def update_leave(self, lid, emp_id, ltype, start, end, notes):
        s = datetime.strptime(start, '%Y-%m-%d').date()
        e = datetime.strptime(end, '%Y-%m-%d').date()
        if e < s:
            return False
        c = self.conn.cursor()
        c.execute("UPDATE leave_requests SET employee_id=?, leave_type=?, start_date=?, "
                  "end_date=?, days=?, notes=? WHERE id=?",
                  (emp_id, ltype, start, end, (e - s).days + 1, notes, lid))
        self.conn.commit()
        return True

    def delete_leave(self, lid):
        c = self.conn.cursor()
        c.execute("DELETE FROM leave_requests WHERE id=?", (lid,))
        self.conn.commit()

    # ---------- العطل ----------
    def add_holiday(self, d, name, htype):
        c = self.conn.cursor()
        try:
            c.execute("INSERT INTO holidays (date, holiday_name, holiday_type) VALUES (?,?,?)", (d, name, htype))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def holidays(self):
        c = self.conn.cursor()
        c.execute("SELECT * FROM holidays ORDER BY date")
        return [dict(r) for r in c.fetchall()]

    def delete_holiday(self, hid):
        c = self.conn.cursor()
        c.execute("DELETE FROM holidays WHERE id=?", (hid,))
        self.conn.commit()

    def clear_holidays(self):
        c = self.conn.cursor()
        c.execute("DELETE FROM holidays")
        self.conn.commit()

    def close(self):
        self.conn.close()


# ═══════════════════════════════════════════════════════════
#  محرك الجدولة
# ═══════════════════════════════════════════════════════════
class Scheduler:
    """
    القواعد:
      • الصباحي: يداوم كل يوم عدا الجمعة/السبت والعطل الرسمية.
      • الخفر المرتبط بوجبة: يداوم وجبة كاملة ثم ينزل وتبدأ وجبة بديله،
        فيكون دوام كل منهما عكس الآخر تماماً.
      • إجازة الخفر: تُحسب إجازة له وبديله يبقى في النزول ولا يُستدعى.
      • الخفر غير المرتبط: يداوم كل يوم عدا الجمعة/السبت.
    """

    def __init__(self, db):
        self.db = db
        self.reload()

    def reload(self):
        self.holidays = {h['date']: h for h in self.db.holidays()}
        self.leave_map = {}
        for l in self.db.leaves():
            try:
                s = datetime.strptime(l['start_date'], '%Y-%m-%d').date()
                e = datetime.strptime(l['end_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            self.leave_map.setdefault(l['employee_id'], []).append((s, e, l['leave_type']))

    def on_leave(self, emp_id, d):
        for s, e, t in self.leave_map.get(emp_id, []):
            if s <= d <= e:
                return t
        return None

    def in_rotation_duty(self, emp, d):
        if not emp.get('backup_id') or not emp.get('rotation_start'):
            return None
        try:
            start = datetime.strptime(emp['rotation_start'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None
        n = int(emp.get('rotation_days') or 10)
        if n < 1:
            n = 1
        elapsed = (d - start).days
        if elapsed < 0:
            return None
        return ((elapsed // n) % 2) == (emp.get('rotation_order') or 0)

    def status(self, emp, d):
        lv = self.on_leave(emp['id'], d)

        # الإجازة لها الأولوية المطلقة: يوم الإجازة يُحسب إجازة دائماً
        # ولا يُحسب ضمن أيام الدوام — أي أنه يُقصّ من رصيد الدوام
        if lv:
            return LEAVE, lv

        if emp['shift_type'] == 'صباحي':
            if d.weekday() in (4, 5):
                return WEEKEND, lv
            if d.strftime('%Y-%m-%d') in self.holidays:
                return HOLIDAY, lv
            return DUTY, lv

        rot = self.in_rotation_duty(emp, d)
        if rot is None:
            if d.weekday() in (4, 5):
                return WEEKEND, lv
            return DUTY, lv
        return (DUTY if rot else OFF), lv

    def month_rows(self, emp, year, month):
        rows = []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            d = date(year, month, day)
            st, lv = self.status(emp, d)
            hol = self.holidays.get(d.strftime('%Y-%m-%d'))
            if lv:
                detail = lv
            elif hol and emp['shift_type'] == 'مسائي' and st == DUTY:
                detail = "%s — الخفر غير مشمول بالعطل" % hol['holiday_name']
            elif hol:
                detail = hol['holiday_name']
            else:
                detail = '—'
            rows.append({'date': d, 'day_name': AR_DAYS[d.weekday()], 'status': st,
                         'detail': detail})
        return rows

    def monthly_breakdown(self, emp, start, end):
        """إحصاء مفصّل شهراً بشهر ضمن المدة"""
        out = []
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            last = calendar.monthrange(y, m)[1]
            s = max(start, date(y, m, 1))
            e = min(end, date(y, m, last))
            out.append(((y, m), self.summary(emp, s, e)))
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return out

    def summary(self, emp, start, end):
        """
        إحصاء المدة. المفاتيح:
          SCHED = الدوام المقرر (الأيام التي كان مفروضاً أن يداومها)
          DUTY  = صافي الدوام الفعلي بعد خصم أيام الإجازة
          LEAVE = أيام الإجازة المخصومة من الدوام
        دائماً:  SCHED = DUTY + LEAVE
        """
        counts = {DUTY: 0, OFF: 0, LEAVE: 0, HOLIDAY: 0, WEEKEND: 0, SCHED: 0}
        d = start
        while d <= end:
            st, _ = self.status(emp, d)
            counts[st] = counts.get(st, 0) + 1
            if st in (DUTY, LEAVE):
                counts[SCHED] += 1          # يوم مقرر للدوام — الإجازة تُقتطع منه
            d += timedelta(days=1)
        return counts

