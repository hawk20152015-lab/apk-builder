# -*- coding: utf-8 -*-
"""
الصندوق — الخادم المحلي (Flask 2.0.3) الذي تعرضه واجهة أندرويد.
تطوير عمر كريم
"""
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import date, datetime
from urllib.parse import quote

from flask import Flask, jsonify, request, send_file, abort

import android_io as aio
import core
import reports
from core import DB, KINDS, KIND_LABEL, TRANSFERRED, DEV_MARK

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('ANDROID_PRIVATE') or HERE
DB_PATH = os.path.join(DATA_DIR, 'fund.db')
VERSION = '2.1'

db = DB(DB_PATH)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024
_pick_job = {'purpose': None, 'division_id': None, 'handled_token': 0, 'result': None}


# ====================================================================== أدوات
def ok(**kw):
    kw.setdefault('ok', True)
    return jsonify(kw)


def err(msg):
    return jsonify(ok=False, error=msg)


def body():
    return request.get_json(silent=True) or {}


def num(v, default=0.0):
    try:
        return float(str(v).replace(',', '').replace('٬', '').strip())
    except (TypeError, ValueError):
        return default


def valid_date(s):
    try:
        datetime.strptime(s or '', '%Y-%m-%d')
        return True
    except ValueError:
        return False


def safe_name(s):
    return ''.join(ch for ch in (s or '') if ch not in '\\/:*?"<>|').strip() or 'ملف'


def stamp():
    return datetime.now().strftime('%Y-%m-%d_%H%M')


def out_path(name):
    d = os.path.join(DATA_DIR, 'exports')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def deliver(path, name):
    """يحفظ الملف في Documents/الصندوق ويعيد بياناته للواجهة."""
    token, where = aio.save_to_documents(path, name)
    return ok(token=token, name=name, where=where, android=aio.IS_ANDROID,
              url='/files/%s' % token)


@app.after_request
def no_cache(r):
    r.headers.setdefault('Cache-Control', 'no-store')
    return r


@app.route('/')
def index():
    return send_file(os.path.join(HERE, 'index.html'))


@app.route('/fonts/<name>')
def fonts(name):
    if name not in ('IBMPlexSansArabic-Regular.ttf', 'IBMPlexSansArabic-SemiBold.ttf'):
        abort(404)
    r = send_file(os.path.join(HERE, name), mimetype='font/ttf')
    r.headers['Cache-Control'] = 'max-age=31536000'
    return r


@app.errorhandler(Exception)
def on_error(e):
    code = getattr(e, 'code', 500)
    if isinstance(code, int) and code < 500:
        return jsonify(ok=False, error=str(e)), code
    return jsonify(ok=False, error='خطأ غير متوقع: %s' % e), 200


# ====================================================================== الدخول
@app.post('/api/login')
def login():
    return ok(ok=db.check_pin(str(body().get('pin', '')).strip()))


@app.post('/api/pin')
def change_pin():
    b = body()
    if not db.check_pin(str(b.get('old', '')).strip()):
        return err('الرمز الحالي غير صحيح')
    n = str(b.get('new', '')).strip()
    if len(n) < 4 or not n.isdigit():
        return err('الرمز الجديد يجب أن يكون 4 أرقام على الأقل')
    if n != str(b.get('confirm', '')).strip():
        return err('الرمز الجديد وتأكيده غير متطابقين')
    db.set_pin(n)
    return ok(msg='تم تغيير الرمز السري')


@app.get('/api/info')
def info():
    return ok(dev=DEV_MARK, version=VERSION, android=aio.IS_ANDROID,
              today=date.today().isoformat(), kinds=KIND_LABEL, transferred=TRANSFERRED)


# ====================================================================== الرئيسية
@app.get('/api/overview')
def overview():
    return ok(overview=db.overview(), monthly=db.monthly(6), divisions=db.divisions(),
              top=db.top_members(5), recent=db.ledger(limit=6))


# ====================================================================== الشعب
@app.get('/api/divisions')
def divisions():
    return ok(divisions=db.divisions())


