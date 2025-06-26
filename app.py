from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sqlite3
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests, useful for frontend testing

# DATABASE Connection Helper
def get_db_connection():
    conn = sqlite3.connect('songs.db')
    conn.row_factory = sqlite3.Row
    return conn

# EMAIL Notification Helper
def send_notification(song_id, title, artist, link, reason):
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587
    sender = 'chnewsong@gmail.com'
    password = 'bdixygrkrynjwjxb'
    recipients = ['ryan@cherryhillsfamily.org','wcwa@cherryhillsfamily.org']

    # new for a Netlify-hosted front end
    survey_link = f'https://chsong-backend.onrender.com/survey/{song_id}'

    html_content = f"""
    <h3>New Song Submission:</h3>
    <p><strong>{title}</strong> by {artist}</p>
    <p>{reason}</p>
    <a href="{link}">Listen Here</a><br>
    <a href="{survey_link}">Review the Song</a>
    """

    msg = MIMEText(html_content, 'html')
    msg['Subject'] = f"New Song Submission: {title}"
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())

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

    send_notification(song_id, data['title'], data['artist'], data['link'], data['reason'])

    return jsonify({'message': 'Song submitted successfully'}), 201

@app.route('/survey/<int:song_id>', methods=['GET'])
def survey(song_id):
    conn = get_db_connection()
    song = conn.execute("SELECT title FROM songs WHERE id = ?", (song_id,)).fetchone()
    conn.close()
    song_title = song['title'] if song else 'Unknown Song'
    return render_template('survey.html', song_id=song_id, song_title=song_title)

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
    song = conn.execute("SELECT title FROM songs WHERE id = ?", (song_id,)).fetchone()
    conn.close()
    return jsonify({'message': 'Survey submitted successfully'}), 200

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    songs = conn.execute("""
        SELECT songs.*, AVG(survey_responses.rating) as avg_rating, COUNT(survey_responses.id) as responses
        FROM songs LEFT JOIN survey_responses
        ON songs.id = survey_responses.song_id
        GROUP BY songs.id
    """).fetchall()
    conn.close()
    return render_template('dashboard.html', songs=songs)

if __name__ == '__main__':
    app.run(debug=True)