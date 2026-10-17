# -*- coding: utf-8 -*-
"""
الصندوق — طبقة البيانات والحسابات
متوافقة مع قواعد بيانات النسخ السابقة (نفس الجداول والأعمدة) مع ترقية تلقائية.
تطوير عمر كريم
"""
import hashlib
import re
import sqlite3
from datetime import datetime, date

DEV_MARK = "تطوير عمر كريم"
DEFAULT_PIN = "1234"
TRANSFERRED = "المنقولون إلى الخارج"      # شعبة دائمة للأفراد المنقولين
UNSORTED = "غير مصنّف"

# أنواع الحركات
ADD, NATH, SPEND = 'add', 'nathriya', 'spend'
KIND_LABEL = {ADD: 'إضافة', NATH: 'خصم للنثرية', SPEND: 'صرف'}
KINDS = (ADD, NATH, SPEND)

_AR_NORM = [
    (re.compile('[ً-ْٰـ]'), ''),   # التشكيل والتطويل
    (re.compile('[إأآٱ]'), 'ا'),
    (re.compile('ى'), 'ي'),
    (re.compile('ة'), 'ه'),
    (re.compile('ؤ'), 'و'),
    (re.compile('ئ'), 'ي'),
]
_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def norm(s):
    """توحيد النص العربي للبحث: يتجاهل الهمزات والتاء المربوطة والتشكيل والأرقام الهندية."""
    s = str(s or '').strip().lower().translate(_DIGITS)
    for rx, rep in _AR_NORM:
        s = rx.sub(rep, s)
    return re.sub(r'\s+', ' ', s)


def now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M')


def signed(kind, amount):
    """المبلغ بالإشارة الصحيحة حسب نوع الحركة."""
    a = abs(float(amount))
    return a if kind == ADD else -a


