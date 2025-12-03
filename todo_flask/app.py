from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
from matplotlib.backends.backend_pdf import PdfPages
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin

app = Flask(__name__)
app.secret_key = "change_this_to_secure_random_value"  
DATABASE = "tasks.db"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    """)
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'").fetchall()
    if not tables:
        conn.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority INTEGER DEFAULT 3,
            category TEXT DEFAULT 'General',
            done INTEGER DEFAULT 0,
            created_at TEXT,
            completed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
    conn.commit()
    conn.close()

init_db()

class User(UserMixin):
    def __init__(self, id_, username, password_hash):
        self.id = id_
        self.username = username
        self.password_hash = password_hash

    @staticmethod
    def get(user_id):
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if row:
            return User(row['id'], row['username'], row['password_hash'])
        return None

    @staticmethod
    def find_by_username(username):
        conn = get_db_connection()
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if row:
            return User(row['id'], row['username'], row['password_hash'])
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if not username or not password:
            flash("Username and password required.", "danger")
            return redirect(url_for('register'))
        if User.find_by_username(username):
            flash("Username already taken.", "warning")
            return redirect(url_for('register'))
        pw_hash = generate_password_hash(password)
        conn = get_db_connection()
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pw_hash))
        conn.commit()
        conn.close()
        flash("Account created - please log in.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.find_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for('index'))
        flash("Invalid credentials.", "danger")
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    category_filter = request.args.get('category')
    status_filter = request.args.get('status')

    conn = get_db_connection()
    sql = "SELECT * FROM tasks WHERE user_id=?"
    params = [current_user.id]

    if category_filter:
        sql += " AND category=?"
        params.append(category_filter)
    if status_filter == 'done':
        sql += " AND done=1"
    elif status_filter == 'incomplete':
        sql += " AND done=0"

    sql += " ORDER BY priority, id"
    tasks = conn.execute(sql, params).fetchall()
    conn.close()

    conn = get_db_connection()
    categories = [row['category'] for row in conn.execute("SELECT DISTINCT category FROM tasks WHERE user_id=?", (current_user.id,)).fetchall()]
    conn.close()

    return render_template('index.html', tasks=tasks, categories=categories)

@app.route('/add', methods=['POST'])
@login_required
def add_task():
    title = request.form['title']
    description = request.form.get('description', '')
    priority = int(request.form.get('priority', 3))
    category = request.form.get('category', 'General')
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO tasks (user_id, title, description, priority, category, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (current_user.id, title, description, priority, category)
    )
    conn.commit()
    conn.close()
    flash("Task added.", "success")
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit_task(id):
    conn = get_db_connection()
    task = conn.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (id, current_user.id)).fetchone()
    conn.close()
    if not task:
        flash("Task not found.", "danger")
        return redirect(url_for('index'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        priority = int(request.form.get('priority', 3))
        category = request.form.get('category', 'General')
        conn = get_db_connection()
        conn.execute("UPDATE tasks SET title=?, description=?, priority=?, category=? WHERE id=? AND user_id=?",
                     (title, description, priority, category, id, current_user.id))
        conn.commit()
        conn.close()
        flash("Task updated.", "success")
        return redirect(url_for('index'))

    conn = get_db_connection()
    categories = [row['category'] for row in conn.execute("SELECT DISTINCT category FROM tasks WHERE user_id=?", (current_user.id,)).fetchall()]
    conn.close()

    return render_template('edit_task.html', task=task, categories=categories)

@app.route('/done/<int:id>')
@login_required
def mark_done(id):
    conn = get_db_connection()
    conn.execute("UPDATE tasks SET done=1, completed_at=datetime('now') WHERE id=? AND user_id=?", (id, current_user.id))
    conn.commit()
    conn.close()
    flash("Task marked done.", "info")
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_task(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (id, current_user.id))
    conn.commit()
    conn.close()
    flash("Task deleted.", "info")
    return redirect(url_for('index'))

@app.route('/analysis')
@login_required
def analysis():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM tasks WHERE user_id = ?", conn, params=(current_user.id,))
    conn.close()
    if df.empty:
        flash("No tasks to analyze.", "warning")
        return render_template('analysis.html', category_plot=None, done_plot=None, trend_plot=None)
    os.makedirs(STATIC_DIR, exist_ok=True)

    for col in ['created_at','completed_at']:
        if col not in df.columns:
            df[col] = ""

    plt.figure(figsize=(6,4))
    sns.countplot(data=df, x='category', palette='pastel')
    plt.title("Tasks per Category")
    plt.ylabel("Count")
    category_plot = os.path.join(STATIC_DIR, f"category_plot_{current_user.id}.png")
    plt.savefig(category_plot)
    plt.close()

    plt.figure(figsize=(5,5))
    df['done'].replace({0:'Incomplete',1:'Complete'}).value_counts().plot(kind='pie', autopct='%1.1f%%', colors=['lightcoral','lightgreen'])
    plt.title("Completed vs Incomplete")
    done_plot = os.path.join(STATIC_DIR, f"done_plot_{current_user.id}.png")
    plt.savefig(done_plot)
    plt.close()

    trend_plot = None
    if 'completed_at' in df.columns and df['completed_at'].notna().any():
        df_completed = df[df['done']==1].copy()
        df_completed['completed_at'] = pd.to_datetime(df_completed['completed_at'])
        trend = df_completed.groupby(df_completed['completed_at'].dt.date).size()
        plt.figure(figsize=(7,4))
        trend.plot(kind='line', marker='o')
        plt.title("Tasks Completed Over Time"); plt.xlabel("Date"); plt.ylabel("Number")
        trend_plot = os.path.join(STATIC_DIR, f"trend_plot_{current_user.id}.png")
        plt.savefig(trend_plot)
        plt.close()

    return render_template('analysis.html',
                           category_plot=os.path.basename(category_plot),
                           done_plot=os.path.basename(done_plot),
                           trend_plot=(os.path.basename(trend_plot) if trend_plot else None))

@app.context_processor
def inject_user():
    return dict(current_user=current_user)

if __name__ == '__main__':
    app.run(debug=True)
