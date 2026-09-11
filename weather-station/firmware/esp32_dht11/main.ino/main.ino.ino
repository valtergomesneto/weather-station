#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>

#define DHTPIN 4
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);

// WIFI
const char* ssid = "Loading-Ext";
const char* password = "9C2KC2200GR118580&v";

// MQTT
const char* mqtt_server = "192.168.0.103";

WiFiClient espClient;
PubSubClient client(espClient);

unsigned long ultimoEnvio = 0;
const unsigned long intervaloEnvio = 30000; // 30 segundos

void setup_wifi() {

  delay(10);

  Serial.println();
  Serial.print("Conectando em ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();
  Serial.println("WiFi conectado");
  Serial.print("IP ESP32: ");
  Serial.println(WiFi.localIP());

  // NTP - Horário do Brasil (UTC-3)
  configTime(
    -3 * 3600,
    0,
    "pool.ntp.org",
    "time.nist.gov"
  );

  Serial.print("Sincronizando horário");

  struct tm timeinfo;

  while (!getLocalTime(&timeinfo)) {
    Serial.print(".");
    delay(1000);
  }

  Serial.println();
  Serial.println("Horário sincronizado!");
}

void reconnect() {

  while (!client.connected()) {

    Serial.print("Conectando MQTT...");

    if (client.connect("ESP32Weather")) {

      Serial.println(" conectado");

    } else {

      Serial.print(" erro=");
      Serial.print(client.state());
      Serial.println(" tentando novamente");

      delay(5000);
    }
  }
}

void setup() {

  Serial.begin(115200);

  dht.begin();

  setup_wifi();

  client.setServer(mqtt_server, 1883);
}

void loop() {

  if (!client.connected()) {
    reconnect();
  }

  client.loop();

  unsigned long agora = millis();

  if (agora - ultimoEnvio >= intervaloEnvio) {

    ultimoEnvio = agora;

    float temperatura = dht.readTemperature();
    float umidade = dht.readHumidity();

    if (isnan(temperatura) || isnan(umidade)) {
      Serial.println("Erro leitura DHT11");
      return;
    }

    String payload = "{";
    payload += "\"temperature\":";
    payload += String(temperatura, 1);
    payload += ",";
    payload += "\"humidity\":";
    payload += String(umidade, 1);
    payload += "}";

    struct tm timeinfo;

    if (getLocalTime(&timeinfo)) {

      char dataHora[30];

      strftime(
        dataHora,
        sizeof(dataHora),
        "%d/%m/%Y %H:%M:%S",
        &timeinfo
      );

      Serial.print("[");
      Serial.print(dataHora);
      Serial.print("] ");

      Serial.println(payload);

    } else {

      Serial.println(payload);

    }

    client.publish(
      "weather/data",
      payload.c_str()
    );
  }
}