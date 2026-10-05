"""
Diagnóstico: confere o fuso horário da sessão exatamente como o
mqtt_to_postgres.py a vê (mesma biblioteca, mesma conexão), para
confirmar se o servidor Postgres está usando UTC nessa conexão
mesmo com o DataGrip mostrando America/Sao_Paulo na dele.
"""

import psycopg2
from datetime import datetime

conn = psycopg2.connect(
    dbname="iot_db",
    user="admin",
    password="3415",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

cursor.execute("SHOW timezone;")
print("Fuso da sessão (psycopg2):", cursor.fetchone()[0])

cursor.execute("SELECT CURRENT_TIMESTAMP;")
print("CURRENT_TIMESTAMP (banco, via psycopg2):", cursor.fetchone()[0])

print("Hora local do Python (datetime.now()):", datetime.now())

cursor.close()
conn.close()