class DB:
    def __init__(self, path):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.create_function('NORM', 1, norm)
        self._create()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------ المخطط
    def _create(self):
        c = self.conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS divisions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_amount REAL DEFAULT 0,
            donation REAL DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS members(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            division_id INTEGER,
            balance REAL DEFAULT 0,
            phone TEXT DEFAULT '',
            mastercard TEXT DEFAULT '',
            FOREIGN KEY(division_id) REFERENCES divisions(id) ON DELETE CASCADE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER,
            amount REAL,
            note TEXT,
            created_at TEXT,
            FOREIGN KEY(member_id) REFERENCES members(id) ON DELETE CASCADE)""")
        c.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL,
            note TEXT,
            created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY, value TEXT)""")
        # ترقية القواعد القديمة
        self._ensure_column(c, "members", "phone", "TEXT DEFAULT ''")
        self._ensure_column(c, "members", "mastercard", "TEXT DEFAULT ''")
        self._ensure_column(c, "members", "notes", "TEXT DEFAULT ''")
        self._ensure_column(c, "members", "created_at", "TEXT")
        self._ensure_column(c, "divisions", "base_amount", "REAL DEFAULT 0")
        self._ensure_column(c, "divisions", "donation", "REAL DEFAULT 0")
        self._ensure_column(c, "divisions", "is_system", "INTEGER DEFAULT 0")
        self._ensure_column(c, "transactions", "kind", "TEXT")
        # الحركات القديمة بلا نوع: الموجب إضافة، السالب خصم للنثرية (كما كان سابقاً)
        c.execute("UPDATE transactions SET kind='add' WHERE kind IS NULL AND amount>=0")
        c.execute("UPDATE transactions SET kind='nathriya' WHERE kind IS NULL AND amount<0")
        # شعبة المنقولين الدائمة
        c.execute("INSERT OR IGNORE INTO divisions(name, is_system) VALUES(?, 1)", (TRANSFERRED,))
        c.execute("UPDATE divisions SET is_system=1 WHERE name=?", (TRANSFERRED,))
        c.execute("CREATE INDEX IF NOT EXISTS ix_tx_member ON transactions(member_id)")
        c.execute("CREATE INDEX IF NOT EXISTS ix_mem_div ON members(division_id)")
        self.conn.commit()
        self.recalc_balances()

    @staticmethod
    def _ensure_column(c, table, col, decl):
        cols = [r[1] for r in c.execute("PRAGMA table_info(%s)" % table).fetchall()]
        if col not in cols:
            c.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))

    def recalc_balances(self):
        """الرصيد = مجموع الحركات — يُعاد حسابه لضمان الدقة."""
        self.conn.execute("""UPDATE members SET balance = COALESCE(
            (SELECT SUM(amount) FROM transactions t WHERE t.member_id = members.id), 0)""")
        self.conn.commit()

    # ------------------------------------------------------------ الرمز السري
    @staticmethod
    def _hash(pin):
        return hashlib.sha256(("omar-karim-fund::" + str(pin)).encode('utf-8')).hexdigest()

    def get_setting(self, key, default=None):
        r = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r['value'] if r else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT INTO settings(key, value) VALUES(?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    def check_pin(self, pin):
        stored = self.get_setting('pin')
        return str(pin) == DEFAULT_PIN if not stored else stored == self._hash(pin)

    def set_pin(self, pin):
        self.set_setting('pin', self._hash(pin))

    # ------------------------------------------------------------ الشُّعب
    def add_division(self, name):
        try:
            cur = self.conn.execute("INSERT INTO divisions(name) VALUES(?)", (name,))
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def division_id_by_name(self, name, create=True):
        r = self.conn.execute("SELECT id FROM divisions WHERE name=?", (name,)).fetchone()
        if r:
            return r['id']
        return self.add_division(name) if create else None

    def update_division(self, did, name, base_amount, donation):
        try:
            self.conn.execute("UPDATE divisions SET name=?, base_amount=?, donation=? "
                              "WHERE id=? AND COALESCE(is_system,0)=0",
                              (name, base_amount, donation, did))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_division(self, did):
        self.conn.execute("DELETE FROM divisions WHERE id=? AND COALESCE(is_system,0)=0", (did,))
        self.conn.commit()

    def divisions(self):
        rows = self.conn.execute("""
            SELECT d.id, d.name, COALESCE(d.base_amount,0) AS base_amount,
                   COALESCE(d.donation,0) AS donation, COALESCE(d.is_system,0) AS is_system,
                   (SELECT COUNT(*) FROM members m WHERE m.division_id=d.id) AS cnt,
                   (SELECT COALESCE(SUM(m.balance),0) FROM members m WHERE m.division_id=d.id) AS total,
                   (SELECT COALESCE(SUM(-t.amount),0) FROM transactions t JOIN members m ON m.id=t.member_id
                     WHERE m.division_id=d.id AND t.kind='nathriya') AS nathriya,
                   (SELECT COALESCE(SUM(-t.amount),0) FROM transactions t JOIN members m ON m.id=t.member_id
                     WHERE m.division_id=d.id AND t.kind='spend') AS spent,
                   (SELECT COALESCE(SUM(t.amount),0) FROM transactions t JOIN members m ON m.id=t.member_id
                     WHERE m.division_id=d.id AND t.kind='add') AS added
            FROM divisions d
            ORDER BY COALESCE(d.is_system,0), d.name""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['net'] = d['base_amount'] - d['nathriya'] - d['donation']
            out.append(d)
        return out

    def division(self, did):
        for d in self.divisions():
            if d['id'] == did:
                return d
        return None

    # ------------------------------------------------------------ الأفراد
    def add_member(self, name, division_id, phone='', mastercard='', notes=''):
        cur = self.conn.execute(
            "INSERT INTO members(name, division_id, balance, phone, mastercard, notes, created_at) "
            "VALUES(?,?,0,?,?,?,?)", (name, division_id, phone, mastercard, notes, now_str()))
        self.conn.commit()
        return cur.lastrowid

    def update_member(self, mid, name, phone, mastercard, notes=''):
        self.conn.execute("UPDATE members SET name=?, phone=?, mastercard=?, notes=? WHERE id=?",
                          (name, phone, mastercard, notes, mid))
        self.conn.commit()

    def delete_member(self, mid):
        self.conn.execute("DELETE FROM transactions WHERE member_id=?", (mid,))
        self.conn.execute("DELETE FROM members WHERE id=?", (mid,))
        self.conn.commit()

    def move_members(self, ids, new_division_id):
        self.conn.executemany("UPDATE members SET division_id=? WHERE id=?",
                              [(new_division_id, i) for i in ids])
        self.conn.commit()

    def members(self, division_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM members WHERE division_id=? ORDER BY name", (division_id,)).fetchall()]

    def member(self, mid):
        r = self.conn.execute("""SELECT m.*, d.name AS division_name FROM members m
                                 LEFT JOIN divisions d ON d.id=m.division_id WHERE m.id=?""",
                              (mid,)).fetchone()
        return dict(r) if r else None

    def member_totals(self, mid):
        r = self.conn.execute("""SELECT
            COALESCE(SUM(CASE WHEN kind='add' THEN amount END),0) AS added,
            COALESCE(SUM(CASE WHEN kind='nathriya' THEN -amount END),0) AS nathriya,
            COALESCE(SUM(CASE WHEN kind='spend' THEN -amount END),0) AS spent,
            COUNT(*) AS n FROM transactions WHERE member_id=?""", (mid,)).fetchone()
        return dict(r)

    def search_members(self, q, limit=80):
        nq = norm(q)
        if not nq:
            return []
        like = '%' + nq + '%'
        rows = self.conn.execute("""SELECT m.*, d.name AS division_name FROM members m
            LEFT JOIN divisions d ON d.id=m.division_id
            WHERE NORM(m.name) LIKE ? OR NORM(m.phone) LIKE ? OR NORM(m.mastercard) LIKE ?
               OR NORM(m.notes) LIKE ?
            ORDER BY m.name LIMIT ?""", (like, like, like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ الحركات
    def add_transaction(self, member_id, kind, amount, note='', when=None):
        if kind not in KINDS:
            raise ValueError('kind')
        amt = signed(kind, amount)
        self.conn.execute("INSERT INTO transactions(member_id, amount, note, created_at, kind) "
                          "VALUES(?,?,?,?,?)", (member_id, amt, note, when or now_str(), kind))
        self.conn.execute("UPDATE members SET balance = balance + ? WHERE id=?", (amt, member_id))

    def bulk_transaction(self, member_ids, kind, amount, note=''):
        when = now_str()
        for mid in member_ids:
            self.add_transaction(mid, kind, amount, note, when)
        self.conn.commit()
        return len(member_ids)

    def delete_transaction(self, tid):
        r = self.conn.execute("SELECT member_id, amount FROM transactions WHERE id=?", (tid,)).fetchone()
        if not r:
            return False
        self.conn.execute("DELETE FROM transactions WHERE id=?", (tid,))
        self.conn.execute("UPDATE members SET balance = balance - ? WHERE id=?",
                          (r['amount'], r['member_id']))
        self.conn.commit()
        return True

    def transactions(self, member_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM transactions WHERE member_id=? ORDER BY created_at DESC, id DESC",
            (member_id,)).fetchall()]

    def ledger(self, kind=None, division_id=None, date_from=None, date_to=None,
               q=None, limit=400):
        """السجل العام لكل الحركات + سحوبات النثرية."""
        where, args = [], []
        if kind and kind != 'withdraw':
            where.append("t.kind=?"); args.append(kind)
        if division_id:
            where.append("m.division_id=?"); args.append(division_id)
        if date_from:
            where.append("substr(t.created_at,1,10)>=?"); args.append(date_from)
        if date_to:
            where.append("substr(t.created_at,1,10)<=?"); args.append(date_to)
        if q:
            where.append("(NORM(m.name) LIKE ? OR NORM(t.note) LIKE ?)")
            args += ['%' + norm(q) + '%'] * 2
        rows = []
        if kind != 'withdraw':
            sql = ("SELECT t.id, t.amount, t.note, t.created_at, t.kind, m.id AS member_id, "
                   "m.name AS member_name, d.name AS division_name FROM transactions t "
                   "JOIN members m ON m.id=t.member_id LEFT JOIN divisions d ON d.id=m.division_id")
            if where:
                sql += " WHERE " + " AND ".join(where)
            rows = [dict(r) for r in self.conn.execute(
                sql + " ORDER BY t.created_at DESC, t.id DESC LIMIT ?", args + [limit]).fetchall()]
        if (not kind or kind == 'withdraw') and not division_id:
            w, a = [], []
            if date_from:
                w.append("substr(created_at,1,10)>=?"); a.append(date_from)
            if date_to:
                w.append("substr(created_at,1,10)<=?"); a.append(date_to)
            if q:
                w.append("NORM(note) LIKE ?"); a.append('%' + norm(q) + '%')
            sql = "SELECT id, -amount AS amount, note, created_at FROM withdrawals"
            if w:
                sql += " WHERE " + " AND ".join(w)
            for r in self.conn.execute(sql + " ORDER BY created_at DESC LIMIT ?", a + [limit]):
                d = dict(r)
                d.update(kind='withdraw', member_id=None, member_name='سحب من النثرية',
                         division_name=None)
                rows.append(d)
            rows.sort(key=lambda r: (r['created_at'] or '', r['id']), reverse=True)
        return rows[:limit]

    # ------------------------------------------------------------ النثرية العامة
    def nathriya_collected(self):
        r = self.conn.execute("SELECT COALESCE(SUM(-amount),0) AS p FROM transactions "
                              "WHERE kind='nathriya'").fetchone()
        return r['p']

    def nathriya_withdrawn(self):
        return self.conn.execute("SELECT COALESCE(SUM(amount),0) AS p FROM withdrawals").fetchone()['p']

    def nathriya_available(self):
        return self.nathriya_collected() - self.nathriya_withdrawn()

    def add_withdrawal(self, amount, note=''):
        self.conn.execute("INSERT INTO withdrawals(amount, note, created_at) VALUES(?,?,?)",
                          (abs(float(amount)), note, now_str()))
        self.conn.commit()

    def delete_withdrawal(self, wid):
        self.conn.execute("DELETE FROM withdrawals WHERE id=?", (wid,))
        self.conn.commit()

    def withdrawals(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM withdrawals ORDER BY created_at DESC, id DESC").fetchall()]

    # ------------------------------------------------------------ الإحصائيات
    def overview(self):
        r = self.conn.execute("""SELECT
            (SELECT COUNT(*) FROM members) AS members,
            (SELECT COUNT(*) FROM divisions WHERE COALESCE(is_system,0)=0) AS divisions,
            (SELECT COALESCE(SUM(balance),0) FROM members) AS balance,
            (SELECT COALESCE(SUM(amount),0) FROM transactions WHERE kind='add') AS added,
            (SELECT COALESCE(SUM(-amount),0) FROM transactions WHERE kind='spend') AS spent,
            (SELECT COUNT(*) FROM transactions) AS tx""").fetchone()
        d = dict(r)
        d['nathriya_collected'] = self.nathriya_collected()
        d['nathriya_withdrawn'] = self.nathriya_withdrawn()
        d['nathriya'] = d['nathriya_collected'] - d['nathriya_withdrawn']
        d['base'] = sum(x['base_amount'] for x in self.divisions())
        d['donation'] = sum(x['donation'] for x in self.divisions())
        return d

    def monthly(self, months=6):
        """مجاميع آخر عدة أشهر لكل نوع."""
        today = date.today()
        keys = []
        y, m = today.year, today.month
        for _ in range(months):
            keys.append('%04d-%02d' % (y, m))
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        keys.reverse()
        data = {k: {'month': k, ADD: 0, NATH: 0, SPEND: 0, 'withdraw': 0} for k in keys}
        for r in self.conn.execute("""SELECT substr(created_at,1,7) AS mo, kind, SUM(ABS(amount)) AS s
                                      FROM transactions WHERE substr(created_at,1,7)>=?
                                      GROUP BY mo, kind""", (keys[0],)):
            if r['mo'] in data and r['kind'] in data[r['mo']]:
                data[r['mo']][r['kind']] = r['s'] or 0
        for r in self.conn.execute("""SELECT substr(created_at,1,7) AS mo, SUM(amount) AS s
                                      FROM withdrawals WHERE substr(created_at,1,7)>=? GROUP BY mo""",
                                   (keys[0],)):
            if r['mo'] in data:
                data[r['mo']]['withdraw'] = r['s'] or 0
        return [data[k] for k in keys]

    def period_report(self, date_from, date_to):
        """تقرير مدة: مجاميع كل شعبة حسب نوع الحركة."""
        rows = self.conn.execute("""SELECT d.id, d.name,
              COALESCE(SUM(CASE WHEN t.kind='add' THEN t.amount END),0) AS added,
              COALESCE(SUM(CASE WHEN t.kind='nathriya' THEN -t.amount END),0) AS nathriya,
              COALESCE(SUM(CASE WHEN t.kind='spend' THEN -t.amount END),0) AS spent,
              COUNT(t.id) AS n
            FROM divisions d
            LEFT JOIN members m ON m.division_id=d.id
            LEFT JOIN transactions t ON t.member_id=m.id
                 AND substr(t.created_at,1,10) BETWEEN ? AND ?
            GROUP BY d.id ORDER BY COALESCE(d.is_system,0), d.name""",
                                 (date_from, date_to)).fetchall()
        out = [dict(r) for r in rows]
        wd = self.conn.execute("""SELECT COALESCE(SUM(amount),0) AS s FROM withdrawals
                                  WHERE substr(created_at,1,10) BETWEEN ? AND ?""",
                               (date_from, date_to)).fetchone()['s']
        tot = {k: sum(r[k] for r in out) for k in ('added', 'nathriya', 'spent', 'n')}
        tot['withdrawn'] = wd
        return out, tot

    def top_members(self, n=5):
        best = [dict(r) for r in self.conn.execute(
            """SELECT m.id, m.name, m.balance, d.name AS division_name FROM members m
               LEFT JOIN divisions d ON d.id=m.division_id ORDER BY m.balance DESC LIMIT ?""", (n,))]
        return best
