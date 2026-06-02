import paho.mqtt.client as mqtt
import psycopg2
import json

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

        temperatura = data.get("temperature")
        umidade = data.get("humidity")

        # Inserir no banco
        cursor.execute(
            """
            INSERT INTO sensores (topico, mensagem, temperatura, umidade)
            VALUES (%s, %s, %s, %s)
            """,
            (
                topico,
                payload,
                temperatura,
                umidade
            )
        )

        conn.commit()
        print("💾 Dados salvos no PostgreSQL")

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