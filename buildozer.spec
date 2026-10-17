[app]
title = الصندوق
package.name = thefund
package.domain = org.omarkarim
source.dir = .
source.include_exts = py,png,html,ttf
source.exclude_dirs = .git,.github,bin,.buildozer,__pycache__,signing
version = 2.1

requirements = python3,flask==2.0.3,werkzeug==2.0.3,jinja2==3.0.3,itsdangerous==2.0.1,click==8.0.4,markupsafe==2.0.1,pillow,openpyxl,et_xmlfile,arabic_reshaper,python-bidi==0.4.2,pyjnius,android

# واجهة أندرويد تعرض الخادم المحلي
p4a.bootstrap = webview
p4a.port = 5000
p4a.branch = v2024.01.21

icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #0B2545

orientation = portrait
fullscreen = 0
android.permissions = INTERNET, READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 0
