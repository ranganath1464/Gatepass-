from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
import psycopg2.extras
from datetime import datetime
import smtplib, ssl
import random
import os
import pytz
import qrcode
from io import BytesIO
import base64


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

        # Generate and store OTP in session
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

    ist = pytz.timezone('Asia/Kolkata')
    for req in requests:
        if isinstance(req['request_date'], datetime):
            req['request_date'] = req['request_date'].astimezone(ist)

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
        ist = pytz.timezone('Asia/Kolkata')
        request_date = datetime.now(ist)

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

            date_str = request_date.strftime('%d-%m-%Y')
            time_str = request_date.strftime('%I:%M %p')
            day_str = request_date.strftime('%A')

            body = f"""
Dear Faculty,

A new gatepass request has been submitted:

- Name: {student['name']}
- Student ID: {student['student_id']}
- Branch: {student['branch']}
- Reason: {reason}
- Date: {date_str}, {day_str}
- Time: {time_str}

Login to view: https://gatepass-system-gmz7.onrender.com/login

Regards,
Gatepass System
            """
            try:
                send_email(faculty_email, subject, body)
            except Exception as e:
                flash("Gatepass submitted, but failed to notify faculty: " + str(e))

        flash("Gatepass request submitted successfully.")
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

    ist = pytz.timezone('Asia/Kolkata')
    for req in requests:
        if isinstance(req['request_date'], datetime):
            req['request_date'] = req['request_date'].astimezone(ist)

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

    # Fetch request + student data
    cur.execute("""
        SELECT gr.*, s.name, s.email, s.student_id, gr.request_date
        FROM gatepass_requests gr
        JOIN students s ON gr.student_id = s.student_id
        WHERE gr.id = %s
    """, (req_id,))
    data = cur.fetchone()

    if data:
        # Update DB with new status and remark
        cur.execute("""
            UPDATE gatepass_requests
            SET status=%s, faculty_remark=%s
            WHERE id=%s
        """, (status, remark, req_id))
        conn.commit()

        # Create QR with URL
        qr_url = f"https://gatepass-system-gmz7.onrender.com/qr-status/{req_id}"
        qr = qrcode.make(qr_url)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode()

        # Date formatting
        ist = pytz.timezone('Asia/Kolkata')
        req_dt = data['request_date'].astimezone(ist)
        now_dt = datetime.now(pytz.utc).astimezone(ist)

        subject = f"Gatepass {status.upper()} - Gatepass System"
        body = f"""
Dear {data['name']},

Your gatepass request submitted on:
Date: {req_dt.strftime('%d-%m-%Y')}, {req_dt.strftime('%A')}
Time: {req_dt.strftime('%I:%M %p')}

has been {status.upper()}.

Faculty Remark: {remark}

Approved On:
Date: {now_dt.strftime('%d-%m-%Y')}, {now_dt.strftime('%A')}
Time: {now_dt.strftime('%I:%M %p')}

Scan QR Code to view gatepass status:
{qr_url}

Regards,
Gatepass System
        """

        try:
            send_email(data['email'], subject, body)
        except Exception as e:
            flash("Request updated, but email failed: " + str(e))

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
# ---------------- FORGOT PASSWORD ----------------
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
            flash("No account found with this email.")
            return render_template("forgot_password.html")

        otp = str(random.randint(100000, 999999))
        session['reset_otp'] = otp
        session['reset_email'] = email
        session['reset_role'] = role

        subject = "OTP for Gatepass Password Reset"
        body = f"""
Dear {user['name']},

You have requested to reset your Gatepass System password.

Your OTP is: {otp}

If you didn't request this, please ignore this email.

Regards,
Gatepass System
        """

        try:
            send_email(email, subject, body)
            flash("OTP sent to your email.")
            return redirect(url_for('reset_password'))
        except Exception as e:
            flash("Failed to send OTP. Error: " + str(e))

    return render_template("forgot_password.html")

# ---------------- RESET PASSWORD ----------------
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        entered_otp = request.form['otp'].strip()
        new_password = request.form['new_password'].strip()

        if entered_otp != session.get('reset_otp'):
            flash("Invalid OTP.")
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

        # Clear session OTP data
        session.pop('reset_otp', None)
        session.pop('reset_email', None)
        session.pop('reset_role', None)

        flash("Password reset successful! Please login.")
        return redirect(url_for('login'))

    return render_template("reset_password.html")

from datetime import datetime
import pytz

@app.route('/qr-status/<int:req_id>')
def qr_status(req_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT gr.status, s.name, gr.request_date
        FROM gatepass_requests gr
        JOIN students s ON gr.student_id = s.student_id
        WHERE gr.id = %s
    """, (req_id,))
    data = cur.fetchone()
    cur.close()
    conn.close()

    if not data:
        return "Invalid QR or request ID."

    status_upper = data['status'].upper()

    if status_upper == "ACCEPTED":
        bg_color = "#28a745"  # green
    elif status_upper == "REJECTED":
        bg_color = "#dc3545"  # red
    else:
        bg_color = "#6c757d"  # gray fallback

    return render_template("qr_status_page.html",
                           status=status_upper,
                           name=data['name'],
                           dt=data['request_date'],
                           bg=bg_color)
