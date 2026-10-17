[app]
title = أرشيف الكتب
package.name = bookarchive
package.domain = org.omar
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
source.exclude_dirs = signing,.github,bin,.buildozer
version = 1.3

icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png
android.presplash_color = #7C3AED

requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,sqlite3,arabic_reshaper,python-bidi==0.4.2,six,androidstorage4kivy

orientation = portrait
fullscreen = 0

android.permissions = READ_EXTERNAL_STORAGE, READ_MEDIA_IMAGES
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
