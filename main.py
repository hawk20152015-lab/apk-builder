# -*- coding: utf-8 -*-
"""تطبيق رصيد الإجازات والدوام — نسخة أندرويد.
يشغّل خادم Flask داخل الهاتف، وواجهة أندرويد (webview bootstrap) تعرض الصفحة."""
import os

# قاعدة البيانات في مجلد التطبيق الخاص حتى لا تُفقد عند التحديث
DATA_DIR = os.environ.get('ANDROID_PRIVATE') or os.path.dirname(os.path.abspath(__file__))

import app as leave_app

leave_app.DB_PATH = os.path.join(DATA_DIR, 'leave_management.db')

if __name__ == '__main__':
    leave_app.init_db()
    leave_app.app.run(host='127.0.0.1', port=5000, debug=False,
                      use_reloader=False, threaded=True)
