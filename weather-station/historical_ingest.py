"""
Ingestão de dados meteorológicos do Open-Meteo para o Postgres.

Dois modos de uso:
  1) Backfill histórico (rodar uma vez, para trazer meses/anos de dados)
     python historical_ingest.py backfill --start 2024-01-01 --end 2026-09-09

  2) Atualização recorrente (rodar via cron, ex: a cada hora)
     python historical_ingest.py recent --past-days 3

Documentação da API: https://open-meteo.com/en/docs
"""

import argparse
import os
import sys
from datetime import date, timedelta

import requests
import psycopg2
from psycopg2.extras import execute_values

# ============================================================
# CONFIGURAÇÃO — ajuste para a sua estação
# ============================================================
LATITUDE = float(os.getenv("STATION_LAT", "-24.0000"))
LONGITUDE = float(os.getenv("STATION_LON", "-46.2529"))
TIMEZONE = os.getenv("STATION_TZ", "America/Sao_Paulo")

DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "iot_db"),
    "user": os.getenv("PGUSER", "admin"),
    "password": os.getenv("PGPASSWORD", "3415"),
}

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "precipitation",
    "wind_speed_10m",
]

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_open_meteo(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_hourly_payload(payload: dict) -> list[tuple]:
    """Transforma o JSON do Open-Meteo em linhas prontas para insert."""
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    temp = hourly.get("temperature_2m", [])
    umid = hourly.get("relative_humidity_2m", [])
    pressao = hourly.get("surface_pressure", [])
    precip = hourly.get("precipitation", [])
    vento = hourly.get("wind_speed_10m", [])

    rows = []
    for i, ts in enumerate(times):
        rows.append((
            ts,
            temp[i] if i < len(temp) else None,
            umid[i] if i < len(umid) else None,
            pressao[i] if i < len(pressao) else None,
            precip[i] if i < len(precip) else None,
            vento[i] if i < len(vento) else None,
            "open-meteo",
        ))
    return rows


def upsert_rows(rows: list[tuple]) -> int:
    if not rows:
        return 0
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn, conn.cursor() as cur:
            query = """
                    INSERT INTO dados_historicos
                    (timestamp, temperatura, umidade, pressao, precipitacao, vento_velocidade, fonte)
                    VALUES %s
                        ON CONFLICT (timestamp, fonte) DO UPDATE SET
                        temperatura = EXCLUDED.temperatura,
                                                              umidade = EXCLUDED.umidade,
                                                              pressao = EXCLUDED.pressao,
                                                              precipitacao = EXCLUDED.precipitacao,
                                                              vento_velocidade = EXCLUDED.vento_velocidade; \
                    """
            execute_values(cur, query, rows)
        return len(rows)
    finally:
        conn.close()


def backfill(start: str, end: str):
    """Busca dados históricos (arquivo) entre duas datas ISO (YYYY-MM-DD)."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": TIMEZONE,
    }
    print(f"Buscando histórico de {start} até {end}...")
    payload = fetch_open_meteo(ARCHIVE_URL, params)
    rows = parse_hourly_payload(payload)
    n = upsert_rows(rows)
    print(f"{n} registros horários inseridos/atualizados.")


def recent(past_days: int):
    """Busca os últimos N dias (inclui dados quase em tempo real + previsão a curto prazo)."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": TIMEZONE,
        "past_days": past_days,
        "forecast_days": 1,
    }
    print(f"Buscando últimos {past_days} dias + previsão de curto prazo...")
    payload = fetch_open_meteo(FORECAST_URL, params)
    rows = parse_hourly_payload(payload)
    n = upsert_rows(rows)
    print(f"{n} registros horários inseridos/atualizados.")


def main():
    parser = argparse.ArgumentParser(description="Ingestão Open-Meteo -> Postgres")
    sub = parser.add_subparsers(dest="modo", required=True)

    p_backfill = sub.add_parser("backfill", help="Traz dados históricos entre duas datas")
    p_backfill.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_backfill.add_argument("--end", default=str(date.today() - timedelta(days=1)))

    p_recent = sub.add_parser("recent", help="Atualiza os últimos N dias (usar em cron)")
    p_recent.add_argument("--past-days", type=int, default=3)

    args = parser.parse_args()

    if args.modo == "backfill":
        backfill(args.start, args.end)
    elif args.modo == "recent":
        recent(args.past_days)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"Erro na API Open-Meteo: {e}", file=sys.stderr)
        sys.exit(1)
    except psycopg2.Error as e:
        print(f"Erro no Postgres: {e}", file=sys.stderr)
        sys.exit(1)