# -*- coding: utf-8 -*-
"""
نظام إدارة الاجازات والدوام — نسخة أندرويد
خادم محلي داخل الهاتف + واجهة ويب (webview bootstrap).
المنطق (core.py) منقول حرفياً من النسخة المكتبية.
تطوير وتصميم عمر كريم
"""
import os
import calendar
from datetime import datetime, date

from flask import Flask, jsonify, request, send_file

import core
from core import (DB, Scheduler, DUTY, OFF, LEAVE, HOLIDAY, WEEKEND, SCHED,
                  SYSTEM_START, DEV_MARK)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('ANDROID_PRIVATE') or HERE
db = DB(os.path.join(DATA_DIR, 'leave_management.db'))
sch = Scheduler(db)
app = Flask(__name__)


def ok(**kw):
    kw.setdefault('ok', True)
    return jsonify(kw)


def err(msg):
    return jsonify(ok=False, error=msg)


def body():
    return request.get_json(silent=True) or {}


def valid_date(s):
    try:
        datetime.strptime(s or '', '%Y-%m-%d')
        return True
    except ValueError:
        return False


def pdate(s):
    return datetime.strptime(s, '%Y-%m-%d').date()


@app.after_request
def no_cache(r):
    r.headers['Cache-Control'] = 'no-store'
    return r


@app.route('/')
def index():
    return send_file(os.path.join(HERE, 'index.html'))


# ---------------------------------------------------------- الرمز السري
@app.post('/api/login')
def login():
    return ok(ok=db.check_pin(str(body().get('pin', '')).strip()))


@app.post('/api/pin')
def change_pin():
    b = body()
    if not db.check_pin(str(b.get('old', '')).strip()):
        return err('الرمز الحالي غير صحيح')
    n = str(b.get('new', '')).strip()
    if len(n) < 4:
        return err('الرمز الجديد يجب ألا يقل عن 4 خانات')
    if n != str(b.get('confirm', '')).strip():
        return err('الرمز الجديد وتأكيده غير متطابقين')
    db.set_pin(n)
    return ok(msg='تم تغيير الرمز السري بنجاح')


# ---------------------------------------------------------- الحالة العامة
@app.get('/api/state')
def state():
    sch.reload()
    emps = db.employees()
    by_id = {e['id']: e for e in emps}
    today = date.today()
    rotation = []
    for e in emps:
        if e['shift_type'] != 'مسائي':
            continue
        b = by_id.get(e.get('backup_id'))
        rotation.append({
            'id': e['id'], 'name': e['name'],
            'backup': b['name'] if b else None,
            'days': e.get('rotation_days') if b else None,
            'start': e.get('rotation_start') if b else None,
            'status': sch.status(e, today)[0],
            'backup_status': sch.status(b, today)[0] if b else None,
        })
    leaves = [dict(l, days=int(l['days'] or 0)) for l in db.leaves()]
    return ok(employees=emps, rotation=rotation, leaves=leaves,
              holidays=db.holidays(), system_start=SYSTEM_START.isoformat(),
              today=today.isoformat(), dev=DEV_MARK)


# ---------------------------------------------------------- الموظفون
@app.post('/api/employee')
def save_employee():
    b = body()
    name, pos = (b.get('name') or '').strip(), (b.get('position') or '').strip()
    shift, hire = b.get('shift') or 'صباحي', b.get('hire_date') or ''
    if not name or not pos:
        return err('الرجاء إدخال الاسم والمنصب')
    if not valid_date(hire):
        return err('صيغة تاريخ المباشرة غير صحيحة')
    eid = b.get('id')
    good = (db.update_employee(eid, name, pos, shift, hire) if eid
            else db.add_employee(name, pos, shift, hire))
    if not good:
        return err('يوجد موظف بنفس الاسم')
    return ok(msg='تم تحديث البيانات' if eid else 'تمت إضافة الموظف')


@app.post('/api/employee/<int:eid>/delete')
def delete_employee(eid):
    db.delete_employee(eid)
    return ok(msg='تم حذف الموظف')


# ---------------------------------------------------------- وجبات الخفر
def _rot_args(b):
    try:
        days = int(b.get('days') or 10)
    except (TypeError, ValueError):
        days = 10
    return max(1, min(90, days)), b.get('start') or ''


@app.post('/api/link')
def link():
    b = body()
    a, c = b.get('first'), b.get('second')
    if not a or not c:
        return err('اختر الخفر الأول والثاني')
    if a == c:
        return err('لا يمكن ربط الموظف بنفسه')
    ea, eb = db.employee(a), db.employee(c)
    if not ea or not eb or ea['shift_type'] != 'مسائي' or eb['shift_type'] != 'مسائي':
        return err('الوجبات متاحة للخفر (المسائي) فقط')
    days, start = _rot_args(b)
    if not valid_date(start):
        return err('صيغة تاريخ البدء غير صحيحة')
    db.link_pair(a, c, days, start)
    return ok(msg='وجبة %d يوماً — يبدأ %s ثم ينزل ويداوم %s' % (days, ea['name'], eb['name']))


@app.post('/api/rotation/<int:eid>/<action>')
def rotation_action(eid, action):
    if action == 'unlink':
        db.unlink(eid)
        return ok(msg='تم فك الارتباط')
    if action == 'flip':
        if db.flip_pair(eid):
            return ok(msg='تم عكس ترتيب الوجبة بين الخفرين')
        return err('هذا الخفر غير مرتبط بوجبة')
    if action == 'edit':
        days, start = _rot_args(body())
        if not valid_date(start):
            return err('صيغة تاريخ البدء غير صحيحة')
        db.set_rotation(eid, days, start)
        return ok(msg='تم تعديل الوجبة')
    return err('إجراء غير معروف')


