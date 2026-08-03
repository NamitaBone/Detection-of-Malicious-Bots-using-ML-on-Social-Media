import psycopg2
from flask import Flask, request, jsonify
from flask_cors import CORS
import hashlib
import joblib
import numpy as np
import random

# ---------------- APP SETUP ----------------
app = Flask(name)
CORS(app, resources={r"/": {"origins": ""}})

# ---------------- DATABASE ----------------
conn = psycopg2.connect(
    dbname="malicious_bot_db",
    user="postgres",
    password="1234",
    host="localhost"
)
cur = conn.cursor()

# ---------------- LOAD MODEL ----------------
model = joblib.load('model/random_forest_model.joblib')

# ---------------- GET USERS ----------------
@app.route('/api/get-users', methods=['POST'])
def get_users():
    data = request.get_json()
    superuser = data.get('superuser')

    if not superuser:
        return jsonify({'error': "Need authorized access"}), 403

    try:
        cur.execute("""
            SELECT email, name, social_media_username, superuser, created_at
            FROM users
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()

        keys = ['email', 'name', 'social_media_username', 'superuser', 'created_at']
        result = [dict(zip(keys, row)) for row in rows]

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- GET METRICS ----------------
@app.route('/api/get-metrics', methods=['POST'])
def get_metrics():
    data = request.get_json()
    email = data.get('email')

    try:
        cur.execute("""
            SELECT username, follower_count, following_count, tweets_posted,
                   engagement_time_minutes, metrics_result, confidence_score
            FROM bot_analysis
            WHERE metrics_by_email = %s
            ORDER BY metrics_time DESC
        """, (email,))
        rows = cur.fetchall()

        keys = ['username', 'follower_count', 'following_count', 'tweets_posted',
                'engagement_time_minutes', 'metrics_result', 'confidence_score']
        result = [dict(zip(keys, row)) for row in rows]

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- SUPER METRICS ----------------
@app.route('/api/get-super-metrics', methods=['POST'])
def get_super_metrics():
    data = request.get_json()
    superuser = data.get('superuser')

    if not superuser:
        return jsonify({'error': "Need authorized access"}), 403

    try:
        cur.execute("""
            SELECT username, follower_count, following_count, tweets_posted,
                   engagement_time_minutes, metrics_result, confidence_score,
                   metrics_by_name, metrics_by_email
            FROM bot_analysis
            ORDER BY metrics_time DESC
        """)
        rows = cur.fetchall()

        keys = ['username', 'follower_count', 'following_count', 'tweets_posted',
                'engagement_time_minutes', 'metrics_result', 'confidence_score',
                'metrics_by_name', 'metrics_by_email']
        result = [dict(zip(keys, row)) for row in rows]

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- PREDICT ----------------
@app.route('/api/predict', methods=['POST'])
def predict():
    try:
        data = request.get_json()

        input_features = [
            data.get('follower_count'),
            data.get('following_count'),
            data.get('tweets_posted'),
            data.get('media_link_tweets'),
            data.get('discussion_count'),
            data.get('engagement_time'),
            data.get('likes_given_tweets'),
            data.get('likes_retweets_shared_content'),
            data.get('likes_replies_comments')
        ]

        if None in input_features:
            return jsonify({'error': 'Missing required input fields'}), 400

        input_array = np.array(input_features).reshape(1, -1)

        prediction = int(model.predict(input_array)[0])
        confidence = round(float(np.max(model.predict_proba(input_array))), 4)

        cs_id = f"CS{''.join(random.choices('0123456789', k=6))}"

        cur.execute("""
            INSERT INTO bot_analysis (
                id, username, follower_count, following_count, tweets_posted,
                media_or_link_tweets, discussion_count, engagement_time_minutes,
                likes_given_to_tweets, likes_retweets_on_shared_content,
                likes_on_replies_or_comments, metrics_by_name, metrics_by_email,
                metrics_result, confidence_score
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            cs_id,
            data.get('username'),
            data.get('follower_count'),
            data.get('following_count'),
            data.get('tweets_posted'),
            data.get('media_link_tweets'),
            data.get('discussion_count'),
            data.get('engagement_time'),
            data.get('likes_given_tweets'),
            data.get('likes_retweets_shared_content'),
            data.get('likes_replies_comments'),
            data.get('metrics_by_name'),
            data.get('metrics_by_email'),
            prediction,
            confidence
        ))

        conn.commit()

        return jsonify({
            'username': data.get('username'),
            'prediction': prediction,
            'confidence': confidence
        })

    except Exception as e:
        return jsonify({'error': f'Prediction failed: {e}'}), 500

# ---------------- FEATURE IMPORTANCE ----------------
@app.route('/api/feature-importance', methods=['GET'])
def feature_importance():
    try:
        feature_names = [
            'Follower Count',
            'Following Count',
            'Tweets Posted',
            'Media/Link Tweets',
            'Discussion Count',
            'Engagement Time',
            'Likes Given to Tweets',
            'Likes/Retweets on Shared Content',
            'Likes on Replies/Comments'
        ]

        importances = model.feature_importances_.tolist()

        data = [
            {"feature": feature_names[i], "importance": round(importances[i], 4)}
            for i in range(len(feature_names))
        ]

        return jsonify(data)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---------------- LOGIN ----------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    cur.execute("SELECT name, social_media_username, email, password, superuser FROM users WHERE email=%s", (email,))
    user = cur.fetchone()

    if user and hashed_password == user[3]:
        return jsonify({
            'message': 'Login successful!',
            'user': {
                'name': user[0],
                'email': user[2],
                'social_media_username': user[1],
                'superuser': user[4]
            }
        })

    return jsonify({'error': 'Invalid credentials'}), 401

# ---------------- REGISTER ----------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()

    hashed_password = hashlib.sha256(data['password'].encode()).hexdigest()

    cur.execute(
        "INSERT INTO users (name, email, password, social_media_username) VALUES (%s,%s,%s,%s)",
        (data['name'], data['email'], hashed_password, data['social_media_username'])
    )
    conn.commit()

    return jsonify({'message': 'Registration successful!'})

# ---------------- RUN APP ----------------
if name == "main":
    app.run(debug=True)