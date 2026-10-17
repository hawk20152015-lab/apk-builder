# -*- coding: utf-8 -*-
"""نقطة البدء — تشغّل الخادم، وإن فشل التشغيل تعرض سبب الخطأ على الشاشة بدل إغلاق التطبيق.
تطوير وتصميم عمر كريم"""
import os
import traceback

PORT = int(os.environ.get('PORT', 5000))

try:
    import server
except Exception:
    err = traceback.format_exc()
    try:
        with open(os.path.join(os.environ.get('ANDROID_PRIVATE') or '.', 'startup_error.txt'),
                  'w', encoding='utf-8') as f:
            f.write(err)
    except Exception:
        pass
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from html import escape

    class ErrorPage(BaseHTTPRequestHandler):
        def do_GET(self):
            body = ('<!doctype html><html dir="rtl"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<body style="font-family:sans-serif;padding:16px;background:#fff1f2">'
                    '<h2 style="color:#be123c">تعذّر تشغيل التطبيق</h2>'
                    '<p>صوّر هذه الشاشة وأرسلها للمطوّر.</p>'
                    '<pre dir="ltr" style="white-space:pre-wrap;font-size:12px;background:#fff;'
                    'padding:12px;border-radius:8px">%s</pre></body></html>' % escape(err))
            data = body.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    HTTPServer(('127.0.0.1', PORT), ErrorPage).serve_forever()
else:
    server.run()
