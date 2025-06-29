from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
import psycopg2.extras
from datetime import datetime
import smtplib, ssl
import random
import os

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- EMAIL UTILITY ----------------
def send_email(receiver_email, subject, body):
    sender_email = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_PASSWORD")

    message = f"Subject: {subject}\n\n{body}"
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, message)

@app.route('/')
def home():
    return redirect(url_for('login'))

# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    branches = ['CSE', 'ECE', 'EEE', 'MECH', 'CIVIL', 'CAI', 'CSD']
    if request.method == 'POST':
        name = request.form['name']
        branch = request.form['branch']
        email = request.form['email']
        mobile = request.form.get('mobile') or None
        password = request.form['password']
        student_id = request.form.get('student_id') or None

        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['pending_user'] = {
            'name': name,
            'branch': branch,
            'email': email,
            'mobile': mobile,
            'password': password,
            'student_id': student_id
        }

        try:
            send_email(email, "Your OTP Verification Code", f"Your OTP is: {otp}")
            flash("OTP sent to your email. Please verify.")
            return redirect(url_for('verify_otp'))
        except Exception as e:
            flash(f"Failed to send OTP: {e}")

    return render_template("register.html", branches=branches)

# ---------------- VERIFY OTP ----------------
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        entered_otp = request.form['otp']
        if entered_otp == session.get('otp'):
            user = session.get('pending_user')
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute("""
                    INSERT INTO students (name, student_id, branch, email, mobile, password)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user['name'], user['student_id'], user['branch'], user['email'], user['mobile'], user['password']))
                conn.commit()
                flash("Registration successful! Please login.")
                return redirect(url_for('login'))
            except Exception as e:
                conn.rollback()
                flash("Error saving to database: " + str(e))
            finally:
                cur.close()
                conn.close()
        else:
            flash("Invalid OTP. Please try again.")

    return render_template("verify_otp.html")

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        role = request.form['role']
        email = request.form['email'].strip()
        password = request.form['password'].strip()
        table = 'students' if role == 'student' else 'faculty'

        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"SELECT * FROM {table} WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user['password'] == password:
            session['email'] = email
            session['role'] = role
            session['branch'] = user['branch']
            return redirect(url_for(f"{role}_dashboard"))
        else:
            error = "Invalid credentials."

    return render_template("login.html", error=error)

# ---------------- STUDENT DASHBOARD ----------------
@app.route('/student/dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    email = session['email']
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM students WHERE email=%s", (email,))
    student = cur.fetchone()

    cur.execute("""
        SELECT * FROM gatepass_requests
        WHERE student_id=%s
        ORDER BY request_date DESC
    """, (student['student_id'],))
    requests = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("student_dashboard.html", student=student, requests=requests)

# ---------------- GATEPASS REQUEST ----------------
@app.route('/student/gatepass', methods=['GET', 'POST'])
def student_gatepass():
    if session.get('role') != 'student':
        return redirect(url_for('login'))

    email = session['email']
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM students WHERE email=%s", (email,))
    student = cur.fetchone()

    if request.method == 'POST':
        reason = request.form['reason']
        request_date = datetime.now()

        cur.execute("""
            INSERT INTO gatepass_requests (student_id, reason, status, request_date)
            VALUES (%s, %s, 'Pending', %s)
        """, (student['student_id'], reason, request_date))
        conn.commit()

        cur.execute("SELECT email FROM faculty WHERE branch=%s LIMIT 1", (student['branch'],))
        faculty = cur.fetchone()

        if faculty:
            faculty_email = faculty['email']
            subject = f"New Gatepass Request from {student['name']} ({student['student_id']})"
            body = f"""
Dear Faculty,

A new gatepass request has been submitted:

- Name: {student['name']}
- Student ID: {student['student_id']}
- Branch: {student['branch']}
- Reason: {reason}
- Date: {request_date.strftime('%Y-%m-%d %H:%M')}

Login here to view: https://gatepass-system-gmz7.onrender.com/login

Regards,
Gatepass System
            """
            try:
                send_email(faculty_email, subject, body)
            except Exception as e:
                flash("Gatepass submitted, but failed to notify faculty: " + str(e))

        flash("Gatepass request submitted and faculty notified.")
        cur.close()
        conn.close()
        return redirect(url_for('student_dashboard'))

    cur.close()
    conn.close()
    return render_template("gatepass_form.html", student=student)

# ---------------- FACULTY DASHBOARD ----------------
@app.route('/faculty/dashboard')
def faculty_dashboard():
    if session.get('role') != 'faculty':
        return redirect(url_for('login'))

    branch = session.get('branch')
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT gr.id, gr.student_id, s.name, s.branch, gr.reason,
               gr.status, gr.faculty_remark, gr.request_date
        FROM gatepass_requests gr
        JOIN students s ON gr.student_id = s.student_id
        WHERE s.branch = %s
        ORDER BY gr.request_date DESC
    """, (branch,))
    requests = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("faculty_dashboard.html", requests=requests)

# ---------------- APPROVE/REJECT ----------------
@app.route('/faculty/approve/<int:req_id>', methods=['POST'])
def faculty_approve(req_id):
    if session.get('role') != 'faculty':
        return redirect(url_for('login'))

    status = request.form['action']
    remark = request.form['remark']

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT gr.*, s.name, s.email, s.student_id, gr.request_date
        FROM gatepass_requests gr
        JOIN students s ON gr.student_id = s.student_id
        WHERE gr.id = %s
    """, (req_id,))
    data = cur.fetchone()

    if data:
        cur.execute("""
            UPDATE gatepass_requests
            SET status=%s, faculty_remark=%s
            WHERE id=%s
        """, (status, remark, req_id))
        conn.commit()

        subject = f"Gatepass Request {status.capitalize()} - Gatepass System"
        body = f"""
Dear {data['name']},

Your gatepass request submitted on {data['request_date'].strftime('%Y-%m-%d %H:%M')} has been {status.upper()}.

Faculty Remark: {remark}

You can check status here:
https://gatepass-system-gmz7.onrender.com/student/dashboard

Regards,
Gatepass System
        """
        try:
            send_email(data['email'], subject, body)
        except Exception as e:
            flash("Request updated, but failed to notify student: " + str(e))

    cur.close()
    conn.close()
    flash(f"Request {status} successfully.")
    return redirect(url_for('faculty_dashboard'))

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)  
