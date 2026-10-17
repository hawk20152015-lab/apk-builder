# -*- coding: utf-8 -*-
"""SQLite storage for the personal budget app."""
import sqlite3


def month_key(year, month):
    return "%04d-%02d" % (year, month)


def shift_month(year, month, delta):
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


class BudgetDB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create()

    def _create(self):
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS income(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                note TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS loans(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                total REAL NOT NULL,
                installment REAL NOT NULL,
                start_date TEXT NOT NULL,
                note TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS loan_payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
                amount REAL NOT NULL,
                date TEXT NOT NULL);
            """
        )
        c.commit()

    # ---------------- income ----------------
    def add_income(self, source, amount, date, note=""):
        self.conn.execute(
            "INSERT INTO income(source, amount, date, note) VALUES(?,?,?,?)",
            (source, float(amount), date, note))
        self.conn.commit()

    def list_income(self, mk):
        return self.conn.execute(
            "SELECT * FROM income WHERE substr(date,1,7)=? "
            "ORDER BY date DESC, id DESC", (mk,)).fetchall()

    def delete_income(self, row_id):
        self.conn.execute("DELETE FROM income WHERE id=?", (row_id,))
        self.conn.commit()

    # ---------------- expenses ----------------
    def add_expense(self, category, amount, date, note=""):
        self.conn.execute(
            "INSERT INTO expenses(category, amount, date, note) VALUES(?,?,?,?)",
            (category, float(amount), date, note))
        self.conn.commit()

    def list_expenses(self, mk):
        return self.conn.execute(
            "SELECT * FROM expenses WHERE substr(date,1,7)=? "
            "ORDER BY date DESC, id DESC", (mk,)).fetchall()

    def delete_expense(self, row_id):
        self.conn.execute("DELETE FROM expenses WHERE id=?", (row_id,))
        self.conn.commit()

    def expenses_by_category(self, mk):
        return self.conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE substr(date,1,7)=? GROUP BY category ORDER BY total DESC",
            (mk,)).fetchall()

    # ---------------- loans ----------------
    def add_loan(self, name, total, installment, start_date, note=""):
        self.conn.execute(
            "INSERT INTO loans(name, total, installment, start_date, note) "
            "VALUES(?,?,?,?,?)",
            (name, float(total), float(installment), start_date, note))
        self.conn.commit()

    def delete_loan(self, loan_id):
        self.conn.execute("DELETE FROM loan_payments WHERE loan_id=?", (loan_id,))
        self.conn.execute("DELETE FROM loans WHERE id=?", (loan_id,))
        self.conn.commit()

    def list_loans(self):
        rows = self.conn.execute(
            "SELECT l.*, IFNULL((SELECT SUM(amount) FROM loan_payments p "
            "WHERE p.loan_id=l.id),0) AS paid FROM loans l ORDER BY l.id"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["remaining"] = max(d["total"] - d["paid"], 0)
            d["closed"] = d["remaining"] <= 0.0001
            if d["installment"] > 0:
                left = d["remaining"] / d["installment"]
                d["left_count"] = int(left) + (1 if left - int(left) > 1e-9 else 0)
            else:
                d["left_count"] = 0
            result.append(d)
        return result

    def add_payment(self, loan_id, amount, date):
        self.conn.execute(
            "INSERT INTO loan_payments(loan_id, amount, date) VALUES(?,?,?)",
            (loan_id, float(amount), date))
        self.conn.commit()

    def list_payments(self, loan_id):
        return self.conn.execute(
            "SELECT * FROM loan_payments WHERE loan_id=? ORDER BY date DESC, id DESC",
            (loan_id,)).fetchall()

    def delete_payment(self, pay_id):
        self.conn.execute("DELETE FROM loan_payments WHERE id=?", (pay_id,))
        self.conn.commit()

    def paid_in_month(self, loan_id, mk):
        r = self.conn.execute(
            "SELECT IFNULL(SUM(amount),0) FROM loan_payments "
            "WHERE loan_id=? AND substr(date,1,7)=?", (loan_id, mk)).fetchone()
        return r[0]

    # ---------------- summaries ----------------
    def _sum(self, table, mk):
        r = self.conn.execute(
            "SELECT IFNULL(SUM(amount),0) FROM %s WHERE substr(date,1,7)=?" % table,
            (mk,)).fetchone()
        return r[0]

    def totals(self, mk):
        inc = self._sum("income", mk)
        exp = self._sum("expenses", mk)
        inst = self._sum("loan_payments", mk)
        return {"income": inc, "expenses": exp, "installments": inst,
                "net": inc - exp - inst}

    def monthly_series(self, year, month, count=6):
        out = []
        for i in range(count - 1, -1, -1):
            y, m = shift_month(year, month, -i)
            t = self.totals(month_key(y, m))
            out.append(("%d/%02d" % (m, y % 100), t["income"],
                        t["expenses"] + t["installments"]))
        return out

    def due_loans(self, mk):
        """Open loans with no payment recorded in this month."""
        return [l for l in self.list_loans()
                if not l["closed"] and l["start_date"][:7] <= mk
                and self.paid_in_month(l["id"], mk) <= 0]
