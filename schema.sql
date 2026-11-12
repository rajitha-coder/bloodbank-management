CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','donor','patient')),
  blood_group TEXT, phone TEXT, city TEXT, age INTEGER, gender TEXT,
  status TEXT DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS inventory(
  blood_group TEXT PRIMARY KEY,
  units INTEGER NOT NULL DEFAULT 0 CHECK(units >= 0)
);
CREATE TABLE IF NOT EXISTS donations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  donor_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  blood_group TEXT NOT NULL, units INTEGER NOT NULL, donated_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  patient TEXT NOT NULL, blood_group TEXT NOT NULL, units INTEGER NOT NULL,
  hospital TEXT NOT NULL, city TEXT, phone TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
  requested_on TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  message TEXT NOT NULL, created_on TEXT NOT NULL
);
