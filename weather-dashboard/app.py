from flask import Flask, render_template, jsonify
import psycopg2

app = Flask(__name__)

# =========================
# 🔗 POSTGRES CONFIG
# =========================
DB_CONFIG = dict(
    dbname="iot_db",
    user="admin",
    password="3415",
    host="localhost",
    port="5432"
)


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def to_float(value):
    """Converte Decimal (retornado pelo psycopg2 para colunas NUMERIC) para
    float puro. O jsonify do Flask serializa Decimal como STRING, não como
    número, o que quebra qualquer .toFixed() no JavaScript. None vira None
    (json null), preservado normalmente."""
    return float(value) if value is not None else None


# =========================
# 🏠 HOME
# =========================
@app.route("/")
def index():
    return render_template("index.html")


# =========================
# 📊 API DADOS REAIS
# =========================
@app.route("/data")
def data():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT temperatura, umidade, pressao_atm, data_hora
                       FROM sensores
                       ORDER BY id DESC
                           LIMIT 20
                       """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    rows.reverse()

    return jsonify({
        "temperatura": [to_float(r[0]) for r in rows],
        "umidade": [to_float(r[1]) for r in rows],
        "pressao": [to_float(r[2]) for r in rows],
        "tempo": [str(r[3]) for r in rows]
    })


# =========================
# 🔮 API PREVISÕES
# =========================
@app.route("/predictions")
def predictions():
    """Retorna a previsão mais recente para cada horizonte (1h, 2h, 3h)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT DISTINCT ON (horizonte_horas)
                           horizonte_horas, timestamp_previsto, temperatura_prevista,
                           umidade_prevista, pressao_prevista
                       FROM previsoes
                       ORDER BY horizonte_horas, gerado_em DESC
                       """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    rows.sort(key=lambda r: r[0])

    return jsonify({
        "horizontes": [r[0] for r in rows],
        "tempo": [str(r[1]) for r in rows],
        "temperatura": [to_float(r[2]) for r in rows],
        "umidade": [to_float(r[3]) for r in rows],
        "pressao": [to_float(r[4]) for r in rows],
    })


# =========================
# 🚀 START
# =========================
if __name__ == "__main__":
    app.run(debug=True)