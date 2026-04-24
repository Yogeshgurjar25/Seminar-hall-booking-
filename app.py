# ================================================================
#  CDGI SEMINAR HALL BOOKING PORTAL
#  File: app.py  (updated — MySQL connected)
#  Run: python app.py
# ================================================================
#
#  Pehle ye install karo (terminal mein):
#  pip install flask flask-mysqldb werkzeug flask-mail
#
# ================================================================

from flask import Flask, render_template, request, redirect, session, jsonify
from flask_mail import Mail, Message
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date, datetime
from dotenv import load_dotenv
import random
import os

# .env file se credentials load karo
load_dotenv()

app = Flask(__name__)

# ── Secret key (session ke liye zaroori) ──────────────────────
app.secret_key = os.environ.get('SECRET_KEY')

# ── MySQL Config ───────────────────────────────────────────────
app.config['MYSQL_HOST']        = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER']        = os.environ.get('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD']    = os.environ.get('MYSQL_PASSWORD')
app.config['MYSQL_DB']          = os.environ.get('MYSQL_DB', 'cdgi_booking')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.config['MYSQL_CHARSET']     = 'utf8mb4'

mysql = MySQL(app)

# ── Gmail / Mail Config ────────────────────────────────────────
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('CDGI BookIt', os.environ.get('MAIL_USERNAME'))

mail = Mail(app)

def send_email(to, subject, body):
    """Helper — email bhejta hai. Fail hone pe crash nahi karta."""
    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Email send failed to {to}: {e}")



# ================================================================
#  DECORATORS — Login check karne ke liye
# ================================================================


