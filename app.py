from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
import psycopg2.extras
from datetime import datetime
import smtplib, ssl
import random
import os
import pytz

app = Flask(__name__)
app.secret_key = "supersecretkey"

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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        branch = request.form['branch']
        student_id = request.form['student_id']
        mobile = request.form['mobile']
        email = request.form['email']
        password = request.form['password']
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM students WHERE email = %s", (email,))
        existing_user = cur.fetchone()
        if existing_user:
            cur.close()
            conn.close()
            return render_template('register.html', error="Email is already in use.")
        otp = str(random.randint(100000, 999999))
        session['otp'] = otp
        session['pending_user'] = {
            'name': name,
            'branch': branch,
            'student_id': student_id,
            'mobile': mobile,
            'email': email,
            'password': password
        }
        subject = "Your OTP for Gatepass Registration"
        body = f"Dear {name},\n\nYour OTP for registration is: {otp}\n\nPlease enter this on the verification page."
        try:
            send_email(email, subject, body)
        except Exception as e:
            flash("Failed to send OTP. Please check your email settings.")
            cur.close()
            conn.close()
            return render_template('register.html')
        cur.close()
        conn.close()
        return redirect(url_for('verify_otp'))
    return render_template('register.html')

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
            return redirect(url_for('student_dashboard' if role == 'student' else 'faculty_dashboard'))
        else:
            error = "Invalid credentials."
    return render_template("login.html", error=error)

@app.route('/student/dashboard')
def student_dashboard():
    if 'email' not in session or session.get('role') != 'student':
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    email = session['email']
    branch = session.get('branch', '')

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM students WHERE email = %s", (email,))
    student = cur.fetchone()

    cur.execute("""
        SELECT * FROM gatepass_requests
        WHERE student_id = %s
        ORDER BY request_date DESC
    """, (student['student_id'],))
    requests = cur.fetchall()

    cur.close()
    conn.close()

    return render_template('student_dashboard.html', student=student, requests=requests)

@app.route('/faculty/dashboard')
def faculty_dashboard():
    if 'email' not in session or session.get('role') != 'faculty':
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    email = session['email']
    branch = session.get('branch', '')

    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM faculty WHERE email = %s", (email,))
    faculty = cur.fetchone()
    cur.close()
    conn.close()

    return render_template('faculty_dashboard.html', faculty=faculty)

# ✅ FIXED function name to match student_dashboard.html
@app.route('/gatepass/request', methods=['GET', 'POST'])
def student_gatepass():
    if 'email' not in session or session.get('role') != 'student':
        flash("Unauthorized access.")
        return redirect(url_for('login'))

    student_email = session['email']
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ✅ Fetch student info
    cur.execute("SELECT student_id, name FROM students WHERE email = %s", (student_email,))
    student = cur.fetchone()

    if request.method == 'POST':
        reason = request.form['reason']
        request_date = datetime.now(pytz.timezone('Asia/Kolkata'))

        cur.execute("""
            INSERT INTO gatepass_requests (student_id, reason, status, request_date)
            VALUES (%s, %s, 'Pending', %s)
        """, (student['student_id'], reason, request_date))
        conn.commit()
        cur.close()
        conn.close()
        flash("Gatepass request submitted.")
        return redirect(url_for('student_dashboard'))

    cur.close()
    conn.close()
    
    # ✅ Pass student to the template
    return render_template('gatepass_form.html', student=student)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        role = request.form['role']
        table = 'students' if role == 'student' else 'faculty'
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(f"SELECT * FROM {table} WHERE email = %s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user:
            flash("No account found with that email.")
            return render_template('forgot_password.html')
        otp = str(random.randint(100000, 999999))
        session['reset_otp'] = otp
        session['reset_email'] = email
        session['reset_role'] = role
        subject = "Password Reset OTP - Gatepass System"
        body = f"Dear {user['name']},\n\nYour OTP for password reset is: {otp}\n\nIf you did not request this, please ignore this email.\n\nRegards,\nGatepass System"
        try:
            send_email(email, subject, body)
            flash("OTP sent to your email address.")
            return redirect(url_for('reset_password'))
        except Exception as e:
            flash("Failed to send OTP email: " + str(e))
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        entered_otp = request.form['otp']
        new_password = request.form['new_password']
        if entered_otp != session.get('reset_otp'):
            flash("Invalid OTP. Please try again.")
            return render_template("reset_password.html")
        email = session.get('reset_email')
        role = session.get('reset_role')
        table = 'students' if role == 'student' else 'faculty'
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"UPDATE {table} SET password = %s WHERE email = %s", (new_password, email))
        conn.commit()
        cur.close()
        conn.close()
        session.pop('reset_otp', None)
        session.pop('reset_email', None)
        session.pop('reset_role', None)
        flash("Password reset successfully. Please log in.")
        return redirect(url_for('login'))
    return render_template("reset_password.html")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
