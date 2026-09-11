"""
Lógica compartilhada de carga de dados e feature engineering.
Usado tanto por build_dataset.py (treino) quanto por predict_service.py
(produção), para garantir que as features sejam calculadas exatamente
da mesma forma nos dois casos.
"""

import os

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()  # carrega variáveis do arquivo .env (na mesma pasta do script), se existir


# ============================================================
# CONFIGURAÇÃO — ajuste conforme seu schema real
# ============================================================
TABLE_NAME = os.getenv("LOCAL_TABLE", "sensores")
COL_TIMESTAMP = "data_hora"
COL_TEMP = "temperatura"
COL_UMID = "umidade"

LAG_HOURS = [1, 2, 3, 6, 12, 24]
ROLLING_WINDOWS = [3, 6, 12]
HORIZONS = [1, 2, 3]


def get_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
            user=os.getenv("PGUSER", "admin"),
            pw=os.getenv("PGPASSWORD", "3415"),
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5432"),
            db=os.getenv("PGDATABASE", "iot_db"),
        ),
    )
    return create_engine(db_url)


def _drop_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Remove informação de timezone do índice, se houver, sem converter o
    horário (mantém o valor de relógio como veio do banco). Necessário porque
    colunas TIMESTAMPTZ e TIMESTAMP no Postgres retornam índices tz-aware e
    tz-naive respectivamente, e o pandas não consegue fazer join entre eles."""
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def load_local_data(engine, since: str | None = None) -> pd.DataFrame:
    where_clause = f"WHERE {COL_TEMP} IS NOT NULL AND {COL_UMID} IS NOT NULL"
    if since:
        where_clause += f" AND {COL_TIMESTAMP} >= '{since}'"

    query = f"""
        SELECT {COL_TIMESTAMP} AS timestamp, {COL_TEMP} AS temperatura, {COL_UMID} AS umidade
        FROM {TABLE_NAME}
        {where_clause}
        ORDER BY {COL_TIMESTAMP}
    """
    df = pd.read_sql(query, engine, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    df = _drop_tz(df)
    hourly = df.resample("1h").mean()
    hourly = hourly.rename(columns={"temperatura": "temp_local", "umidade": "umid_local"})
    return hourly


def load_external_data(engine, since: str | None = None) -> pd.DataFrame:
    where_clause = f"WHERE timestamp >= '{since}'" if since else ""
    query = f"""
        SELECT timestamp, temperatura, umidade, pressao, precipitacao, vento_velocidade
        FROM dados_historicos
        {where_clause}
        ORDER BY timestamp
    """
    df = pd.read_sql(query, engine, parse_dates=["timestamp"])
    df = df.set_index("timestamp")
    df = _drop_tz(df)
    df = df.rename(columns={"temperatura": "temp_ext", "umidade": "umid_ext"})
    return df


def merge_sources(local: pd.DataFrame, external: pd.DataFrame) -> pd.DataFrame:
    merged = local.join(external, how="outer")
    merged["temperatura"] = merged["temp_local"].combine_first(merged["temp_ext"])
    merged["umidade"] = merged["umid_local"].combine_first(merged["umid_ext"])
    return merged.sort_index()


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    hour = df.index.hour + df.index.minute / 60.0
    day_of_year = df.index.dayofyear

    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["doy_sin"] = np.sin(2 * np.pi * day_of_year / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * day_of_year / 365.25)
    return df


def add_lag_and_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    base_cols = ["temperatura", "umidade", "pressao", "precipitacao", "vento_velocidade"]
    base_cols = [c for c in base_cols if c in df.columns]

    for col in base_cols:
        for lag in LAG_HOURS:
            df[f"{col}_lag{lag}h"] = df[col].shift(lag)

        for window in ROLLING_WINDOWS:
            df[f"{col}_roll_mean{window}h"] = df[col].shift(1).rolling(window).mean()
            df[f"{col}_roll_std{window}h"] = df[col].shift(1).rolling(window).std()

        df[f"{col}_delta1h"] = df[col] - df[col].shift(1)

    return df


def build_feature_frame(engine, since: str | None = None) -> pd.DataFrame:
    """Monta o dataframe com todas as features (sem alvos), pronto tanto
    para treino (que depois adiciona os alvos) quanto para predição
    (que usa só a última linha)."""
    local = load_local_data(engine, since=since)
    external = load_external_data(engine, since=since)
    df = merge_sources(local, external)
    df = add_time_features(df)
    df = add_lag_and_rolling_features(df)
    return df