from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
import psycopg2.extras
from datetime import datetime
import smtplib, ssl
import random

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- EMAIL OTP UTILITY ----------------
def send_otp_email(receiver_email, otp):
    sender_email = "your_email@gmail.com"
    app_password = "your_app_password"  # Replace with your Gmail App Password
    
    subject = "Your OTP Verification Code"
    body = f"Your OTP is: {otp}"
    message = f"Subject: {subject}\n\n{body}"

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, message)

# ---------------- HOME ----------------
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

        # Generate and send OTP
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
            send_otp_email(email, otp)
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
        cur.execute("""
            INSERT INTO gatepass_requests (student_id, reason, status, request_date)
            VALUES (%s, %s, 'Pending', %s)
        """, (student['student_id'], reason, datetime.now()))
        conn.commit()
        flash("Gatepass request submitted.")
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
    cur = conn.cursor()
    cur.execute("""
        UPDATE gatepass_requests
        SET status=%s, faculty_remark=%s
        WHERE id=%s
    """, (status, remark, req_id))
    conn.commit()
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
