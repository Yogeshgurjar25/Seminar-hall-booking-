-- ================================================================
--  CDGI SEMINAR HALL BOOKING PORTAL
--  File: database_setup.sql
--  Kaise chalayein:
--    1. MySQL Workbench ya phpMyAdmin kholo
--    2. Ye poora file paste karo aur Run karo
--    3. 'cdgi_booking' database + saari tables ban jayengi
-- ================================================================

CREATE DATABASE IF NOT EXISTS cdgi_booking
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cdgi_booking;

-- ================================================================
-- TABLE 1: users
-- Kaun: Faculty / Staff jo register karke login karte hain
-- Form: register.html  → name, email, phone, department, password
-- ================================================================
CREATE TABLE IF NOT EXISTS users (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100)  NOT NULL,
    email        VARCHAR(100)  NOT NULL UNIQUE,   -- @cdgi.edu.in only
    phone        VARCHAR(15)   NOT NULL,
    department   VARCHAR(50)   NOT NULL,          -- CSE, IT, EC, ME, CE
    password     VARCHAR(255)  NOT NULL,          -- hashed — kabhi plain text nahi
    is_active    TINYINT(1)    NOT NULL DEFAULT 0,  -- 0 = unverified; set to 1 after OTP
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                 ON UPDATE CURRENT_TIMESTAMP
);

-- ================================================================
-- TABLE 2: admins
-- Kaun: Admin jo bookings approve/reject karta hai
-- Form: login.html (admin_login route) → email, password
-- ================================================================
CREATE TABLE IF NOT EXISTS admins (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    name         VARCHAR(100)  NOT NULL,
    email        VARCHAR(100)  NOT NULL UNIQUE,
    password     VARCHAR(255)  NOT NULL,          -- hashed
    is_active    TINYINT(1)    NOT NULL DEFAULT 1,
    last_login   DATETIME      DEFAULT NULL,
    created_at   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Default admin — password baad mein hash karke update karo
-- python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('admin123'))"
INSERT INTO admins (name, email, password) VALUES
('CDGI Admin', 'admin@cdgi.edu.in', 'scrypt:32768:8:1$dEiC9UFaK3r0KVaq$23d066893e7b793a265635378560b372b13c4a91804b6a389e192c64673e044daea1f19bdbe30b2bc4a6a0701a256e570e31105a356f6378cd370cfe690a11c3');

-- ================================================================
-- TABLE 3: halls
-- Kaun: Admin manage karta hai; Users dashboard pe dekhte hain
-- Data: dashboard.html ke 3 hall cards se match karta hai
-- ================================================================
CREATE TABLE IF NOT EXISTS halls (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100)  NOT NULL UNIQUE,
    capacity      INT           NOT NULL,
    location      VARCHAR(150)  NOT NULL,
    icon          VARCHAR(20)   DEFAULT '🏛️',   -- emoji for frontend
    is_available  TINYINT(1)    NOT NULL DEFAULT 1,
    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO halls (name, capacity, location, icon) VALUES
('Multipurpose Auditorium', 1000, 'Mechanical Department', '🏟'),
('Seminar Hall 1',          250, 'Ground Floor',          '🏛️'),
('Seminar Hall 2',          200, 'Ground Floor',          '🏛️');

-- ================================================================
-- TABLE 4: bookings
-- Kaun: User booking.html se submit karta hai
-- Form fields: hall (select), event_date, time_slots (checkboxes), purpose
-- Admin booking approve/reject karta hai admin.html se
-- ================================================================
CREATE TABLE IF NOT EXISTS bookings (
    id            INT AUTO_INCREMENT PRIMARY KEY,

    user_id       INT           NOT NULL,
    FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE,

    hall_id       INT           NOT NULL,
    FOREIGN KEY (hall_id)  REFERENCES halls(id) ON DELETE RESTRICT,

    event_date    DATE          NOT NULL,         -- konsi date chahiye

    -- booking.html mein time slots checkboxes hain
    -- selected slots comma-separated store honge: "9:00-10:00,10:00-11:00"
    time_slots    VARCHAR(255)  NOT NULL,

    purpose       TEXT          NOT NULL,         -- textarea se

    status        ENUM('pending','approved','rejected','cancelled')
                  NOT NULL DEFAULT 'pending',

    admin_remark  TEXT          DEFAULT NULL,     -- admin ka comment
    reviewed_by   INT           DEFAULT NULL,
    FOREIGN KEY (reviewed_by) REFERENCES admins(id) ON DELETE SET NULL,
    reviewed_at   DATETIME      DEFAULT NULL,

    created_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                  ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user     (user_id),
    INDEX idx_hall     (hall_id),
    INDEX idx_date     (event_date),
    INDEX idx_status   (status)
);

-- ================================================================
-- TABLE 5: notifications
-- Kaun: Jab admin approve/reject kare to user ko notification jaaye
-- Dikhta hai: notification.html mein
-- ================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT           NOT NULL,
    FOREIGN KEY (user_id)   REFERENCES users(id) ON DELETE CASCADE,
    booking_id  INT           DEFAULT NULL,
    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE SET NULL,
    title       VARCHAR(200)  NOT NULL,
    message     TEXT          NOT NULL,
    type        ENUM('success','error','info','warning') NOT NULL DEFAULT 'info',
    is_read     TINYINT(1)    NOT NULL DEFAULT 0,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_notif (user_id),
    INDEX idx_unread     (is_read)
);

CREATE TABLE IF NOT EXISTS otp_verifications (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    email      VARCHAR(100) NOT NULL,
    otp        VARCHAR(6)   NOT NULL,
    expires_at DATETIME     NOT NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_otp_email (email)
);

-- ================================================================
-- VERIFY — ye run karke check karo
-- ================================================================
SHOW TABLES;