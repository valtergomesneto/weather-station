import paho.mqtt.client as mqtt
import psycopg2
import json
from datetime import datetime

# =========================
# 🔗 POSTGRESQL CONFIG
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
# 📡 MQTT CONFIG
# =========================
MQTT_BROKER = "localhost"   # ou IP do broker
MQTT_PORT = 1883
MQTT_TOPIC = "weather/#"

# =========================
# 🔌 CALLBACK CONEXÃO MQTT
# =========================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado ao MQTT com sucesso")
        client.subscribe(MQTT_TOPIC)
    else:
        print("❌ Falha na conexão MQTT. Código:", rc)

# =========================
# 📥 CALLBACK MENSAGEM
# =========================
def on_message(client, userdata, msg):
    topico = msg.topic
    payload = msg.payload.decode()

    print(f"📩 Recebido: {topico} -> {payload}")

    try:
        # Converter JSON vindo do ESP32
        data = json.loads(payload)

        temperatura = data.get("temperature_dht11")
        umidade = data.get("humidity_dht11")
        pressao_atm = data.get("pressure_bmp280")

        # IMPORTANTE: gravamos o horário explicitamente aqui, em vez de
        # depender do DEFAULT CURRENT_TIMESTAMP da coluna no Postgres.
        # O CURRENT_TIMESTAMP do banco usa o fuso da SESSÃO da conexão,
        # que por padrão vinha em UTC nesta conexão (confirmado via
        # diagnóstico), gravando a hora 3h adiantada em relação ao
        # horário real do Brasil. datetime.now() usa o relógio local
        # do sistema operacional onde este script roda.
        agora_local = datetime.now()

        # Inserir no banco
        cursor.execute(
            """
            INSERT INTO sensores (topico, mensagem, temperatura, umidade, data_hora, pressao_atm) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                topico,
                payload,
                temperatura,
                umidade,
                agora_local,
                pressao_atm

            )
        )

        conn.commit()
        print(f"💾 Dados salvos no PostgreSQL ({agora_local})")

    except json.JSONDecodeError:
        print("⚠️ Payload não é JSON válido:", payload)

    except Exception as e:
        print("❌ Erro ao salvar no banco:", e)

# =========================
# 🚀 SETUP MQTT CLIENT
# =========================
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("⏳ Aguardando mensagens MQTT...")
client.loop_forever()