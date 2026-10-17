#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تطبيق رصيد الاجازات والدوام - نسخة محسّنة
مع نظام الإجازات والبدلاء للخفر
"""

from flask import Flask, render_template_string, request, jsonify
import sqlite3
from datetime import datetime
import json

app = Flask(__name__)
DB_PATH = 'leave_management.db'

def init_db():
    """إنشاء قاعدة البيانات"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # حذف الجداول القديمة
    cursor.execute('DROP TABLE IF EXISTS employees')
    cursor.execute('DROP TABLE IF EXISTS leaves')
    cursor.execute('DROP TABLE IF EXISTS backups')
    
    # جدول الموظفين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position TEXT NOT NULL,
            hire_date TEXT NOT NULL,
            shift_type TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            shift_duration TEXT NOT NULL,
            backup_id INTEGER,
            status TEXT DEFAULT 'نشط'
        )
    ''')
    
    # جدول الإجازات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS leaves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'معلق',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id)
        )
    ''')
    
    # جدول البدلاء
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            backup_employee_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            FOREIGN KEY (backup_employee_id) REFERENCES employees(id)
        )
    ''')
    
    # إضافة بيانات تجريبية
    sample_data = [
        ("أحمد محمد", "مهندس", "2020-01-15", "صباحي", "07:00", "15:00", "دوام يومي", None),
        ("فاطمة علي", "محاسبة", "2019-05-20", "صباحي", "08:00", "16:00", "دوام يومي", None),
        ("عمر حسن", "مدير", "2018-03-10", "صباحي", "07:30", "15:30", "دوام يومي", None),
        ("ليلى إبراهيم", "موظفة", "2021-07-25", "مسائي", "15:00", "23:00", "3 أيام/أسبوع", None),
        ("محمود أحمد", "فني", "2020-11-30", "مسائي", "14:00", "22:00", "أسبوع", None),
    ]
    
    for name, position, hire_date, shift_type, start_time, end_time, duration, backup_id in sample_data:
        cursor.execute('''
            INSERT INTO employees (name, position, hire_date, shift_type, start_time, end_time, shift_duration, backup_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, position, hire_date, shift_type, start_time, end_time, duration, backup_id))
    
    # تعيين بدلاء للخفر (ليلى لها محمود بديل والعكس)
    cursor.execute('UPDATE employees SET backup_id = 5 WHERE id = 4')
    cursor.execute('UPDATE employees SET backup_id = 4 WHERE id = 5')
    
    conn.commit()
    conn.close()

def get_employees():
    """الحصول على جميع الموظفين"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees')
    employees = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return employees

def get_employee(emp_id):
    """الحصول على موظف واحد"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM employees WHERE id = ?', (emp_id,))
    employee = cursor.fetchone()
    conn.close()
    return dict(employee) if employee else None

