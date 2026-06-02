#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

#define DHTPIN 4
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);

// WIFI
const char* ssid = "Loading-Ext";
const char* password = "9C2KC2200GR118580&v";

// MQTT
const char* mqtt_server = "192.168.0.250";

WiFiClient espClient;
PubSubClient client(espClient);

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

  Serial.println("");
  Serial.println("WiFi conectado");
  Serial.print("IP ESP32: ");
  Serial.println(WiFi.localIP());
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

  float temperatura = dht.readTemperature();
  float umidade = dht.readHumidity();

  if (isnan(temperatura) || isnan(umidade)) {
    Serial.println("Erro leitura DHT11");
    return;
  }

  String payload = "{";
  payload += "\"temperature\":";
  payload += String(temperatura);
  payload += ",";
  payload += "\"humidity\":";
  payload += String(umidade);
  payload += "}";

  Serial.println(payload);

  client.publish(
      "weather/data",
      payload.c_str()
  );

  delay(10000);
}