@app.post('/api/division')
def save_division():
    b = body()
    name = (b.get('name') or '').strip()
    if not name:
        return err('اكتب اسم الشعبة')
    base, dona = num(b.get('base_amount')), num(b.get('donation'))
    did = b.get('id')
    if did:
        if not db.update_division(did, name, base, dona):
            return err('يوجد شعبة بنفس الاسم')
        return ok(msg='تم حفظ الشعبة', id=did)
    did = db.add_division(name)
    if not did:
        return err('يوجد شعبة بنفس الاسم')
    if base or dona:
        db.update_division(did, name, base, dona)
    return ok(msg='تمت إضافة الشعبة', id=did)


@app.post('/api/division/<int:did>/delete')
def delete_division(did):
    d = db.division(did)
    if not d:
        return err('الشعبة غير موجودة')
    if d['is_system']:
        return err('لا يمكن حذف هذه الشعبة')
    db.delete_division(did)
    return ok(msg='تم حذف الشعبة وأفرادها')


@app.get('/api/division/<int:did>')
def division(did):
    d = db.division(did)
    if not d:
        return err('الشعبة غير موجودة')
    return ok(division=d, members=db.members(did))


# ====================================================================== الأفراد
@app.post('/api/member')
def save_member():
    b = body()
    name = (b.get('name') or '').strip()
    if not name:
        return err('اكتب اسم الفرد')
    phone, mc, notes = [(b.get(k) or '').strip() for k in ('phone', 'mastercard', 'notes')]
    mid = b.get('id')
    if mid:
        db.update_member(mid, name, phone, mc, notes)
        return ok(msg='تم حفظ البيانات', id=mid)
    did = b.get('division_id')
    if not did:
        return err('اختر الشعبة')
    mid = db.add_member(name, did, phone, mc, notes)
    opening = num(b.get('opening'))
    if opening:
        db.add_transaction(mid, 'add', opening, 'رصيد افتتاحي')
        db.conn.commit()
    return ok(msg='تمت إضافة الفرد', id=mid)


@app.post('/api/member/<int:mid>/delete')
def delete_member(mid):
    db.delete_member(mid)
    return ok(msg='تم حذف الفرد وحركاته')


@app.get('/api/member/<int:mid>')
def member(mid):
    m = db.member(mid)
    if not m:
        return err('الفرد غير موجود')
    return ok(member=m, totals=db.member_totals(mid), transactions=db.transactions(mid))


@app.post('/api/members/move')
def move_members():
    b = body()
    ids = [int(i) for i in b.get('ids') or []]
    did = b.get('division_id')
    if not ids or not did:
        return err('اختر الأفراد والشعبة')
    db.move_members(ids, did)
    return ok(msg='تم نقل %d فرد' % len(ids))


@app.get('/api/search')
def search():
    return ok(results=db.search_members(request.args.get('q', '')))


# ====================================================================== الحركات
@app.post('/api/tx')
def add_tx():
    b = body()
    ids = [int(i) for i in b.get('member_ids') or []]
    kind = b.get('kind')
    amount = num(b.get('amount'))
    if kind not in KINDS:
        return err('اختر نوع الحركة')
    if not ids:
        return err('لم يتم اختيار أي فرد')
    if amount <= 0:
        return err('اكتب مبلغاً صحيحاً')
    n = db.bulk_transaction(ids, kind, amount, (b.get('note') or '').strip())
    return ok(msg='تم تسجيل «%s» لـ %d فرد' % (KIND_LABEL[kind], n))


@app.post('/api/tx/<int:tid>/delete')
def delete_tx(tid):
    if not db.delete_transaction(tid):
        return err('الحركة غير موجودة')
    return ok(msg='تم حذف الحركة وتعديل الرصيد')


@app.post('/api/withdraw')
def withdraw():
    b = body()
    amount = num(b.get('amount'))
    if amount <= 0:
        return err('اكتب مبلغاً صحيحاً')
    avail = db.nathriya_available()
    if amount > avail + 1e-9:
        return err('المبلغ أكبر من النثرية المتاحة (%s)' % reports.money(avail))
    db.add_withdrawal(amount, (b.get('note') or '').strip())
    return ok(msg='تم السحب من النثرية')


@app.post('/api/withdraw/<int:wid>/delete')
def delete_withdraw(wid):
    db.delete_withdrawal(wid)
    return ok(msg='تم حذف السحب')


