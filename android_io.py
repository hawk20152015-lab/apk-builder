# -*- coding: utf-8 -*-
"""
جسر أندرويد (pyjnius فقط، بدون Kivy):
  • اختيار ملف عبر منتقي النظام (SAF) ونسخه لمجلد التطبيق
  • حفظ ملف في مجلد Documents/الصندوق
  • مشاركة ملف (واتساب، تيليجرام، Drive ...) أو فتحه
  • فتح رابط (واتساب برسالة جاهزة)
على الحاسبة تعمل الدوال كبدائل بسيطة حتى يمكن تجربة التطبيق.
"""
import os
import shutil
import threading

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ or 'ANDROID_PRIVATE' in os.environ
APP_FOLDER = 'الصندوق'
REQ_PICK = 7311
RESULT_OK = -1

MIME = {
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.pdf': 'application/pdf',
    '.zip': 'application/zip',
    '.db': 'application/octet-stream',
}

_lock = threading.Lock()
_pick = {'status': 'idle', 'path': None, 'name': None, 'error': None, 'token': 0}
_bound = False


def _cache_dir():
    d = os.path.join(os.environ.get('ANDROID_PRIVATE') or os.path.dirname(os.path.abspath(__file__)),
                     'io_cache')
    os.makedirs(d, exist_ok=True)
    return d


def _jni():
    from jnius import autoclass, cast
    return autoclass, cast


def _activity():
    autoclass, _ = _jni()
    return autoclass('org.kivy.android.PythonActivity').mActivity


def _ui(fn):
    """تنفيذ على خيط الواجهة في أندرويد."""
    try:
        from android.runnable import run_on_ui_thread
        run_on_ui_thread(fn)()
    except Exception:
        fn()


def _sdk():
    autoclass, _ = _jni()
    return autoclass('android.os.Build$VERSION').SDK_INT


def _copy_streams(jin, jout):
    """نسخ InputStream إلى OutputStream بالكامل داخل جافا (سريع ولا يمر بايثون)."""
    autoclass, _ = _jni()
    Channels = autoclass('java.nio.channels.Channels')
    ByteBuffer = autoclass('java.nio.ByteBuffer')
    rch, wch = Channels.newChannel(jin), Channels.newChannel(jout)
    buf = ByteBuffer.allocateDirect(1 << 16)
    total = 0
    while True:
        n = rch.read(buf)
        if n < 0:
            break
        buf.flip()
        while buf.hasRemaining():
            wch.write(buf)
        buf.clear()
        total += max(n, 0)
    rch.close()
    wch.close()
    return total


# ------------------------------------------------------------------ اختيار ملف
def pick_status():
    with _lock:
        return dict(_pick)


def pick_reset():
    with _lock:
        _pick.update(status='idle', path=None, name=None, error=None)


def start_pick():
    """يفتح منتقي ملفات النظام. النتيجة تُقرأ لاحقاً عبر pick_status()."""
    global _bound
    if not IS_ANDROID:
        raise RuntimeError('desktop')
    autoclass, _ = _jni()
    if not _bound:
        from android import activity
        activity.bind(on_activity_result=_on_result)
        _bound = True
    Intent = autoclass('android.content.Intent')
    with _lock:
        _pick.update(status='waiting', path=None, name=None, error=None,
                     token=_pick['token'] + 1)

    def go():
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType('*/*')
        _activity().startActivityForResult(intent, REQ_PICK)
    _ui(go)


def _display_name(resolver, uri):
    try:
        c = resolver.query(uri, None, None, None, None)
        if c is not None:
            try:
                if c.moveToFirst():
                    i = c.getColumnIndex('_display_name')
                    if i >= 0:
                        return c.getString(i)
            finally:
                c.close()
    except Exception:
        pass
    return None


def _on_result(request_code, result_code, intent):
    if request_code != REQ_PICK:
        return
    if result_code != RESULT_OK or intent is None or intent.getData() is None:
        with _lock:
            _pick.update(status='cancel')
        return
    try:
        autoclass, _ = _jni()
        uri = intent.getData()
        resolver = _activity().getContentResolver()
        name = _display_name(resolver, uri) or 'file'
        safe = ''.join(ch for ch in name if ch not in '\\/:*?"<>|') or 'file'
        dest = os.path.join(_cache_dir(), 'picked_' + safe)
        FileOutputStream = autoclass('java.io.FileOutputStream')
        _copy_streams(resolver.openInputStream(uri), FileOutputStream(dest))
        with _lock:
            _pick.update(status='done', path=dest, name=name)
    except Exception as e:
        with _lock:
            _pick.update(status='error', error=str(e))


