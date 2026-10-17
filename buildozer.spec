[app]
title = ميزانيتي
package.name = mybudget
package.domain = org.omarkarim
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf
version = 1.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,arabic-reshaper,python-bidi==0.4.2
orientation = portrait
fullscreen = 0
android.permissions =
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