@app.get('/api/ledger')
def ledger():
    a = request.args
    rows = db.ledger(kind=a.get('kind') or None, division_id=a.get('division', type=int) or None,
                     date_from=a.get('from') or None, date_to=a.get('to') or None,
                     q=a.get('q') or None, limit=a.get('limit', 300, type=int))
    tot = {'add': 0, 'nathriya': 0, 'spend': 0, 'withdraw': 0}
    for r in rows:
        tot[r['kind']] = tot.get(r['kind'], 0) + abs(r['amount'] or 0)
    return ok(rows=rows, totals=tot)


@app.get('/api/report')
def report():
    f, t = request.args.get('from'), request.args.get('to')
    if not valid_date(f) or not valid_date(t):
        return err('صيغة التاريخ غير صحيحة')
    if t < f:
        return err('تاريخ النهاية قبل البداية')
    rows, tot = db.period_report(f, t)
    return ok(rows=rows, totals=tot)


# ====================================================================== واتساب
def wa_phone(p):
    d = ''.join(ch for ch in str(p or '').translate(core._DIGITS) if ch.isdigit())
    if d.startswith('00'):
        d = d[2:]
    if d.startswith('07') and len(d) == 11:
        d = '964' + d[1:]
    elif d.startswith('7') and len(d) == 10:
        d = '964' + d
    return d


@app.post('/api/whatsapp/<int:mid>')
def whatsapp(mid):
    m = db.member(mid)
    if not m:
        return err('الفرد غير موجود')
    text = ('السلام عليكم %s\nرصيدك في الصندوق: %s دينار\n(%s)'
            % (m['name'], reports.money(m['balance']), m.get('division_name') or ''))
    phone = wa_phone(m.get('phone'))
    url = 'https://wa.me/%s?text=%s' % (phone, quote(text))
    aio.open_url(url)
    return ok(url=url)


# ====================================================================== الملفات المُصدَّرة
@app.post('/api/export')
def export():
    b = body()
    what = b.get('what')
    if what == 'member_pdf':
        m = db.member(int(b.get('id') or 0))
        if not m:
            return err('الفرد غير موجود')
        name = 'كشف حساب - %s - %s.pdf' % (safe_name(m['name']), stamp())
        return deliver(reports.member_statement(db, m['id'], out_path(name)), name)
    if what in ('division_pdf', 'division_xlsx'):
        d = db.division(int(b.get('id') or 0))
        if not d:
            return err('الشعبة غير موجودة')
        if what == 'division_pdf':
            name = 'كشف شعبة - %s - %s.pdf' % (safe_name(d['name']), stamp())
            return deliver(reports.division_statement(db, d['id'], out_path(name)), name)
        name = '%s - %s.xlsx' % (safe_name(d['name']), stamp())
        return deliver(reports.export_division_xlsx(db, d['id'], out_path(name)), name)
    if what == 'all_xlsx':
        name = 'الصندوق - كل البيانات - %s.xlsx' % stamp()
        return deliver(reports.export_all_xlsx(db, out_path(name)), name)
    if what == 'template':
        name = 'قالب استيراد الأفراد.xlsx'
        return deliver(reports.template_xlsx(out_path(name)), name)
    if what == 'report_pdf':
        f, t = b.get('from'), b.get('to')
        if not valid_date(f) or not valid_date(t) or t < f:
            return err('اختر مدة صحيحة')
        name = 'تقرير الصندوق %s إلى %s.pdf' % (f, t)
        return deliver(reports.period_report_pdf(db, f, t, out_path(name)), name)
    return err('نوع غير معروف')


@app.post('/api/share/<token>')
def share(token):
    aio.share(token, 'مشاركة الملف')
    return ok()


@app.post('/api/open/<token>')
def open_file(token):
    aio.open_file(token)
    return ok()


@app.get('/files/<token>')
def download(token):
    item = aio._saved.get(token)
    if not item:
        abort(404)
    return send_file(item['path'], as_attachment=True, download_name=item['name'])


