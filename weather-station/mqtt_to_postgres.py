
import paho.mqtt.client as mqtt
import psycopg2
import json
from datetime import datetime

# =========================
# POSTGRESQL CONFIG
# =========================
DB_CONFIG = {
    "dbname": "iot_db",
    "user": "admin",
    "password": "3415",
    "host": "localhost",
    "port": 5432
}

# =========================
# MQTT CONFIG
# =========================
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "weather/#"


# =========================
# CALLBACK CONEXÃO MQTT
# =========================
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado ao MQTT com sucesso")
        client.subscribe(MQTT_TOPIC)
        print(f"📡 Inscrito no tópico: {MQTT_TOPIC}")
    else:
        print("❌ Falha na conexão MQTT. Código:", rc)


# =========================
# CALLBACK MENSAGEM
# =========================
def on_message(client, userdata, msg):
    conn = None
    topico = msg.topic
    payload = msg.payload.decode("utf-8")

    print(f"📩 Recebido: {topico} -> {payload}")

    try:
        data = json.loads(payload)

        temperatura = data.get("temperature_dht11")
        umidade = data.get("humidity_dht11")
        pressao_atm = data.get("pressure_bmp280")

        agora_local = datetime.now()

        # Abre uma conexão válida para esta mensagem
        conn = psycopg2.connect(**DB_CONFIG)

        # O cursor é criado e fechado automaticamente
        with conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO sensores
                    (topico, mensagem, temperatura, umidade,
                     data_hora, pressao_atm)
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

        print(
            f"💾 Dados salvos no PostgreSQL "
            f"({agora_local.strftime('%d/%m/%Y %H:%M:%S')})"
        )

    except json.JSONDecodeError:
        print("⚠️ Payload não é JSON válido:", payload)

    except psycopg2.Error as e:
        print("❌ Erro no PostgreSQL:", e)

    except Exception as e:
        print("❌ Erro ao processar mensagem:", e)

    finally:
        if conn is not None:
            conn.close()


# =========================
# SETUP MQTT CLIENT
# =========================
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print("⏳ Aguardando mensagens MQTT...")
    client.loop_forever()

except KeyboardInterrupt:
    print("\n🛑 Encerrando o consumidor MQTT...")

except Exception as e:
    print("❌ Erro na conexão MQTT:", e)

finally:
    client.disconnect()
    client.loop_stop()