# ---------------------------------------------------------- الإجازات
@app.post('/api/leave')
def save_leave():
    b = body()
    eid = b.get('employee_id')
    if not eid:
        return err('اختر الموظف')
    s, e = b.get('start') or '', b.get('end') or ''
    if not valid_date(s) or not valid_date(e):
        return err('صيغة التاريخ غير صحيحة')
    ltype, notes = b.get('type') or 'إجازة اعتيادية', (b.get('notes') or '').strip()
    lid = b.get('id')
    good = (db.update_leave(lid, eid, ltype, s, e, notes) if lid
            else db.add_leave(eid, ltype, s, e, notes))
    if not good:
        return err('تاريخ النهاية قبل تاريخ البداية')
    return ok(msg='تم حفظ التعديل' if lid else 'تم تسجيل الإجازة')


@app.post('/api/leave/<int:lid>/delete')
def delete_leave(lid):
    db.delete_leave(lid)
    return ok(msg='تم حذف الإجازة')


# ---------------------------------------------------------- العطل
@app.post('/api/holiday')
def save_holiday():
    b = body()
    d, name = b.get('date') or '', (b.get('name') or '').strip()
    if not name:
        return err('أدخل اسم العطلة')
    if not valid_date(d):
        return err('صيغة التاريخ غير صحيحة')
    if not db.add_holiday(d, name, b.get('type') or 'رسمي'):
        return err('هذا التاريخ مسجّل مسبقاً')
    return ok(msg='تمت إضافة العطلة')


@app.post('/api/holiday/<int:hid>/delete')
def delete_holiday(hid):
    db.delete_holiday(hid)
    return ok(msg='تم حذف العطلة')


@app.post('/api/holidays/clear')
def clear_holidays():
    db.clear_holidays()
    return ok(msg='تم حذف جميع العطل')


# ---------------------------------------------------------- جدول الدوام
@app.get('/api/schedule')
def schedule():
    emp = db.employee(request.args.get('emp', type=int) or 0)
    if not emp:
        return err('اختر الموظف')
    y, m = request.args.get('y', type=int), request.args.get('m', type=int)
    if not y or not m or not 1 <= m <= 12:
        return err('السنة والشهر غير صحيحين')
    sch.reload()
    rows, counts = [], {}
    for r in sch.month_rows(emp, y, m):
        counts[r['status']] = counts.get(r['status'], 0) + 1
        rows.append({'date': r['date'].isoformat(), 'day_name': r['day_name'],
                     'weekday': r['date'].weekday(), 'status': r['status'],
                     'detail': r['detail']})
    return ok(emp={'name': emp['name'], 'shift': emp['shift_type']}, rows=rows,
              first_weekday=calendar.monthrange(y, m)[0],
              summary={'sched': counts.get(DUTY, 0) + counts.get(LEAVE, 0),
                       'leave': counts.get(LEAVE, 0), 'duty': counts.get(DUTY, 0),
                       'off': counts.get(OFF, 0), 'holiday': counts.get(HOLIDAY, 0),
                       'weekend': counts.get(WEEKEND, 0)})


# ---------------------------------------------------------- التقارير
def _leaves_in(emp_id, s, e):
    out = []
    for l in db.leaves_of(emp_id):
        try:
            ls, le = pdate(l['start_date']), pdate(l['end_date'])
        except (ValueError, TypeError):
            continue
        if le < s or ls > e:
            continue
        out.append({'type': l['leave_type'], 'start': l['start_date'], 'end': l['end_date'],
                    'days': (min(le, e) - max(ls, s)).days + 1, 'notes': l['notes'] or ''})
    return out


def _stats(c, count):
    return {'sched': c.get(SCHED, 0), 'leave': c.get(LEAVE, 0), 'duty': c.get(DUTY, 0),
            'off': c.get(OFF, 0), 'count': count,
            'hol': c.get(HOLIDAY, 0) + c.get(WEEKEND, 0)}


@app.get('/api/report')
def report():
    try:
        s, e = pdate(request.args.get('from', '')), pdate(request.args.get('to', ''))
    except ValueError:
        return err('صيغة التاريخ غير صحيحة')
    if e < s:
        return err('تاريخ النهاية قبل تاريخ البداية')
    if (e - s).days > 3660:
        return err('المدة طويلة جداً — اختر مدة أقصر')
    sch.reload()
    eid = request.args.get('emp', type=int)
    if not eid:
        emps = db.employees()
        if not emps:
            return err('لا يوجد موظفون مسجّلون')
        by_id = {x['id']: x for x in emps}
        rows, tot, tot_cnt = [], {}, 0
        for emp in emps:
            c = sch.summary(emp, s, e)
            n = len(_leaves_in(emp['id'], s, e))
            tot_cnt += n
            for k, v in c.items():
                tot[k] = tot.get(k, 0) + v
            b = by_id.get(emp.get('backup_id'))
            rows.append(dict(_stats(c, n), name=emp['name'], shift=emp['shift_type'],
                             backup=b['name'] if b else None))
        return ok(mode='all', stats=_stats(tot, tot_cnt), rows=rows)
    emp = db.employee(eid)
    if not emp:
        return err('الموظف غير موجود')
    lv = _leaves_in(eid, s, e)
    months = [dict(_stats(c, 0), month='%04d-%02d' % (y, m))
              for (y, m), c in sch.monthly_breakdown(emp, s, e)]
    return ok(mode='one', stats=_stats(sch.summary(emp, s, e), len(lv)),
              leaves=lv, months=months, name=emp['name'])


if __name__ == '__main__':
    # خيط واحد لأن اتصال SQLite مشترك
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5000)),
            debug=False, use_reloader=False, threaded=False)