# ====================================================================== النسخ الاحتياطي
@app.post('/api/backup')
def backup():
    name = 'نسخة احتياطية - الصندوق - %s.zip' % stamp()
    path = out_path(name)
    snap = out_path('fund_snapshot.db')
    if os.path.exists(snap):
        os.remove(snap)
    dst = sqlite3.connect(snap)
    db.conn.backup(dst)
    dst.close()
    ov = db.overview()
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(snap, 'fund.db')
        z.writestr('meta.json', json.dumps({'app': 'الصندوق', 'version': VERSION,
                                            'created': datetime.now().isoformat(timespec='seconds'),
                                            'members': ov['members'], 'divisions': ov['divisions']},
                                           ensure_ascii=False))
    os.remove(snap)
    return deliver(path, name)


def restore_from(path):
    global db
    work = out_path('restore.db')
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            src = 'fund.db' if 'fund.db' in names else next((n for n in names if n.endswith('.db')), None)
            if not src:
                return False, 'الملف لا يحتوي على نسخة الصندوق'
            with z.open(src) as s, open(work, 'wb') as d:
                shutil.copyfileobj(s, d)
    else:
        shutil.copyfile(path, work)
    try:
        chk = sqlite3.connect(work)
        chk.execute('SELECT COUNT(*) FROM members').fetchone()
        chk.execute('SELECT COUNT(*) FROM divisions').fetchone()
        chk.close()
    except Exception:
        os.remove(work)
        return False, 'الملف ليس قاعدة بيانات صالحة للصندوق'
    db.close()
    if os.path.exists(DB_PATH):
        shutil.copyfile(DB_PATH, DB_PATH + '.before_restore')
    shutil.move(work, DB_PATH)
    db = DB(DB_PATH)
    ov = db.overview()
    return True, 'تمت الاستعادة: %d شعبة و %d فرد' % (ov['divisions'], ov['members'])


# ====================================================================== استقبال الملفات
def handle_file(path, purpose, division_id=None):
    ext = os.path.splitext(path)[1].lower()
    if purpose in ('excel', 'excel_div'):
        if ext not in ('.xlsx', '.xlsm'):
            return {'ok': False, 'error': 'اختر ملف إكسل بصيغة xlsx'}
        try:
            added, skipped = reports.import_xlsx(db, path, division_id if purpose == 'excel_div' else None)
        except Exception as e:
            return {'ok': False, 'error': 'تعذّرت قراءة الملف: %s' % e}
        msg = 'تمت إضافة %d فرد' % added + (' (تخطّي %d)' % skipped if skipped else '')
        return {'ok': True, 'msg': msg}
    if purpose == 'restore':
        good, msg = restore_from(path)
        return {'ok': good, 'msg' if good else 'error': msg}
    return {'ok': False, 'error': 'غرض غير معروف'}


@app.post('/api/upload')
def upload():
    """على الحاسبة: رفع الملف من المتصفح."""
    f = request.files.get('file')
    if not f:
        return err('لم يتم اختيار ملف')
    path = out_path('upload_' + safe_name(f.filename))
    f.save(path)
    try:
        res = handle_file(path, request.form.get('purpose'), request.form.get('division_id', type=int))
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return jsonify(res)


@app.post('/api/pick/start')
def pick_start():
    """على الهاتف: فتح منتقي ملفات أندرويد."""
    b = body()
    _pick_job.update(purpose=b.get('purpose'), division_id=b.get('division_id'), result=None)
    try:
        aio.start_pick()
    except Exception as e:
        return err('تعذّر فتح منتقي الملفات: %s' % e)
    return ok(token=aio.pick_status()['token'])


@app.get('/api/pick/status')
def pick_status():
    st = aio.pick_status()
    if st['status'] == 'done' and _pick_job['handled_token'] != st['token']:
        _pick_job['handled_token'] = st['token']
        try:
            _pick_job['result'] = handle_file(st['path'], _pick_job['purpose'], _pick_job['division_id'])
        finally:
            try:
                os.remove(st['path'])
            except OSError:
                pass
    res = _pick_job['result'] if st['status'] == 'done' else None
    return ok(status=st['status'], error=st['error'], result=res)


def run():
    aio.request_storage_permission()
    # خيط واحد: اتصال SQLite ومنتقي الملفات مشتركان
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5000)),
            debug=False, use_reloader=False, threaded=False)


if __name__ == '__main__':
    run()
