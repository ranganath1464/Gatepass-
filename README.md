# Gatepass-
# 🚪 Gatepass Management System

A complete web-based Gatepass Management System for colleges, built using **Flask**, **PostgreSQL**, **HTML**, **CSS**, and **Bootstrap**, deployed on **Render**.

## 🌐 Live Demo
🔗 [Visit Website](https://gatepass-system-gmz7.onrender.com/login)

---

## 📌 Features

### 👤 User Roles
- **Students**
  - Register and login
  - Submit gatepass requests with reason and mobile number
  - Track status (Pending / Accepted / Rejected)
  - Receive email & SMS notifications with QR code upon approval/rejection

- **Faculty**
  - Login using branch credentials
  - View gatepass requests from students of same branch
  - Approve or reject requests with remarks
  - Send real-time updates via email and SMS

---

### 📩 Notifications
- **Email Alerts**
  - Sent to faculty when a student submits a request
  - Sent to students after approval/rejection (includes QR code with status link)

- **SMS Notifications**
  - Sent to faculty on new request
  - Sent to student on approval/rejection

---

### 📲 QR Code Support
- Each approved/rejected request includes a QR code
- Scanning shows status:
  - ✅ Green Screen: **ACCEPTED**
  - ❌ Red Screen: **REJECTED**
  - With student name and timestamp in bold

---

## ⚙️ Tech Stack

| Layer         | Technology          |
|---------------|---------------------|
| Frontend      | HTML, CSS, Bootstrap |
| Backend       | Flask (Python)       |
| Database      | PostgreSQL (via psycopg2) |
| Deployment    | Render               |
| Email Service | SMTP (Gmail)         |
| SMS Service   | [Optional: Twilio/Way2SMS] |
| QR Generator  | `qrcode` Python module |

---