# ------------------------------------------------------------------ الحفظ والمشاركة
_saved = {}     # token -> {'uri': java Uri | None, 'path': str, 'name': str, 'mime': str}


def save_to_documents(path, name=None):
    """يحفظ الملف في Documents/الصندوق ويعيد (رمز، مكان الحفظ للعرض)."""
    name = name or os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    mime = MIME.get(ext, 'application/octet-stream')
    token = str(len(_saved) + 1)
    if not IS_ANDROID:
        out_dir = os.path.join(os.path.expanduser('~'), 'Documents', APP_FOLDER)
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, name)
        shutil.copyfile(path, dest)
        _saved[token] = {'uri': None, 'path': dest, 'name': name, 'mime': mime}
        return token, dest
    autoclass, _ = _jni()
    FileInputStream = autoclass('java.io.FileInputStream')
    resolver = _activity().getContentResolver()
    if _sdk() >= 29:
        ContentValues = autoclass('android.content.ContentValues')
        Files = autoclass('android.provider.MediaStore$Files')
        cv = ContentValues()
        cv.put('_display_name', name)
        cv.put('mime_type', mime)
        cv.put('relative_path', 'Documents/' + APP_FOLDER)
        uri = resolver.insert(Files.getContentUri('external'), cv)
        if uri is None:
            raise RuntimeError('MediaStore insert failed')
        _copy_streams(FileInputStream(path), resolver.openOutputStream(uri))
        where = 'Documents/' + APP_FOLDER + '/' + name
    else:
        Environment = autoclass('android.os.Environment')
        base = Environment.getExternalStoragePublicDirectory(
            Environment.DIRECTORY_DOCUMENTS).getAbsolutePath()
        out_dir = os.path.join(base, APP_FOLDER)
        os.makedirs(out_dir, exist_ok=True)
        dest = os.path.join(out_dir, name)
        shutil.copyfile(path, dest)
        Uri = autoclass('android.net.Uri')
        File = autoclass('java.io.File')
        uri = Uri.fromFile(File(dest))
        where = dest
    _saved[token] = {'uri': uri, 'path': path, 'name': name, 'mime': mime}
    return token, where


def _start(intent):
    _ui(lambda: _activity().startActivity(intent))


def share(token, title='مشاركة'):
    item = _saved.get(str(token))
    if not item:
        raise KeyError('token')
    if not IS_ANDROID:
        return item['path']
    autoclass, cast = _jni()
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    intent = Intent(Intent.ACTION_SEND)
    intent.setType(item['mime'])
    intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', item['uri']))
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    _start(Intent.createChooser(intent, cast('java.lang.CharSequence', String(title))))
    return True


def open_file(token):
    item = _saved.get(str(token))
    if not item:
        raise KeyError('token')
    if not IS_ANDROID:
        return item['path']
    autoclass, cast = _jni()
    Intent = autoclass('android.content.Intent')
    String = autoclass('java.lang.String')
    intent = Intent(Intent.ACTION_VIEW)
    intent.setDataAndType(item['uri'], item['mime'])
    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    _start(Intent.createChooser(intent, cast('java.lang.CharSequence', String('فتح الملف'))))
    return True


def open_url(url):
    if not IS_ANDROID:
        import webbrowser
        webbrowser.open(url)
        return True
    autoclass, _ = _jni()
    Intent = autoclass('android.content.Intent')
    Uri = autoclass('android.net.Uri')
    intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    _start(intent)
    return True


def request_storage_permission():
    """أندرويد 9 وأقدم فقط يحتاج إذن الكتابة لحفظ الملفات في Documents."""
    if not IS_ANDROID:
        return
    try:
        if _sdk() < 29:
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.WRITE_EXTERNAL_STORAGE,
                                 Permission.READ_EXTERNAL_STORAGE])
    except Exception:
        pass
