import os
import logging
import sqlite3
import smtplib
from email.mime.text import MIMEText

from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, session, flash
)
from flask_cors import CORS

app = Flask(__name__)
# Secret key for session (admin login)
app.secret_key = os.getenv('SECRET_KEY', 'dev_secret')

# Enable CORS
CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)

# DATABASE Connection Helper


def get_db_connection():
    conn = sqlite3.connect('songs.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize a reviewers table for admin-managed dropdown


def init_db():
    conn = get_db_connection()
    conn.execute(
        'CREATE TABLE IF NOT EXISTS reviewers ('
        ' id INTEGER PRIMARY KEY AUTOINCREMENT,'
        ' name TEXT UNIQUE NOT NULL)'
    )
    conn.commit()
    conn.close()


# Initialize on startup
init_db()

# EMAIL Notification Helper


def send_notification(song_id, title, artist, link, reason):
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    sender = os.getenv('SMTP_USER', 'chnewsong@gmail.com')
    password = os.getenv('SMTP_PASS', 'bdixygrkrynjwjxb')
    recipients = ['ryan@cherryhillsfamily.org', 'wcwa@cherryhillsfamily.org']

    survey_link = f'https://chsong-backend.onrender.com/survey/{song_id}'

    html_content = f"""
    <h3>New Song Submission:</h3>
    <p><strong>{title}</strong> by {artist}</p>
    <p>{reason}</p>
    <p><a href="{link}">Listen Here</a></p>
    <p><a href="{survey_link}">Review the Song</a></p>
    """

    msg = MIMEText(html_content, 'html')
    msg['Subject'] = f"New Song Submission: {title}"
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    try:
        logging.info(
            f"Connecting to SMTP {smtp_server}:{smtp_port} as {sender}")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        logging.info("Email sent successfully")
    except Exception as e:
        logging.error("Failed to send email", exc_info=e)

# Routes


@app.route('/')
def index():
    return render_template('submit_song.html')


@app.route('/submit_song', methods=['POST'])
def submit_song():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO songs (title, artist, reason, link) VALUES (?, ?, ?, ?)",
        (data['title'], data['artist'], data['reason'], data['link'])
    )
    conn.commit()
    song_id = cursor.lastrowid
    conn.close()

    send_notification(song_id, data['title'],
                      data['artist'], data['link'], data['reason'])
    return jsonify({'message': 'Song submitted successfully'}), 201


@app.route('/survey/<int:song_id>', methods=['GET'])
def survey(song_id):
    conn = get_db_connection()
    song = conn.execute(
        "SELECT title FROM songs WHERE id = ?", (song_id,)).fetchone()
    reviewers = conn.execute(
        "SELECT name FROM reviewers ORDER BY name").fetchall()
    conn.close()
    song_title = song['title'] if song else 'Unknown Song'
    return render_template(
        'survey.html',
        song_id=song_id,
        song_title=song_title,
        reviewers=[r['name'] for r in reviewers]
    )


@app.route('/submit_survey/<int:song_id>', methods=['POST'])
def submit_survey(song_id):
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO survey_responses (song_id, reviewer, rating, comments) VALUES (?, ?, ?, ?)",
        (song_id, data['reviewer'], data['rating'], data['comments'])
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Survey submitted successfully'}), 200


@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    songs = conn.execute("""
        SELECT songs.*, 
               AVG(survey_responses.rating) AS avg_rating, 
               COUNT(survey_responses.id) AS responses
        FROM songs
        LEFT JOIN survey_responses 
          ON songs.id = survey_responses.song_id
        GROUP BY songs.id
    """).fetchall()
    conn.close()
    return render_template('dashboard.html', songs=songs)


@app.route('/delete_song/<int:song_id>', methods=['POST'])
def delete_song(song_id):
    logging.info(f"Attempting to delete song with ID {song_id}")
    try:
        conn = get_db_connection()
        conn.execute("DELETE FROM survey_responses WHERE song_id = ?", (song_id,))
        conn.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        conn.commit()
        conn.close()
        logging.info(f"Successfully deleted song with ID {song_id}")
    except Exception as e:
        logging.error(f"Error deleting song with ID {song_id}", exc_info=e)
        flash("There was an error deleting the song.", "error")
    # Redirect back to the admin dashboard
    return redirect(url_for('admin_dashboard'))

# --- ADMIN INTERFACE BELOW ---


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('pin') == '2006':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid PIN', 'error')
    return render_template('admin_login.html')


@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    songs = conn.execute("SELECT * FROM songs").fetchall()
    reviewers = conn.execute(
        "SELECT * FROM reviewers ORDER BY name").fetchall()
    conn.close()
    return render_template('admin.html', songs=songs, reviewers=reviewers)


@app.route('/admin/add_reviewer', methods=['POST'])
def add_reviewer():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    name = request.form.get('name', '').strip()
    if name:
        conn = get_db_connection()
        conn.execute(
            "INSERT OR IGNORE INTO reviewers (name) VALUES (?)", (name,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete_reviewer/<int:rev_id>', methods=['POST'])
def delete_reviewer(rev_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    conn.execute("DELETE FROM reviewers WHERE id = ?", (rev_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/update_song/<int:song_id>', methods=['POST'])
def update_song(song_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    data = request.form
    conn = get_db_connection()
    conn.execute(
        "UPDATE songs SET title=?, artist=?, reason=?, link=? WHERE id=?",
        (data['title'], data['artist'], data['reason'], data['link'], song_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