def get_leaves():
    """الحصول على جميع الإجازات"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT l.*, e.name as employee_name
        FROM leaves l
        JOIN employees e ON l.employee_id = e.id
        ORDER BY l.start_date DESC
    ''')
    leaves = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return leaves

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تطبيق رصيد الاجازات والدوام</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Arial', 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 32px;
            margin-bottom: 10px;
        }
        
        .tabs {
            display: flex;
            border-bottom: 2px solid #eee;
            flex-wrap: wrap;
            overflow-x: auto;
        }
        
        .tab-button {
            flex: 1;
            min-width: 130px;
            padding: 15px;
            border: none;
            background: white;
            color: #333;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: bold;
        }
        
        .tab-button:hover {
            background: #f5f5f5;
        }
        
        .tab-button.active {
            background: #667eea;
            color: white;
            border-bottom: 3px solid #667eea;
        }
        
        .tab-content {
            display: none;
            padding: 30px;
        }
        
        .tab-content.active {
            display: block;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 13px;
        }
        
        table th {
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: right;
            font-weight: bold;
        }
        
        table td {
            padding: 10px 12px;
            border-bottom: 1px solid #eee;
        }
        
        table tr:hover {
            background: #f9f9f9;
        }
        
        .action-buttons {
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }
        
        .btn-small {
            padding: 5px 10px;
            font-size: 11px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-weight: bold;
        }
        
        .btn-edit {
            background: #17a2b8;
            color: white;
        }
        
        .btn-edit:hover {
            background: #138496;
        }
        
        .btn-delete {
            background: #dc3545;
            color: white;
        }
        
        .btn-delete:hover {
            background: #c82333;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
            font-size: 14px;
        }
        
        .form-group input,
        .form-group select,
        .form-group textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
            font-family: 'Arial', sans-serif;
        }
        
        .form-group textarea {
            resize: vertical;
            min-height: 80px;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        .form-row-3 {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 15px;
        }
        
        button.btn {
            background: #667eea;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            transition: all 0.3s;
            font-family: 'Arial', sans-serif;
        }
        
        button.btn:hover {
            background: #5568d3;
        }
        
        .alert {
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
            font-weight: bold;
            font-size: 14px;
        }
        
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .alert-info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-card h3 {
            font-size: 24px;
            margin-bottom: 10px;
        }
        
        .stat-card p {
            font-size: 12px;
            opacity: 0.9;
        }
        
        .shift-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
        }
        
        .shift-morning {
            background: #fff3cd;
            color: #856404;
        }
        
        .shift-evening {
            background: #d1ecf1;
            color: #0c5460;
        }
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        
        .modal-content {
            background-color: white;
            margin: 5% auto;
            padding: 30px;
            border-radius: 10px;
            width: 90%;
            max-width: 600px;
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .modal-header {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
            color: #333;
        }
        
        .modal-close {
            float: left;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
            color: #999;
        }
        
        .modal-close:hover {
            color: #333;
        }
        
        .backup-info {
            background: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            border-right: 4px solid #667eea;
            margin: 10px 0;
            font-size: 13px;
        }
        
        .footer {
            background: #333;
            color: #999;
            text-align: center;
            padding: 20px;
            margin-top: 30px;
            border-top: 1px solid #555;
            font-size: 13px;
        }
        
        .footer a {
            color: #667eea;
            text-decoration: none;
        }
        
        .footer a:hover {
            text-decoration: underline;
        }
    
        /* ---- تحسينات الهاتف ---- */
        @media (max-width: 640px) {
            body { padding: 0 !important; }
            .container { border-radius: 0; box-shadow: none; }
            .header { padding: 20px 14px; }
            .header h1 { font-size: 24px; }
            table { display: block; overflow-x: auto; white-space: nowrap; -webkit-overflow-scrolling: touch; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 تطبيق رصيد الاجازات والدوام</h1>
            <p>نظام إدارة الموظفين والإجازات والبدلاء</p>
        </div>
        
        <div class="tabs">
            <button class="tab-button active" onclick="showTab('employees')">👥 الموظفين</button>
            <button class="tab-button" onclick="showTab('leaves')">📋 الإجازات</button>
            <button class="tab-button" onclick="showTab('backups')">🔄 البدلاء</button>
            <button class="tab-button" onclick="showTab('add')">➕ إضافة</button>
        </div>
        
        <!-- تبويب الموظفين -->
        <div id="employees" class="tab-content active">
            <h2>👥 قائمة الموظفين</h2>
            <div id="employees-stats" class="stats"></div>
            <table>
                <thead>
                    <tr>
                        <th>الرقم</th>
                        <th>الاسم</th>
                        <th>المنصب</th>
                        <th>النوع</th>
                        <th>الوقت</th>
                        <th>المدة</th>
                        <th>الإجراءات</th>
                    </tr>
                </thead>
                <tbody id="employees-table">
                </tbody>
            </table>
        </div>
        
        <!-- تبويب الإجازات -->
        <div id="leaves" class="tab-content">
            <h2>📋 الإجازات</h2>
            <button class="btn" onclick="showAddLeaveModal()" style="margin-bottom: 20px;">➕ إضافة إجازة</button>
            
            <table>
                <thead>
                    <tr>
                        <th>الرقم</th>
                        <th>الموظف</th>
                        <th>نوع الإجازة</th>
                        <th>من</th>
                        <th>إلى</th>
                        <th>السبب</th>
                        <th>الحالة</th>
                        <th>الإجراءات</th>
                    </tr>
                </thead>
                <tbody id="leaves-table">
                </tbody>
            </table>
        </div>
        
        <!-- تبويب البدلاء -->
        <div id="backups" class="tab-content">
            <h2>🔄 نظام البدلاء (للخفر فقط)</h2>
            <div class="alert alert-info">
                📌 اختر بديل لكل موظف خفر (مسائي)
            </div>
            <table>
                <thead>
                    <tr>
                        <th>الموظف</th>
                        <th>النوع</th>
                        <th>البديل</th>
                        <th>الإجراءات</th>
                    </tr>
                </thead>
                <tbody id="backups-table">
                </tbody>
            </table>
        </div>
        
        <!-- تبويب الإضافة -->
        <div id="add" class="tab-content">
            <h2>➕ إضافة موظف جديد</h2>
            <form id="addEmployeeForm">
                <div class="form-group">
                    <label>الاسم *</label>
                    <input type="text" id="name" required>
                </div>
                
                <div class="form-group">
                    <label>المنصب *</label>
                    <input type="text" id="position" required>
                </div>
                
                <div class="form-group">
                    <label>تاريخ التعيين *</label>
                    <input type="date" id="hire_date" required>
                </div>
                
                <div class="form-group">
                    <label>نوع الدوام *</label>
                    <select id="shift_type" required onchange="updateShiftFields()">
                        <option value="">-- اختر --</option>
                        <option value="صباحي">صباحي</option>
                        <option value="مسائي">مسائي (خفر)</option>
                    </select>
                </div>
                
                <div class="form-row-3">
                    <div class="form-group">
                        <label>الصعود *</label>
                        <input type="time" id="start_time" required>
                    </div>
                    <div class="form-group">
                        <label>النزول *</label>
                        <input type="time" id="end_time" required>
                    </div>
                    <div class="form-group">
                        <label>المدة *</label>
                        <input type="text" id="shift_duration" required placeholder="مثال: 3 أيام">
                    </div>
                </div>
                
                <div id="backup-select" class="form-group" style="display:none;">
                    <label>اختر بديل (للخفر) *</label>
                    <select id="backup_id">
                        <option value="">-- اختر بديل --</option>
                    </select>
                </div>
                
                <button type="submit" class="btn">✅ إضافة</button>
            </form>
            <div id="form-message"></div>
        </div>
    </div>
    
    <!-- Modal إضافة إجازة -->
    <div id="addLeaveModal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeLeaveModal()">&times;</span>
            <div class="modal-header">➕ إضافة إجازة جديدة</div>
            
            <form id="addLeaveForm">
                <div class="form-group">
                    <label>الموظف *</label>
                    <select id="leave_employee_id" required>
                        <option value="">-- اختر موظف --</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label>نوع الإجازة *</label>
                    <select id="leave_type" required>
                        <option value="">-- اختر نوع --</option>
                        <option value="إجازة عادية">إجازة عادية</option>
                        <option value="إجازة مرضية">إجازة مرضية</option>
                        <option value="إجازة بدون راتب">إجازة بدون راتب</option>
                        <option value="إجازة طوارئ">إجازة طوارئ</option>
                    </select>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label>من *</label>
                        <input type="date" id="leave_start_date" required>
                    </div>
                    <div class="form-group">
                        <label>إلى *</label>
                        <input type="date" id="leave_end_date" required>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>السبب</label>
                    <textarea id="leave_reason" placeholder="اكتب السبب (اختياري)"></textarea>
                </div>
                
                <button type="submit" class="btn" style="width: 100%;">💾 حفظ الإجازة</button>
            </form>
        </div>
    </div>
    
    <!-- Modal تعديل الموظف -->
    <div id="editEmployeeModal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeEditEmployeeModal()">&times;</span>
            <div class="modal-header">✏️ تعديل بيانات الموظف</div>
            
            <form id="editEmployeeForm">
                <input type="hidden" id="edit_emp_id">
                
                <div class="form-group">
                    <label>الاسم *</label>
                    <input type="text" id="edit_emp_name" required>
                </div>
                
                <div class="form-group">
                    <label>المنصب *</label>
                    <input type="text" id="edit_emp_position" required>
                </div>
                
                <div class="form-group">
                    <label>تاريخ التعيين *</label>
                    <input type="date" id="edit_emp_hire_date" required>
                </div>
                
                <div class="form-group">
                    <label>نوع الدوام *</label>
                    <select id="edit_emp_shift_type" required onchange="updateEditShiftFields()">
                        <option value="صباحي">صباحي</option>
                        <option value="مسائي">مسائي (خفر)</option>
                    </select>
                </div>
                
                <div class="form-row-3">
                    <div class="form-group">
                        <label>الصعود *</label>
                        <input type="time" id="edit_emp_start_time" required>
                    </div>
                    <div class="form-group">
                        <label>النزول *</label>
                        <input type="time" id="edit_emp_end_time" required>
                    </div>
                    <div class="form-group">
                        <label>المدة *</label>
                        <input type="text" id="edit_emp_shift_duration" required>
                    </div>
                </div>
                
                <div id="edit_backup_select" class="form-group" style="display:none;">
                    <label>البديل *</label>
                    <select id="edit_emp_backup_id">
                        <option value="">-- اختر بديل --</option>
                    </select>
                </div>
                
                <button type="submit" class="btn" style="width: 100%;">💾 حفظ التعديلات</button>
            </form>
        </div>
    </div>
    
    <!-- Footer -->
    <div class="footer">
        <p>📱 تطوير و برمجة: <strong>عمر كريم</strong></p>
        <p>تطبيق إدارة الموظفين والإجازات والدوام الرسمي © 2026</p>
    </div>
    
    <!-- Modal تعديل الموظف -->
    <div id="editEmployeeModal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeEditEmployeeModal()">&times;</span>
            <div class="modal-header">✏️ تعديل بيانات الموظف</div>
            
            <form id="editEmployeeForm">
                <input type="hidden" id="edit_emp_id">
                
                <div class="form-group">
                    <label>الاسم *</label>
                    <input type="text" id="edit_emp_name" required>
                </div>
                
                <div class="form-group">
                    <label>المنصب *</label>
                    <input type="text" id="edit_emp_position" required>
                </div>
                
                <div class="form-group">
                    <label>نوع الدوام *</label>
                    <select id="edit_emp_shift_type" required>
                        <option value="صباحي">صباحي</option>
                        <option value="مسائي">مسائي (خفر)</option>
                    </select>
                </div>
                
                <div class="form-row-3">
                    <div class="form-group">
                        <label>الصعود *</label>
                        <input type="time" id="edit_emp_start_time" required>
                    </div>
                    <div class="form-group">
                        <label>النزول *</label>
                        <input type="time" id="edit_emp_end_time" required>
                    </div>
                    <div class="form-group">
                        <label>المدة *</label>
                        <input type="text" id="edit_emp_shift_duration" required>
                    </div>
                </div>
                
                <button type="submit" class="btn" style="width: 100%;">💾 حفظ التعديلات</button>
            </form>
        </div>
    </div>
    
    <!-- Modal تعديل البديل -->
    <div id="editBackupModal" class="modal">
        <div class="modal-content">
            <span class="modal-close" onclick="closeEditBackupModal()">&times;</span>
            <div class="modal-header">✏️ تعديل البديل</div>
            
            <form id="editBackupForm">
                <input type="hidden" id="edit_backup_emp_id">
                
                <div class="form-group">
                    <label id="backup_emp_label"></label>
                </div>
                
                <div class="form-group">
                    <label>اختر بديل جديد *</label>
                    <select id="edit_backup_id" required>
                        <option value="">-- اختر بديل --</option>
                    </select>
                </div>
                
                <button type="submit" class="btn" style="width: 100%;">💾 حفظ التعديل</button>
            </form>
        </div>
    </div>
    
    <script>
        const shiftTimes = {
            'صباحي': { start: '07:00', end: '15:00' },
            'مسائي': { start: '15:00', end: '23:00' }
        };
        
        document.addEventListener('DOMContentLoaded', function() {
            loadEmployees();
            loadLeaves();
            loadBackups();
            loadEmployeesForLeave();
        });
        
        // تحديث حقول الدوام
        function updateShiftFields() {
            const shiftType = document.getElementById('shift_type').value;
            const backupSelect = document.getElementById('backup-select');
            
            if (shiftType && shiftTimes[shiftType]) {
                document.getElementById('start_time').value = shiftTimes[shiftType].start;
                document.getElementById('end_time').value = shiftTimes[shiftType].end;
            }
            
            if (shiftType === 'مسائي') {
                backupSelect.style.display = 'block';
                loadBackupOptions();
            } else {
                backupSelect.style.display = 'none';
                document.getElementById('backup_id').value = '';
            }
        }
        
        // تحديث حقول الدوام في التعديل
        function updateEditShiftFields() {
            const shiftType = document.getElementById('edit_emp_shift_type').value;
            const backupSelect = document.getElementById('edit_backup_select');
            
            if (shiftType && shiftTimes[shiftType]) {
                document.getElementById('edit_emp_start_time').value = shiftTimes[shiftType].start;
                document.getElementById('edit_emp_end_time').value = shiftTimes[shiftType].end;
            }
            
            if (shiftType === 'مسائي') {
                backupSelect.style.display = 'block';
                loadEditBackupOptions();
            } else {
                backupSelect.style.display = 'none';
                document.getElementById('edit_emp_backup_id').value = '';
            }
        }
        
        // فتح modal التعديل
        function editEmployee(empId) {
            fetch(`/api/employee/${empId}`)
                .then(r => r.json())
                .then(emp => {
                    document.getElementById('edit_emp_id').value = emp.id;
                    document.getElementById('edit_emp_name').value = emp.name;
                    document.getElementById('edit_emp_position').value = emp.position;
                    document.getElementById('edit_emp_hire_date').value = emp.hire_date;
                    document.getElementById('edit_emp_shift_type').value = emp.shift_type;
                    document.getElementById('edit_emp_start_time').value = emp.start_time;
                    document.getElementById('edit_emp_end_time').value = emp.end_time;
                    document.getElementById('edit_emp_shift_duration').value = emp.shift_duration;
                    
                    if (emp.shift_type === 'مسائي') {
                        document.getElementById('edit_backup_select').style.display = 'block';
                        loadEditBackupOptions(emp.backup_id);
                    } else {
                        document.getElementById('edit_backup_select').style.display = 'none';
                    }
                    
                    document.getElementById('editEmployeeModal').style.display = 'block';
                });
        }
        
        function closeEditEmployeeModal() {
            document.getElementById('editEmployeeModal').style.display = 'none';
        }
        
        function loadEditBackupOptions(currentBackupId) {
            fetch('/api/employees')
                .then(r => r.json())
                .then(data => {
                    const select = document.getElementById('edit_emp_backup_id');
                    const empId = document.getElementById('edit_emp_id').value;
                    select.innerHTML = '<option value="">-- اختر بديل --</option>';
                    
                    data.forEach(emp => {
                        if (emp.shift_type === 'مسائي' && emp.id != empId) {
                            const selected = emp.id === currentBackupId ? 'selected' : '';
                            select.innerHTML += `<option value="${emp.id}" ${selected}>${emp.name}</option>`;
                        }
                    });
                });
        }
        
        // تحميل خيارات البدلاء
        function loadBackupOptions() {
            fetch('/api/employees')
                .then(r => r.json())
                .then(data => {
                    const select = document.getElementById('backup_id');
                    select.innerHTML = '<option value="">-- اختر بديل --</option>';
                    
                    data.forEach(emp => {
                        if (emp.shift_type === 'مسائي') {
                            select.innerHTML += `<option value="${emp.id}">${emp.name}</option>`;
                        }
                    });
                });
        }
        
        // تبديل التبويبات
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(e => e.classList.remove('active'));
            document.querySelectorAll('.tab-button').forEach(e => e.classList.remove('active'));
            
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'backups') loadBackups();
        }
        
        // تحميل الموظفين
        function loadEmployees() {
            fetch('/api/employees')
                .then(r => r.json())
                .then(data => {
                    const table = document.getElementById('employees-table');
                    const stats = document.getElementById('employees-stats');
                    
                    table.innerHTML = '';
                    const morning = data.filter(e => e.shift_type === 'صباحي').length;
                    const evening = data.filter(e => e.shift_type === 'مسائي').length;
                    
                    stats.innerHTML = `
                        <div class="stat-card">
                            <h3>${data.length}</h3>
                            <p>الموظفين</p>
                        </div>
                        <div class="stat-card">
                            <h3>${morning}</h3>
                            <p>صباحي</p>
                        </div>
                        <div class="stat-card">
                            <h3>${evening}</h3>
                            <p>خفر</p>
                        </div>
                    `;
                    
                    data.forEach(emp => {
                        const badge = emp.shift_type === 'صباحي' 
                            ? '<span class="shift-badge shift-morning">☀️ صباحي</span>'
                            : '<span class="shift-badge shift-evening">🌙 خفر</span>';
                        
                        const row = `
                            <tr>
                                <td>${emp.id}</td>
                                <td>${emp.name}</td>
                                <td>${emp.position}</td>
                                <td>${badge}</td>
                                <td>${emp.start_time} - ${emp.end_time}</td>
                                <td>${emp.shift_duration}</td>
                                <td>
                                    <div class="action-buttons">
                                        <button class="btn-small btn-edit" onclick="editEmployee(${emp.id})">✏️</button>
                                        <button class="btn-small btn-delete" onclick="deleteEmployee(${emp.id})">🗑️</button>
                                    </div>
                                </td>
                            </tr>
                        `;
                        table.innerHTML += row;
                    });
                });
        }
        
        // تحميل الإجازات
        function loadLeaves() {
            fetch('/api/leaves')
                .then(r => r.json())
                .then(data => {
                    const table = document.getElementById('leaves-table');
                    table.innerHTML = '';
                    
                    if (data.length === 0) {
                        table.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 20px;">لا توجد إجازات</td></tr>';
                        return;
                    }
                    
                    data.forEach((leave, index) => {
                        const statusBadge = leave.status === 'معلق' 
                            ? '<span style="background: #ffc107; color: #000; padding: 3px 8px; border-radius: 3px; font-size: 11px;">⏳ معلق</span>'
                            : '<span style="background: #28a745; color: #fff; padding: 3px 8px; border-radius: 3px; font-size: 11px;">✅ موافق</span>';
                        
                        const row = `
                            <tr>
                                <td>${index + 1}</td>
                                <td>${leave.employee_name}</td>
                                <td>${leave.leave_type}</td>
                                <td>${leave.start_date}</td>
                                <td>${leave.end_date}</td>
                                <td>${leave.reason || '-'}</td>
                                <td>${statusBadge}</td>
                                <td>
                                    <button class="btn-small btn-delete" onclick="deleteLeave(${leave.id})">🗑️</button>
                                </td>
                            </tr>
                        `;
                        table.innerHTML += row;
                    });
                });
        }
        
        // تحميل البدلاء
        function loadBackups() {
            fetch('/api/employees')
                .then(r => r.json())
                .then(data => {
                    const table = document.getElementById('backups-table');
                    table.innerHTML = '';
                    
                    const evening = data.filter(e => e.shift_type === 'مسائي');
                    
                    if (evening.length === 0) {
                        table.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 20px;">لا يوجد موظفي خفر</td></tr>';
                        return;
                    }
                    
                    evening.forEach(emp => {
                        const backup = data.find(e => e.id === emp.backup_id);
                        const backupName = backup ? backup.name : '❌ لم يتم تحديد';
                        
                        const row = `
                            <tr>
                                <td>${emp.name}</td>
                                <td><span class="shift-badge shift-evening">🌙 خفر</span></td>
                                <td>${backupName}</td>
                                <td>
                                    <button class="btn-small btn-edit" onclick="editBackup(${emp.id})">✏️ تعديل</button>
                                </td>
                            </tr>
                        `;
                        table.innerHTML += row;
                    });
                });
        }
        
        // تحميل الموظفين للإجازات
        function loadEmployeesForLeave() {
            fetch('/api/employees')
                .then(r => r.json())
                .then(data => {
                    const select = document.getElementById('leave_employee_id');
                    select.innerHTML = '<option value="">-- اختر موظف --</option>';
                    
                    data.forEach(emp => {
                        select.innerHTML += `<option value="${emp.id}">${emp.name}</option>`;
                    });
                });
        }
        
        // Modal الإجازات
        function showAddLeaveModal() {
            document.getElementById('addLeaveModal').style.display = 'block';
        }
        
        function closeLeaveModal() {
            document.getElementById('addLeaveModal').style.display = 'none';
        }
        
        // Modal البديل
        function editBackup(empId) {
            fetch(`/api/employee/${empId}`)
                .then(r => r.json())
                .then(emp => {
                    document.getElementById('edit_backup_emp_id').value = emp.id;
                    document.getElementById('backup_emp_label').textContent = `البديل لـ: ${emp.name}`;
                    
                    // تحميل البدلاء الممكنين (موظفي خفر آخرين)
                    fetch('/api/employees')
                        .then(r => r.json())
                        .then(data => {
                            const select = document.getElementById('edit_backup_id');
                            select.innerHTML = '<option value="">-- اختر بديل --</option>';
                            
                            data.forEach(e => {
                                if (e.shift_type === 'مسائي' && e.id !== empId) {
                                    select.innerHTML += `<option value="${e.id}" ${e.id === emp.backup_id ? 'selected' : ''}>${e.name}</option>`;
                                }
                            });
                        });
                    
                    document.getElementById('editBackupModal').style.display = 'block';
                });
        }
        
        function closeEditBackupModal() {
            document.getElementById('editBackupModal').style.display = 'none';
        }
        
        // حفظ الإجازة
        document.getElementById('addLeaveForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const data = {
                employee_id: document.getElementById('leave_employee_id').value,
                leave_type: document.getElementById('leave_type').value,
                start_date: document.getElementById('leave_start_date').value,
                end_date: document.getElementById('leave_end_date').value,
                reason: document.getElementById('leave_reason').value,
            };
            
            fetch('/api/add-leave', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(response => {
                if (response.success) {
                    alert('✅ تمت إضافة الإجازة بنجاح!');
                    closeLeaveModal();
                    document.getElementById('addLeaveForm').reset();
                    loadLeaves();
                }
            });
        });
        
        // حفظ البديل
        document.getElementById('editBackupForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const data = {
                employee_id: document.getElementById('edit_backup_emp_id').value,
                backup_id: document.getElementById('edit_backup_id').value,
            };
            
            fetch('/api/update-backup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(response => {
                if (response.success) {
                    alert('✅ تم تحديث البديل بنجاح!');
                    closeEditBackupModal();
                    loadBackups();
                }
            });
        });
        
        // حذف إجازة
        function deleteLeave(leaveId) {
            if (confirm('هل تريد حذف الإجازة؟')) {
                fetch(`/api/delete-leave/${leaveId}`, {method: 'POST'})
                    .then(r => r.json())
                    .then(response => {
                        if (response.success) {
                            loadLeaves();
                        }
                    });
            }
        }
        
        // تعديل الموظف
        function editEmployee(empId) {
            fetch(`/api/employee/${empId}`)
                .then(r => r.json())
                .then(emp => {
                    document.getElementById('edit_emp_id').value = emp.id;
                    document.getElementById('edit_emp_name').value = emp.name;
                    document.getElementById('edit_emp_position').value = emp.position;
                    document.getElementById('edit_emp_shift_type').value = emp.shift_type;
                    document.getElementById('edit_emp_start_time').value = emp.start_time;
                    document.getElementById('edit_emp_end_time').value = emp.end_time;
                    document.getElementById('edit_emp_shift_duration').value = emp.shift_duration;
                    
                    document.getElementById('editEmployeeModal').style.display = 'block';
                });
        }
        
        function closeEditEmployeeModal() {
            document.getElementById('editEmployeeModal').style.display = 'none';
        }
        
        // حفظ تعديلات الموظف
        document.getElementById('editEmployeeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const data = {
                id: document.getElementById('edit_emp_id').value,
                name: document.getElementById('edit_emp_name').value,
                position: document.getElementById('edit_emp_position').value,
                hire_date: '2020-01-01', // لن نغيره
                shift_type: document.getElementById('edit_emp_shift_type').value,
                start_time: document.getElementById('edit_emp_start_time').value,
                end_time: document.getElementById('edit_emp_end_time').value,
                shift_duration: document.getElementById('edit_emp_shift_duration').value,
            };
            
            fetch('/api/update-employee', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(response => {
                if (response.success) {
                    alert('✅ تم تحديث البيانات بنجاح!');
                    closeEditEmployeeModal();
                    loadEmployees();
                    loadBackups();
                    loadEmployeesForLeave();
                } else {
                    alert('❌ حدث خطأ: ' + response.error);
                }
            });
        });
        
        // حذف موظف
        function deleteEmployee(empId) {
            if (confirm('هل تريد حذف الموظف؟')) {
                fetch(`/api/delete-employee/${empId}`, {method: 'POST'})
                    .then(r => r.json())
                    .then(response => {
                        if (response.success) {
                            loadEmployees();
                            loadBackups();
                            loadEmployeesForLeave();
                        }
                    });
            }
        }
        
        // إضافة موظف
        document.getElementById('addEmployeeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const data = {
                name: document.getElementById('name').value,
                position: document.getElementById('position').value,
                hire_date: document.getElementById('hire_date').value,
                shift_type: document.getElementById('shift_type').value,
                start_time: document.getElementById('start_time').value,
                end_time: document.getElementById('end_time').value,
                shift_duration: document.getElementById('shift_duration').value,
                backup_id: document.getElementById('backup_id').value || null,
            };
            
            fetch('/api/add-employee', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(response => {
                if (response.success) {
                    alert('✅ تمت إضافة الموظف بنجاح!');
                    document.getElementById('addEmployeeForm').reset();
                    loadEmployees();
                    loadBackups();
                    loadEmployeesForLeave();
                }
            });
        });
        
        // تعديل الموظف
        document.getElementById('editEmployeeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const data = {
                id: document.getElementById('edit_emp_id').value,
                name: document.getElementById('edit_emp_name').value,
                position: document.getElementById('edit_emp_position').value,
                hire_date: document.getElementById('edit_emp_hire_date').value,
                shift_type: document.getElementById('edit_emp_shift_type').value,
                start_time: document.getElementById('edit_emp_start_time').value,
                end_time: document.getElementById('edit_emp_end_time').value,
                shift_duration: document.getElementById('edit_emp_shift_duration').value,
                backup_id: document.getElementById('edit_emp_backup_id').value || null,
            };
            
            fetch('/api/update-employee', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(response => {
                if (response.success) {
                    alert('✅ تم تحديث بيانات الموظف بنجاح!');
                    closeEditEmployeeModal();
                    loadEmployees();
                    loadBackups();
                    loadEmployeesForLeave();
                } else {
                    alert('❌ حدث خطأ: ' + response.error);
                }
            });
        });
        
        // إغلاق modal عند الضغط خارجه
        window.onclick = function(event) {
            const leaveModal = document.getElementById('addLeaveModal');
            const backupModal = document.getElementById('editBackupModal');
            const empModal = document.getElementById('editEmployeeModal');
            
            if (event.target == leaveModal) leaveModal.style.display = 'none';
            if (event.target == backupModal) backupModal.style.display = 'none';
            if (event.target == empModal) empModal.style.display = 'none';
        }
    </script>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/employees')
def api_employees():
    return jsonify(get_employees())

@app.route('/api/employee/<int:emp_id>')
def api_employee(emp_id):
    return jsonify(get_employee(emp_id) or {})

@app.route('/api/leaves')
def api_leaves():
    return jsonify(get_leaves())

@app.route('/api/add-employee', methods=['POST'])
def api_add_employee():
    try:
        data = request.json
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO employees (name, position, hire_date, shift_type, start_time, end_time, shift_duration, backup_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['name'], data['position'], data['hire_date'], 
              data['shift_type'], data['start_time'], data['end_time'], data['shift_duration'], 
              data['backup_id'] or None))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/add-leave', methods=['POST'])
def api_add_leave():
    try:
        data = request.json
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO leaves (employee_id, leave_type, start_date, end_date, reason)
            VALUES (?, ?, ?, ?, ?)
        ''', (data['employee_id'], data['leave_type'], data['start_date'], 
              data['end_date'], data['reason']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-leave/<int:leave_id>', methods=['POST'])
def api_delete_leave(leave_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM leaves WHERE id=?', (leave_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/delete-employee/<int:emp_id>', methods=['POST'])
def api_delete_employee(emp_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM employees WHERE id=?', (emp_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-employee', methods=['POST'])
def api_update_employee():
    try:
        data = request.json
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE employees 
            SET name=?, position=?, shift_type=?, start_time=?, end_time=?, shift_duration=?
            WHERE id=?
        ''', (data['name'], data['position'], data['shift_type'], 
              data['start_time'], data['end_time'], data['shift_duration'], data['id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/update-backup', methods=['POST'])
def api_update_backup():
    try:
        data = request.json
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE employees SET backup_id=? WHERE id=?', 
                      (data['backup_id'] or None, data['employee_id']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    init_db()
    print("🚀 التطبيق على: http://localhost:5000")
    print("💡 Ctrl+C للخروج")
    app.run(debug=True, port=5000)
