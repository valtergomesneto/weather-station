#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <Adafruit_BMP280.h>
#include <Wire.h>
#include <time.h>

// =====================================================
// DHT11
// =====================================================

#define DHTPIN 4
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);


// =====================================================
// BMP280 - HW-611 E/P280
// =====================================================

Adafruit_BMP280 bmp;


// =====================================================
// WIFI
// =====================================================

const char* ssid = "Loading..._EXT";
const char* password = "9C2KC2200&v";


// =====================================================
// MQTT
// =====================================================

const char* mqtt_server = "192.168.0.103";

WiFiClient espClient;
PubSubClient client(espClient);


// =====================================================
// INTERVALO
// =====================================================

unsigned long ultimoEnvio = 0;

const unsigned long intervaloEnvio = 30000; // 30 segundos


// =====================================================
// WIFI
// =====================================================

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


  // =================================================
  // NTP - Horário do Brasil UTC-3
  // =================================================

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


// =====================================================
// MQTT
// =====================================================

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


// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  // DHT11
  dht.begin();


  // =================================================
  // I2C
  // SDA = GPIO 21
  // SCL = GPIO 22
  // =================================================

  Wire.begin(21, 22);


  // =================================================
  // BMP280
  // =================================================

  if (!bmp.begin(0x76)) {

    Serial.println("BMP280 não encontrado em 0x76.");

    if (!bmp.begin(0x77)) {

      Serial.println("ERRO: BMP280 não encontrado em 0x76 nem 0x77.");

      while (true) {
        delay(1000);
      }

    } else {

      Serial.println("BMP280 encontrado em 0x77.");
    }

  } else {

    Serial.println("BMP280 encontrado em 0x76.");
  }


  // =================================================
  // Configuração do BMP280
  // =================================================

  bmp.setSampling(
    Adafruit_BMP280::MODE_NORMAL,
    Adafruit_BMP280::SAMPLING_X2,  // temperatura
    Adafruit_BMP280::SAMPLING_X16, // pressão
    Adafruit_BMP280::FILTER_X16,
    Adafruit_BMP280::STANDBY_MS_500
  );


  // MQTT
  setup_wifi();

  client.setServer(mqtt_server, 1883);
}


// =====================================================
// LOOP
// =====================================================

void loop() {

  // =================================================
  // MQTT
  // =================================================

  if (!client.connected()) {

    reconnect();
  }

  client.loop();


  // =================================================
  // INTERVALO DE LEITURA
  // =================================================

  unsigned long agora = millis();


  if (agora - ultimoEnvio >= intervaloEnvio) {

    ultimoEnvio = agora;


    // =================================================
    // DHT11
    // =================================================

    float temperaturaDHT = dht.readTemperature();

    float umidadeDHT = dht.readHumidity();


    if (isnan(temperaturaDHT) || isnan(umidadeDHT)) {

      Serial.println("Erro leitura DHT11");

      return;
    }


    // =================================================
    // BMP280
    // =================================================

    float temperaturaBMP = bmp.readTemperature();

    // Pressão em hPa
    float pressao = bmp.readPressure() / 100.0F;


    // =================================================
    // DATA E HORA
    // =================================================

    struct tm timeinfo;

    char dataHora[30];

    if (getLocalTime(&timeinfo)) {

      strftime(
        dataHora,
        sizeof(dataHora),
        "%d/%m/%Y %H:%M:%S",
        &timeinfo
      );

    } else {

      strcpy(dataHora, "sem_horario");
    }


    // =================================================
    // JSON MQTT
    // =================================================

    String payload = "{";

    payload += "\"temperature_dht11\":";
    payload += String(temperaturaDHT, 1);

    payload += ",";

    payload += "\"humidity_dht11\":";
    payload += String(umidadeDHT, 1);

    payload += ",";

    payload += "\"temperature_bmp280\":";
    payload += String(temperaturaBMP, 1);

    payload += ",";

    payload += "\"pressure_bmp280\":";
    payload += String(pressao, 1);

    payload += "}";


    // =================================================
    // SERIAL
    // =================================================

    Serial.print("[");
    Serial.print(dataHora);
    Serial.print("] ");

    Serial.println(payload);


    // =================================================
    // MQTT
    // =================================================

    client.publish(
      "weather/data",
      payload.c_str()
    );
  }
}