def login_required(f):
    """User login hai ya nahi — nahi hai to /Login bhejo"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Admin login hai ya nahi — nahi hai to /admin_login bhejo"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect('/admin_login')
        return f(*args, **kwargs)
    return decorated

# ================================================================
#  PUBLIC ROUTES (login ki zaroorat nahi)
# ================================================================

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/about')
def about():
    return render_template("about.html")

@app.route('/contact')
def contact():
    return render_template("contact.html")

# ================================================================
#  REGISTER
#  Form fields: name, email, phone, department, password, confirm
# ================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name       = request.form['name'].strip()
        email      = request.form['email'].strip().lower()
        phone      = request.form['phone'].strip()
        department = request.form['department']
        password   = request.form['password']
        confirm    = request.form['confirm']

        # ── Validations ──
        if len(name) < 3:
            return render_template('register.html', error="Name too short")

        if not email.endswith('@cdgi.edu.in'):
            return render_template('register.html', error="Use college email only (@cdgi.edu.in)")

        if len(phone) != 10 or not phone.isdigit():
            return render_template('register.html', error="Invalid phone number (10 digits)")

        if password != confirm:
            return render_template('register.html', error="Passwords do not match")

        if len(password) < 6:
            return render_template('register.html', error="Password must be at least 6 characters")

        # ── Database mein save karo ──
        try:
            cur = mysql.connection.cursor()

            # Pehle check karo — email already exist karta hai?
            cur.execute("SELECT id, is_active FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing:
                if existing['is_active'] == 1:
                    return render_template('register.html', error="Email already registered")
                else:
                    # Purana unverified account delete karo — fresh OTP bhejenge
                    cur.execute("DELETE FROM users WHERE email = %s", (email,))
                    mysql.connection.commit()

            # Password hash karo — plain text kabhi nahi
            hashed = generate_password_hash(password)

            # User save karo — is_active=0 (verify hone ke baad 1 hoga)
            cur.execute(
                "INSERT INTO users (name, email, phone, department, password, is_active) VALUES (%s,%s,%s,%s,%s,0)",
                (name, email, phone, department, hashed)
            )
            user_id = cur.lastrowid

            # 6-digit OTP generate karo
            otp = str(random.randint(100000, 999999))

            # OTP table mein save karo (purana delete karke)
            cur.execute("DELETE FROM otp_verifications WHERE email = %s", (email,))
            cur.execute(
                "INSERT INTO otp_verifications (email, otp, expires_at) VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))",
                (email, otp)
            )
            mysql.connection.commit()
            cur.close()

            # OTP email bhejo
            send_email(
                to=email,
                subject="Verify your CDGI BookIt account — OTP",
                body=(
                    f"Dear {name},\n\n"
                    f"Your One-Time Password (OTP) to verify your CDGI BookIt account is:\n\n"
                    f"    {otp}\n\n"
                    f"This OTP is valid for 10 minutes. Do not share it with anyone.\n\n"
                    f"If you did not register on CDGI BookIt, please ignore this email.\n\n"
                    f"— CDGI BookIt"
                )
            )

            # Email session mein store karo — verify page pe kaam aayega
            session['pending_verification_email'] = email
            return redirect('/verify_otp')

        except Exception as e:
            return render_template('register.html', error=f"Error: {str(e)}")

    return render_template("register.html")

# ================================================================
#  VERIFY OTP
#  User OTP enter karta hai — sahi hone pe account activate hota hai
# ================================================================

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('pending_verification_email')

    # Agar session nahi hai — register pe bhejo
    if not email:
        return redirect('/register')

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()

        try:
            cur = mysql.connection.cursor()

            # OTP fetch karo — expired to nahi?
            cur.execute(
                "SELECT otp, expires_at FROM otp_verifications WHERE email = %s ORDER BY id DESC LIMIT 1",
                (email,)
            )
            record = cur.fetchone()

            if not record:
                return render_template('verify_otp.html', email=email,
                                       error="OTP not found. Please register again.")

            # Expiry check
            if datetime.now() > record['expires_at']:
                cur.execute("DELETE FROM otp_verifications WHERE email = %s", (email,))
                mysql.connection.commit()
                cur.close()
                session.pop('pending_verification_email', None)
                return render_template('verify_otp.html', email=email,
                                       error="OTP expired. Please register again.")

            # OTP match check
            if entered_otp != record['otp']:
                cur.close()
                return render_template('verify_otp.html', email=email,
                                       error="Incorrect OTP. Please try again.")

            # ✅ Sahi OTP — account activate karo
            cur.execute("UPDATE users SET is_active = 1 WHERE email = %s", (email,))
            cur.execute("DELETE FROM otp_verifications WHERE email = %s", (email,))

            # User ka data fetch karo auto-login ke liye
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            mysql.connection.commit()
            cur.close()

            session.pop('pending_verification_email', None)
            
            # Auto-login — seedha dashboard pe bhejo
            session['user_id']    = user['id']
            session['user_name']  = user['name']
            session['user_email'] = user['email']
            return redirect('/dashboard')
        
        except Exception as e:
            return render_template('verify_otp.html', email=email, error=f"Error: {str(e)}")

    return render_template('verify_otp.html', email=email)

# ================================================================
#  RESEND OTP
# ================================================================

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    email = session.get('pending_verification_email')
    if not email:
        return redirect('/register')

    try:
        cur = mysql.connection.cursor()

        # Check karo user exist karta hai
        cur.execute("SELECT name FROM users WHERE email = %s AND is_active = 0", (email,))
        user = cur.fetchone()
        if not user:
            cur.close()
            return redirect('/register')

        # Naya OTP generate karo
        otp = str(random.randint(100000, 999999))
        cur.execute("DELETE FROM otp_verifications WHERE email = %s", (email,))
        cur.execute(
            "INSERT INTO otp_verifications (email, otp, expires_at) VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL 10 MINUTE))",
            (email, otp)
        )
        mysql.connection.commit()
        cur.close()

        send_email(
            to=email,
            subject="Resend: Your CDGI BookIt OTP",
            body=(
                f"Dear {user['name']},\n\n"
                f"Your new OTP is:\n\n"
                f"    {otp}\n\n"
                f"Valid for 10 minutes.\n\n"
                f"— CDGI BookIt"
            )
        )
        return render_template('verify_otp.html', email=email,
                               success="A new OTP has been sent to your email.")

    except Exception as e:
        return render_template('verify_otp.html', email=email, error=f"Error: {str(e)}")

# ================================================================
#  USER LOGIN
#  Form fields: email, password
# ================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s AND is_active = 1", (email,))
            user = cur.fetchone()
            cur.close()

            if user and check_password_hash(user['password'], password):
                # Session mein save karo
                session['user_id']   = user['id']
                session['user_name'] = user['name']
                session['user_email']= user['email']
                return redirect('/dashboard')
            else:
                return render_template('login.html', error="Invalid email or password")

        except Exception as e:
            return render_template('login.html', error=f"Error: {str(e)}")

    return render_template("login.html")

# ================================================================
#  ADMIN LOGIN
# ================================================================

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email    = request.form['email'].strip().lower()
        password = request.form['password']

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM admins WHERE email = %s AND is_active = 1", (email,))
            admin = cur.fetchone()

            if admin and check_password_hash(admin['password'], password):
                session['admin_id']   = admin['id']
                session['admin_name'] = admin['name']

                # Last login update karo
                cur.execute("UPDATE admins SET last_login = NOW() WHERE id = %s", (admin['id'],))
                mysql.connection.commit()
                cur.close()
                return redirect('/admin')
            else:
                cur.close()
                return render_template('admin_login.html', error="Invalid admin credentials")

        except Exception as e:
            return render_template('admin_login.html', error=f"Error: {str(e)}")

    return render_template('admin_login.html')

# ================================================================
#  LOGOUT
# ================================================================

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect('/')

# ================================================================
#  USER DASHBOARD
#  Halls list dikhata hai — DB se
# ================================================================

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM halls WHERE is_available = 1")
        halls = cur.fetchall()
        cur.close()
    except Exception as e:
        app.logger.error(f"dashboard error: {e}")
        halls = []

    return render_template("dashboard.html",
                           halls=halls,
                           user_name=session.get('user_name', ''))

# ================================================================
#  BOOKING
#  GET  → booking form dikhao
#  POST → booking DB mein save karo
#  Form fields: hall_id, event_date, time_slots (multiple), purpose
# ================================================================

@app.route('/booking', methods=['GET', 'POST'])
@login_required
def booknow():

    def get_halls():
        """Helper — fetch available halls list for re-rendering form on errors."""
        try:
            c = mysql.connection.cursor()
            c.execute("SELECT id, name FROM halls WHERE is_available = 1")
            result = c.fetchall()
            c.close()
            return result
        except Exception:
            return []

    if request.method == 'POST':
        hall_id     = request.form.get('hall_id')
        event_date  = request.form.get('event_date')
        time_slots  = request.form.getlist('time_slots')  # checkboxes → list
        purpose     = request.form.get('purpose', '').strip()

        # Validations — FIX: always pass halls list so dropdown doesn't go empty
        if not hall_id or not event_date or not time_slots or not purpose:
            return render_template('booking.html', halls=get_halls(), error="Please fill in all the fields")

        try:
            booking_date = date.fromisoformat(event_date)
            if booking_date < date.today():
                return render_template('booking.html', halls=get_halls(), error="Booking cannot be made for a past date")
        except ValueError:
            return render_template('booking.html', halls=get_halls(), error="Invalid date format")

        slots_str = ','.join(time_slots)  # "9:00-10:00,10:00-11:00"

        try:
            cur = mysql.connection.cursor()

            # FIX: Validate that hall_id is a real, available hall — reject crafted requests
            cur.execute("SELECT id FROM halls WHERE id=%s AND is_available=1", (hall_id,))
            if not cur.fetchone():
                cur.close()
                return render_template('booking.html', halls=[], error="Selected hall is not available. Please choose a valid hall.")

            # Transaction shuru karo — race condition avoid karne ke liye
            mysql.connection.begin()

            # SELECT FOR UPDATE — concurrent requests ko lock kar deta hai
            # Jab tak ye transaction commit na ho, koi aur request same rows modify nahi kar sakti
            cur.execute(
                """SELECT time_slots FROM bookings
                   WHERE hall_id = %s AND event_date = %s
                   AND status IN ('pending','approved')
                   FOR UPDATE""",
                (hall_id, event_date)
            )
            booked_rows = cur.fetchall()

            # Booked slots collect karo
            booked_slots = set()
            for row in booked_rows:
                for s in row['time_slots'].split(','):
                    booked_slots.add(s.strip())

            # Conflict check karo
            conflict = [s for s in time_slots if s in booked_slots]
            if conflict:
                mysql.connection.rollback()
                cur.close()
                return render_template('booking.html',
                    error=f"Slots already booked: {', '.join(conflict)}")

            # Booking insert karo
            cur.execute(
                """INSERT INTO bookings (user_id, hall_id, event_date, time_slots, purpose)
                   VALUES (%s, %s, %s, %s, %s)""",
                (session['user_id'], hall_id, event_date, slots_str, purpose)
            )
            booking_id = cur.lastrowid

            # User ko notification bhejo
            cur.execute(
                """INSERT INTO notifications (user_id, booking_id, title, message, type)
                   VALUES (%s, %s, %s, %s, 'info')""",
                (session['user_id'], booking_id,
                 "Booking Request Submitted",
                 f"Your booking request for {event_date} has been submitted successfully.")
            )

            mysql.connection.commit()
            cur.close()

            # Confirmation email — user ko bhejo
            send_email(
                to=session.get('user_email', ''),
                subject="Booking Request Received — CDGI BookIt",
                body=(
                    f"Dear {session.get('user_name', 'User')},\n\n"
                    f"Your booking request for {event_date} has been received and is pending admin approval.\n"
                    f"You will be notified once it is reviewed.\n\n"
                    f"— CDGI BookIt"
                )
            )

            return redirect('/my_booking')

        except Exception as e:
            mysql.connection.rollback()
            return render_template('booking.html', error=f"Error: {str(e)}")

    # GET — halls list bhi pass karo select dropdown ke liye
    halls_error = None
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id, name FROM halls WHERE is_available = 1")
        halls = cur.fetchall()
        cur.close()
    except Exception as e:
        app.logger.error(f"booking halls fetch error: {e}")
        halls = []
        halls_error = "Could not load halls. Please refresh or try again."

    selected_hall_id = request.args.get('hall_id', type=int)
    return render_template('booking.html', halls=halls, selected_hall_id=selected_hall_id, error=halls_error)

# ================================================================
#  MY BOOKINGS — User ki saari bookings
# ================================================================

@app.route('/my_booking')
@login_required
def my_bookings():
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """SELECT b.*, h.name as hall_name, h.icon as hall_icon
               FROM bookings b
               JOIN halls h ON b.hall_id = h.id
               WHERE b.user_id = %s
               ORDER BY b.created_at DESC""",
            (session['user_id'],)
        )
        bookings = cur.fetchall()
        cur.close()
    except Exception as e:
        app.logger.error(f"my_bookings error: {e}")
        bookings = []

    return render_template('my_booking.html', bookings=bookings)

# ================================================================
#  BOOKING CANCEL — User apni pending booking cancel kar sake
# ================================================================

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """UPDATE bookings SET status='cancelled'
               WHERE id=%s AND user_id=%s AND status='pending'""",
            (booking_id, session['user_id'])
        )
        mysql.connection.commit()

        # FIX: Check if any row was actually updated — rowcount 0 means booking was not pending or not owned by user
        if cur.rowcount == 0:
            cur.close()
            from flask import flash
            flash("Booking could not be cancelled. It may have already been approved, rejected, or cancelled.", "warning")
            return redirect('/my_booking')

        cur.execute(
            """INSERT INTO notifications (user_id, booking_id, title, message, type)
               VALUES (%s, %s, 'Booking Cancelled', 'You have cancelled your booking.', 'warning')""",
            (session['user_id'], booking_id)
        )
        mysql.connection.commit()
        cur.close()
        from flask import flash
        flash("Your booking has been cancelled successfully.", "success")
    except Exception as e:
        app.logger.error(f"cancel_booking error: {e}")

    return redirect('/my_booking')

# ================================================================
#  PROFILE — User apna profile dekhe
# ================================================================

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    success = None
    error   = None

    if request.method == 'POST':
        name         = request.form.get('name', '').strip()
        phone        = request.form.get('phone', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm      = request.form.get('confirm_password', '')

        if len(name) < 3:
            error = "Name must be at least 3 characters long"
        elif len(phone) != 10 or not phone.isdigit():
            error = "Phone number must be 10 digits"
        elif new_password and not current_password:
            # FIX: Block password change if old password not provided
            error = "Please enter your current password to set a new one"
        elif new_password and len(new_password) < 6:
            error = "New password must be at least 6 characters"
        elif new_password and new_password != confirm:
            error = "Passwords don't match"
        else:
            try:
                cur = mysql.connection.cursor()

                if new_password:
                    # FIX: Verify old password before allowing update
                    cur.execute("SELECT password FROM users WHERE id=%s", (session['user_id'],))
                    user_row = cur.fetchone()
                    if not user_row or not check_password_hash(user_row['password'], current_password):
                        cur.close()
                        error = "Current password is incorrect"
                    else:
                        hashed = generate_password_hash(new_password)
                        cur.execute("UPDATE users SET name=%s, phone=%s, password=%s WHERE id=%s",
                                    (name, phone, hashed, session['user_id']))
                        mysql.connection.commit()
                        session['user_name'] = name
                        cur.close()
                        success = "Profile successfully updated"
                else:
                    cur.execute("UPDATE users SET name=%s, phone=%s WHERE id=%s",
                                (name, phone, session['user_id']))
                    mysql.connection.commit()
                    session['user_name'] = name
                    cur.close()
                    success = "Profile successfully updated"
            except Exception as e:
                error = f"Error: {str(e)}"

    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
        user = cur.fetchone()
        cur.execute("SELECT status, COUNT(*) as count FROM bookings WHERE user_id=%s GROUP BY status",
                    (session['user_id'],))
        stats = {row['status']: row['count'] for row in cur.fetchall()}
        cur.close()
    except Exception as e:
        app.logger.error(f"profile fetch error: {e}")
        user  = {}
        stats = {}

    return render_template("profile.html", user=user, stats=stats,
                           success=success, error=error)
# ================================================================
#  NOTIFICATIONS
# ================================================================

@app.route('/notification')
@login_required
def notification():
    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC",
            (session['user_id'],)
        )
        notifs = cur.fetchall()

        # FIX: Only mark as read AFTER successfully fetching — so if fetch fails, unread count stays correct
        if notifs:
            cur.execute(
                "UPDATE notifications SET is_read=1 WHERE user_id=%s AND is_read=0",
                (session['user_id'],)
            )
            mysql.connection.commit()
        cur.close()
    except Exception as e:
        app.logger.error(f"notification error: {e}")
        notifs = []

    return render_template("notification.html", notifications=notifs)

# ================================================================
#  ADMIN DASHBOARD
# ================================================================

@app.route('/admin')
@admin_required
def admin():
    try:
        cur = mysql.connection.cursor()

        # Saari bookings with user + hall details
        cur.execute(
            """SELECT b.*, u.name as user_name, u.email as user_email,
                      u.department, h.name as hall_name
               FROM bookings b
               JOIN users u ON b.user_id = u.id
               JOIN halls  h ON b.hall_id  = h.id
               ORDER BY b.created_at DESC"""
        )
        bookings = cur.fetchall()

        # Stats cards ke liye
        cur.execute("SELECT COUNT(*) as total FROM bookings")
        total = cur.fetchone()['total']

        cur.execute("SELECT COUNT(*) as pending FROM bookings WHERE status='pending'")
        pending = cur.fetchone()['pending']

        cur.execute("SELECT COUNT(*) as approved FROM bookings WHERE status='approved'")
        approved = cur.fetchone()['approved']

        cur.execute("SELECT COUNT(*) as cancelled FROM bookings WHERE status='cancelled'")
        cancelled = cur.fetchone()['cancelled']

        cur.execute("SELECT COUNT(*) as rejected FROM bookings WHERE status='rejected'")
        rejected = cur.fetchone()['rejected']

        cur.execute("SELECT COUNT(*) as users FROM users")
        total_users = cur.fetchone()['users']

        # Venue utilization — har hall ke liye approved bookings count
        cur.execute("""
            SELECT h.name, h.id,
                   COUNT(b.id) as booking_count
            FROM halls h
            LEFT JOIN bookings b ON h.id = b.hall_id
            AND b.status = 'approved'
            GROUP BY h.id, h.name
        """)
        hall_stats = cur.fetchall()

        # Aaj ki bookings — schedule ke liye
        cur.execute("""
            SELECT b.time_slots, b.purpose, h.name as hall_name
            FROM bookings b
            JOIN halls h ON b.hall_id = h.id
            WHERE b.event_date = CURDATE()
            AND b.status = 'approved'
            ORDER BY h.id
        """)
        today_bookings = cur.fetchall()

        # Total approved bookings (monthly throughput)
        cur.execute("SELECT COUNT(*) as monthly FROM bookings WHERE MONTH(created_at) = MONTH(NOW()) AND YEAR(created_at) = YEAR(NOW())")
        monthly = cur.fetchone()['monthly']

        cur.execute("SELECT COUNT(*) as total_halls FROM halls WHERE is_available = 1")
        total_halls = cur.fetchone()['total_halls']

        cur.close()
    except Exception as e:
        app.logger.error(e)
        bookings    = []
        total       = pending = approved = cancelled = rejected = total_users = 0
        hall_stats  = []
        today_bookings = []
        monthly     = 0
        total_halls = 0

    return render_template("admin.html",
                           bookings=bookings,
                           total=total,
                           pending=pending,
                           approved=approved,
                           cancelled=cancelled,
                           rejected=rejected,
                           total_users=total_users,
                           hall_stats=hall_stats,
                           today_bookings=today_bookings,
                           monthly=monthly,
                           total_halls=total_halls,
                           today_date=datetime.now().strftime('%A, %b %d'),
                           admin_name=session.get('admin_name',''))

# ================================================================
#  ADMIN — APPROVE BOOKING
# ================================================================

@app.route('/approve_booking/<int:booking_id>', methods=['POST'])
@admin_required
def approve_booking(booking_id):
    remark = request.form.get('remark', '')
    try:
        cur = mysql.connection.cursor()

        # FIX: Only allow approving a 'pending' booking — prevents overwriting cancelled/rejected status
        cur.execute("SELECT status FROM bookings WHERE id=%s", (booking_id,))
        booking_check = cur.fetchone()
        if not booking_check or booking_check['status'] != 'pending':
            cur.close()
            return redirect('/admin')

        cur.execute(
            """UPDATE bookings
               SET status='approved', admin_remark=%s,
                   reviewed_by=%s, reviewed_at=NOW()
               WHERE id=%s AND status='pending'""",
            (remark, session['admin_id'], booking_id)
        )

        # User ka user_id aur email nikalo
        cur.execute("""
            SELECT b.user_id, b.event_date, b.time_slots, b.purpose,
                   u.email as user_email, u.name as user_name,
                   h.name as hall_name
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN halls  h ON b.hall_id  = h.id
            WHERE b.id = %s
        """, (booking_id,))
        b = cur.fetchone()

        if b:
            cur.execute(
                """INSERT INTO notifications (user_id, booking_id, title, message, type)
                   VALUES (%s,%s,'Booking Approved! ✅',
                   %s,'success')""",
                (b['user_id'], booking_id,
                 f"Your booking for {b['event_date']} has been successfully approved. The hall is reserved for your use.")
            )

        mysql.connection.commit()
        cur.close()

        # Email bhejo user ko
        if b:
            remark_line = f"Admin note: {remark}\n" if remark else ""
            send_email(
                to=b['user_email'],
                subject="Your Booking is Approved ✅ — CDGI BookIt",
                body=(
                    f"Dear {b['user_name']},\n\n"
                    f"Great news! Your booking has been approved.\n\n"
                    f"  Hall    : {b['hall_name']}\n"
                    f"  Date    : {b['event_date']}\n"
                    f"  Slots   : {b['time_slots']}\n"
                    f"  Purpose : {b['purpose']}\n"
                    f"{remark_line}"
                    f"\nThe hall is reserved for your use. Please arrive on time.\n\n"
                    f"— CDGI BookIt"
                )
            )

    except Exception as e:
        app.logger.error(f"approve_booking error: {e}")
    return redirect('/admin')

# ================================================================
#  ADMIN — REJECT BOOKING
# ================================================================

@app.route('/reject_booking/<int:booking_id>', methods=['POST'])
@admin_required
def reject_booking(booking_id):
    remark = request.form.get('remark', '')
    try:
        cur = mysql.connection.cursor()

        # FIX: Only allow rejecting a 'pending' booking — prevents overwriting cancelled/approved status
        cur.execute("SELECT status FROM bookings WHERE id=%s", (booking_id,))
        booking_check = cur.fetchone()
        if not booking_check or booking_check['status'] != 'pending':
            cur.close()
            return redirect('/admin')

        cur.execute(
            """UPDATE bookings
               SET status='rejected', admin_remark=%s,
                   reviewed_by=%s, reviewed_at=NOW()
               WHERE id=%s AND status='pending'""",
            (remark, session['admin_id'], booking_id)
        )
        cur.execute("""
            SELECT b.user_id, b.event_date, b.time_slots, b.purpose,
                   u.email as user_email, u.name as user_name,
                   h.name as hall_name
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN halls  h ON b.hall_id  = h.id
            WHERE b.id = %s
        """, (booking_id,))
        b = cur.fetchone()

        if b:
            reason_text = f" Reason: {remark}" if remark else ""
            cur.execute(
                """INSERT INTO notifications (user_id, booking_id, title, message, type)
                   VALUES (%s,%s,'Booking Rejected ❌',%s,'error')""",
                (b['user_id'], booking_id,
                 f"We regret to inform you that your booking for {b['event_date']} was not approved.{reason_text}")
            )

        mysql.connection.commit()
        cur.close()

        # Email bhejo user ko
        if b:
            reason_line = f"  Reason  : {remark}\n" if remark else ""
            send_email(
                to=b['user_email'],
                subject="Booking Request Rejected — CDGI BookIt",
                body=(
                    f"Dear {b['user_name']},\n\n"
                    f"We regret to inform you that your booking request could not be approved.\n\n"
                    f"  Hall    : {b['hall_name']}\n"
                    f"  Date    : {b['event_date']}\n"
                    f"  Slots   : {b['time_slots']}\n"
                    f"  Purpose : {b['purpose']}\n"
                    f"{reason_line}"
                    f"\nYou may submit a new request for a different date or time slot.\n\n"
                    f"— CDGI BookIt"
                )
            )

    except Exception as e:
        app.logger.error(f"reject_booking error: {e}")
    return redirect('/admin')

# ================================================================
#  ADMIN — HALLS PAGE
# ================================================================

@app.route('/admin_halls')
@admin_required
def admin_halls():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM halls")
        halls = cur.fetchall()
        cur.close()
    except Exception as e:
        app.logger.error(e)
        halls = []
    return render_template("admin_halls.html", halls=halls, admin_name=session.get('admin_name',''))

# ================================================================
#  ADMIN — USERS PAGE
# ================================================================

@app.route('/admin_users')
@admin_required
def admin_users():
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
        cur.close()
    except Exception as e:
        app.logger.error(e)
        users = []
    return render_template("admin_users.html", users=users, admin_name=session.get('admin_name',''))

# ================================================================
#  ADMIN — ADD HALL
# ================================================================

@app.route('/add_hall', methods=['POST'])
@admin_required
def add_hall():
    from flask import flash
    name     = request.form.get('name', '').strip()
    capacity = request.form.get('capacity', '').strip()
    location = request.form.get('location', '').strip()
    icon     = request.form.get('icon', '🏛️').strip()

    # FIX: Flash error instead of silently redirecting so admin knows what went wrong
    if not name or not capacity or not location:
        flash("All fields (name, capacity, location) are required.", "danger")
        return redirect('/admin_halls')

    try:
        capacity = int(capacity)
        if capacity <= 0:
            flash("Capacity must be a positive number.", "danger")
            return redirect('/admin_halls')
    except ValueError:
        flash("Capacity must be a valid number.", "danger")
        return redirect('/admin_halls')

    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "INSERT INTO halls (name, capacity, location, icon) VALUES (%s, %s, %s, %s)",
            (name, capacity, location, icon)
        )
        mysql.connection.commit()
        cur.close()
        flash(f"Hall '{name}' added successfully.", "success")
    except Exception as e:
        app.logger.error(f"add_hall error: {e}")
        flash(f"Could not add hall: {str(e)}", "danger")

    return redirect('/admin_halls')

# ================================================================
#  ADMIN — EDIT HALL
# ================================================================

@app.route('/edit_hall/<int:hall_id>', methods=['POST'])
@admin_required
def edit_hall(hall_id):
    name     = request.form.get('name', '').strip()
    capacity = request.form.get('capacity', '').strip()
    location = request.form.get('location', '').strip()
    icon     = request.form.get('icon', '🏛️').strip()

    if not name or not capacity or not location:
        return redirect('/admin_halls')

    try:
        capacity = int(capacity)
        if capacity <= 0:
            return redirect('/admin_halls')
    except ValueError:
        return redirect('/admin_halls')

    try:
        cur = mysql.connection.cursor()
        cur.execute(
            "UPDATE halls SET name=%s, capacity=%s, location=%s, icon=%s WHERE id=%s",
            (name, capacity, location, icon, hall_id)
        )
        mysql.connection.commit()
        cur.close()
    except Exception as e:
        app.logger.error(f"edit_hall error: {e}")

    return redirect('/admin_halls')

# ================================================================
#  ADMIN — TOGGLE HALL AVAILABILITY (available ↔ unavailable)
# ================================================================

@app.route('/toggle_hall/<int:hall_id>', methods=['POST'])
@admin_required
def toggle_hall(hall_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT is_available FROM halls WHERE id=%s", (hall_id,))
        hall = cur.fetchone()
        if hall:
            new_status = 0 if hall['is_available'] else 1

            # FIX: Block disabling if there are pending/approved future bookings for this hall
            if new_status == 0:
                cur.execute(
                    """SELECT COUNT(*) as active_count FROM bookings
                       WHERE hall_id=%s AND status IN ('pending','approved')
                       AND event_date >= CURDATE()""",
                    (hall_id,)
                )
                result = cur.fetchone()
                if result and result['active_count'] > 0:
                    cur.close()
                    from flask import flash
                    flash(f"Cannot disable hall: {result['active_count']} active/upcoming booking(s) exist. Resolve them first.", "danger")
                    return redirect('/admin_halls')

            cur.execute("UPDATE halls SET is_available=%s WHERE id=%s", (new_status, hall_id))
            mysql.connection.commit()
        cur.close()
    except Exception as e:
        app.logger.error(f"toggle_hall error: {e}")

    return redirect('/admin_halls')

# ================================================================
#  ADMIN — TOGGLE USER ACTIVE/INACTIVE
# ================================================================

@app.route('/toggle_user/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user(user_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT is_active FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()
        if user:
            new_status = 0 if user['is_active'] else 1
            cur.execute("UPDATE users SET is_active=%s WHERE id=%s", (new_status, user_id))
            mysql.connection.commit()

            # FIX: If deactivating, remove any active session for this user so they are logged out immediately
            if new_status == 0:
                # Flask's default cookie sessions can't be invalidated server-side directly,
                # but we store user_id in session — if the logged-in user is this user, clear their session.
                # For full server-side invalidation, a session store (e.g. Flask-Session) would be needed.
                if session.get('user_id') == user_id:
                    session.clear()

        cur.close()
    except Exception as e:
        app.logger.error(f"toggle_user error: {e}")

    return redirect('/admin_users')

# ================================================================
#  CHECK AVAILABILITY — AJAX endpoint
# ================================================================

@app.route('/check_availability')
@login_required
def check_availability():
    hall_id    = request.args.get('hall_id')
    event_date = request.args.get('date')

    if not hall_id or not event_date:
        return jsonify({'error': 'Missing params'}), 400

    try:
        cur = mysql.connection.cursor()
        cur.execute(
            """SELECT time_slots FROM bookings
               WHERE hall_id=%s AND event_date=%s
               AND status IN ('pending','approved')""",
            (hall_id, event_date)
        )
        rows = cur.fetchall()
        cur.close()

        booked_slots = set()
        for row in rows:
            for slot in row['time_slots'].split(','):
                booked_slots.add(slot.strip())

        return jsonify({'booked_slots': list(booked_slots)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/admin_bookings')
@admin_required
def admin_bookings():
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT b.*, u.name as user_name, u.department,
                   h.name as hall_name
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            JOIN halls h ON b.hall_id = h.id
            ORDER BY b.created_at DESC
        """)
        bookings = cur.fetchall()
        cur.close()
    except Exception as e:
        bookings = []
    return render_template('admin_bookings.html',
                           bookings=bookings,
                           admin_name=session.get('admin_name',''))

# ================================================================

if __name__ == "__main__":
    app.run(debug=True)