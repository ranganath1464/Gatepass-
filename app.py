from flask import Flask, render_template, request, redirect, url_for, session, flash
from db_config import get_connection
import psycopg2.extras
from datetime import datetime
import smtplib, ssl
import random
import os
import qrcode
from io import BytesIO
from base64 import b64encode

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ---------------- EMAIL UTILITY WITH QR ----------------
def send_email_with_qr(receiver_email, subject, body_text, qr_data_url):
    sender_email = os.environ.get("EMAIL_USER")
    app_password = os.environ.get("EMAIL_PASSWORD")

    # Generate QR code
    qr_img = qrcode.make(qr_data_url)
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    img_str = b64encode(buffered.getvalue()).decode()

    html_body = f"""
    <html>
    <body>
        <p>{body_text}</p>
        <p><b>Scan QR Code to check your gatepass status:</b></p>
        <img src="data:image/png;base64,{img_str}" alt="QR Code" />
    </body>
    </html>
    """

    message = f"Subject: {subject}\nContent-Type: text/html\n\n{html_body}"

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, receiver_email, message)

# ---------------- STATUS PAGE ROUTE ----------------
@app.route('/status/<int:req_id>')
def show_status(req_id):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT gr.status, gr.request_date, s.name
        FROM gatepass_requests gr
        JOIN students s ON gr.student_id = s.student_id
        WHERE gr.id = %s
    """, (req_id,))
    data = cur.fetchone()
    cur.close()
    conn.close()

    if not data:
        return "Invalid or expired link."

    return render_template("status_view.html", status=data['status'], name=data['name'], date=data['request_date'])

# ---------------- FACULTY APPROVE/REJECT UPDATED ----------------
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
Dear {data['name']},<br><br>
Your gatepass request submitted on {data['request_date'].strftime('%Y-%m-%d %H:%M')} has been <b>{status.upper()}</b>.<br>
Faculty Remark: {remark}<br>

Check your status here:<br>
"""
        status_url = f"https://gatepass-system-gmz7.onrender.com/status/{req_id}"
        try:
            send_email_with_qr(data['email'], subject, body, status_url)
        except Exception as e:
            flash("Request updated, but failed to notify student: " + str(e))

    cur.close()
    conn.close()
    flash(f"Request {status} successfully.")
    return redirect(url_for('faculty_dashboard'))
