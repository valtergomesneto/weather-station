from flask import Flask, render_template, jsonify
import psycopg2

app = Flask(__name__)

# =========================
# 🔗 POSTGRES CONFIG
# =========================
conn = psycopg2.connect(
    dbname="iot_db",
    user="admin",
    password="3415",
    host="localhost",
    port="5432"
)

cursor = conn.cursor()

# =========================
# 🏠 HOME
# =========================
@app.route("/")
def index():
    return render_template("index.html")

# =========================
# 📊 API DADOS
# =========================
@app.route("/data")
def data():
    cursor.execute("""
        SELECT temperatura, umidade, data_hora
        FROM sensores
        ORDER BY id DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    rows.reverse()

    return jsonify({
        "temperatura": [r[0] for r in rows],
        "umidade": [r[1] for r in rows],
        "tempo": [str(r[2]) for r in rows]
    })

# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    app.run(debug=True)