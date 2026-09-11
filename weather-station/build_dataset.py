"""
Monta o dataset de treino unindo:
  - dados locais da estação (tabela MQTT/ESP32, alta frequência)
  - dados externos históricos (tabela dados_historicos, Open-Meteo, horário)

Saída: um arquivo parquet com todas as features + os alvos (temperatura e
umidade em t+1h, t+2h, t+3h), pronto para o train_model.py.

Uso:
    python build_dataset.py --out dataset.parquet
"""

import argparse
import os

import numpy as np
import pandas as pd
from sqlalchemy import create_engine


# ============================================================
# CONFIGURAÇÃO
# ============================================================

TABLE_NAME = os.getenv("LOCAL_TABLE", "sensores")

COL_TIMESTAMP = "data_hora"
COL_TEMP = "temperatura"
COL_UMID = "umidade"

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
        user=os.getenv("PGUSER", "admin"),
        pw=os.getenv("PGPASSWORD", "3415"),
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        db=os.getenv("PGDATABASE", "iot_db"),
    ),
)


# ============================================================
# CONFIGURAÇÃO TEMPORAL
# ============================================================

# Os dados da estação são considerados horário de São Paulo.
LOCAL_TIMEZONE = "America/Sao_Paulo"

# Todos os timestamps utilizados pelo dataset serão convertidos
# para UTC antes do merge.
DATASET_TIMEZONE = "UTC"


# ============================================================
# CONFIGURAÇÃO DO MODELO
# ============================================================

# Horizontes de previsão, em horas
HORIZONS = [1, 2, 3]

# Janelas em horas para lags e médias móveis
LAG_HOURS = [1, 2, 3, 6, 12, 24]

ROLLING_WINDOWS = [3, 6, 12]


# ============================================================
# NORMALIZAÇÃO DE DATETIME
# ============================================================

def normalize_timestamp(
        index: pd.DatetimeIndex,
        source_timezone: str,
) -> pd.DatetimeIndex:
    """
    Normaliza um índice temporal.

    Se o timestamp não possuir timezone:
        interpreta o horário usando source_timezone.

    Se já possuir timezone:
        mantém o instante representado.

    Ao final:
        converte tudo para UTC.

    Isso garante que local e externo possam ser combinados
    sem o erro:

        Cannot join tz-naive with tz-aware DatetimeIndex
    """

    index = pd.to_datetime(index)

    # Timestamp sem timezone
    if index.tz is None:
        index = index.tz_localize(
            source_timezone,
            ambiguous="infer",
            nonexistent="shift_forward",
        )

    # Timestamp com timezone
    return index.tz_convert(DATASET_TIMEZONE)


# ============================================================
# CARREGAR DADOS LOCAIS
# ============================================================

def load_local_data(engine) -> pd.DataFrame:

    query = f"""
        SELECT
            {COL_TIMESTAMP} AS timestamp,
            {COL_TEMP} AS temperatura,
            {COL_UMID} AS umidade
        FROM {TABLE_NAME}
        WHERE
            {COL_TEMP} IS NOT NULL
            AND {COL_UMID} IS NOT NULL
        ORDER BY {COL_TIMESTAMP}
    """

    df = pd.read_sql(
        query,
        engine,
        parse_dates=["timestamp"],
    )

    if df.empty:
        print("AVISO: nenhum dado local encontrado.")

        return pd.DataFrame(
            columns=[
                "temp_local",
                "umid_local",
            ],
            index=pd.DatetimeIndex(
                [],
                tz=DATASET_TIMEZONE,
            ),
        )

    df = df.set_index("timestamp")

    # ========================================================
    # IMPORTANTE
    #
    # O ESP32 trabalha com horário de São Paulo.
    #
    # Exemplo:
    #
    #   15:00 Brasil
    #
    # vira:
    #
    #   18:00 UTC
    #
    # ========================================================

    df.index = normalize_timestamp(
        df.index,
        LOCAL_TIMEZONE,
    )

    # Dados locais possuem alta frequência.
    # Converte para média horária.
    hourly = (
        df
        .resample("1h")
        .mean()
    )

    hourly = hourly.rename(
        columns={
            "temperatura": "temp_local",
            "umidade": "umid_local",
        }
    )

    return hourly


# ============================================================
# CARREGAR DADOS EXTERNOS
# ============================================================

def load_external_data(engine) -> pd.DataFrame:

    query = """
            SELECT
                timestamp,
                temperatura,
                umidade,
                pressao,
                precipitacao,
                vento_velocidade
            FROM dados_historicos
            ORDER BY timestamp \
            """

    df = pd.read_sql(
        query,
        engine,
        parse_dates=["timestamp"],
    )

    if df.empty:
        print("AVISO: nenhum dado externo encontrado.")

        return pd.DataFrame(
            columns=[
                "temp_ext",
                "umid_ext",
                "pressao",
                "precipitacao",
                "vento_velocidade",
            ],
            index=pd.DatetimeIndex(
                [],
                tz=DATASET_TIMEZONE,
            ),
        )

    df = df.set_index("timestamp")

    # ========================================================
    # Dados da fonte externa.
    #
    # Normalmente a API armazena/retorna timestamps em UTC.
    #
    # Caso estejam sem timezone, consideramos UTC.
    # ========================================================

    df.index = normalize_timestamp(
        df.index,
        "UTC",
    )

    df = df.rename(
        columns={
            "temperatura": "temp_ext",
            "umidade": "umid_ext",
        }
    )

    return df


# ============================================================
# UNIR AS FONTES
# ============================================================

def merge_sources(
        local: pd.DataFrame,
        external: pd.DataFrame,
) -> pd.DataFrame:

    local = local.copy()
    external = external.copy()

    # Segurança adicional:
    # garante que ambos os índices sejam UTC.

    local.index = normalize_timestamp(
        local.index,
        LOCAL_TIMEZONE,
    )

    external.index = normalize_timestamp(
        external.index,
        "UTC",
    )

    # Ordena os índices antes do join.

    local = local.sort_index()
    external = external.sort_index()

    # ========================================================
    # Agora ambos são:
    #
    # DatetimeIndex(tz="UTC")
    #
    # Portanto o join é compatível.
    # ========================================================

    merged = local.join(
        external,
        how="outer",
    )

    # ========================================================
    # TEMPERATURA OFICIAL
    #
    # Prioridade:
    #
    # 1. Sensor local
    # 2. Fonte externa
    #
    # Se o ESP32 tiver um valor naquele horário,
    # ele será utilizado.
    #
    # Caso contrário, utiliza-se o dado externo.
    # ========================================================

    merged["temperatura"] = (
        merged["temp_local"]
        .combine_first(
            merged["temp_ext"]
        )
    )

    # ========================================================
    # UMIDADE OFICIAL
    # ========================================================

    merged["umidade"] = (
        merged["umid_local"]
        .combine_first(
            merged["umid_ext"]
        )
    )

    merged = merged.sort_index()

    return merged


# ============================================================
# FEATURES TEMPORAIS
# ============================================================

def add_time_features(
        df: pd.DataFrame,
) -> pd.DataFrame:

    # Como o índice está em UTC, convertemos temporariamente
    # para São Paulo para extrair hora/dia corretamente.

    local_time = df.index.tz_convert(
        LOCAL_TIMEZONE
    )

    hour = (
            local_time.hour
            + local_time.minute / 60.0
    )

    day_of_year = local_time.dayofyear

    # Hora do dia
    df["hour_sin"] = np.sin(
        2 * np.pi * hour / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * hour / 24
    )

    # Dia do ano
    df["doy_sin"] = np.sin(
        2 * np.pi * day_of_year / 365.25
    )

    df["doy_cos"] = np.cos(
        2 * np.pi * day_of_year / 365.25
    )

    return df


# ============================================================
# LAGS E ROLLING WINDOWS
# ============================================================

def add_lag_and_rolling_features(
        df: pd.DataFrame,
) -> pd.DataFrame:

    base_cols = [
        "temperatura",
        "umidade",
        "pressao",
        "precipitacao",
        "vento_velocidade",
    ]

    base_cols = [
        col
        for col in base_cols
        if col in df.columns
    ]

    for col in base_cols:

        # ====================================================
        # LAGS
        # ====================================================

        for lag in LAG_HOURS:

            df[f"{col}_lag{lag}h"] = (
                df[col].shift(lag)
            )

        # ====================================================
        # ROLLING
        # ====================================================

        for window in ROLLING_WINDOWS:

            df[
                f"{col}_roll_mean{window}h"
            ] = (
                df[col]
                .shift(1)
                .rolling(window)
                .mean()
            )

            df[
                f"{col}_roll_std{window}h"
            ] = (
                df[col]
                .shift(1)
                .rolling(window)
                .std()
            )

        # ====================================================
        # DELTA
        # ====================================================

        df[
            f"{col}_delta1h"
        ] = (
                df[col]
                - df[col].shift(1)
        )

    return df


# ============================================================
# TARGETS
# ============================================================

def add_targets(
        df: pd.DataFrame,
) -> pd.DataFrame:

    for h in HORIZONS:

        # Temperatura futura

        df[
            f"temp_t+{h}h"
        ] = (
            df["temperatura"]
            .shift(-h)
        )

        # Umidade futura

        df[
            f"umid_t+{h}h"
        ] = (
            df["umidade"]
            .shift(-h)
        )

    return df


# ============================================================
# BUILD DATASET
# ============================================================

def build_dataset() -> pd.DataFrame:

    print()
    print("=" * 60)
    print("CONSTRUINDO DATASET")
    print("=" * 60)

    # ========================================================
    # DATABASE
    # ========================================================

    print("Conectando ao PostgreSQL...")

    engine = create_engine(
        DB_URL
    )

    # ========================================================
    # LOCAL
    # ========================================================

    print("Carregando dados locais...")

    local = load_local_data(
        engine
    )

    print(
        f"Dados locais: {len(local)} registros horários"
    )

    # ========================================================
    # EXTERNO
    # ========================================================

    print("Carregando dados externos...")

    external = load_external_data(
        engine
    )

    print(
        f"Dados externos: {len(external)} registros"
    )

    # ========================================================
    # MERGE
    # ========================================================

    print("Unindo fontes...")

    df = merge_sources(
        local,
        external,
    )

    print(
        f"Registros após merge: {len(df)}"
    )

    # ========================================================
    # FEATURES TEMPORAIS
    # ========================================================

    print("Criando features temporais...")

    df = add_time_features(
        df
    )

    # ========================================================
    # LAGS / ROLLING
    # ========================================================

    print("Criando lags e médias móveis...")

    df = add_lag_and_rolling_features(
        df
    )

    # ========================================================
    # TARGETS
    # ========================================================

    print("Criando targets...")

    df = add_targets(
        df
    )

    # ========================================================
    # TARGET COLUMNS
    # ========================================================

    target_cols = (
            [
                f"temp_t+{h}h"
                for h in HORIZONS
            ]
            +
            [
                f"umid_t+{h}h"
                for h in HORIZONS
            ]
    )

    # ========================================================
    # FEATURE COLUMNS
    # ========================================================

    feature_cols = [
        col
        for col in df.columns
        if not col.startswith(
            (
                "temp_t+",
                "umid_t+",
            )
        )
    ]

    # ========================================================
    # REMOVE NaN
    #
    # O modelo precisa possuir:
    #
    # - todas as features
    # - todos os targets
    #
    # Portanto removemos qualquer linha incompleta.
    # ========================================================

    print("Removendo registros incompletos...")

    antes = len(df)

    df = df.dropna(
        subset=feature_cols + target_cols
    )

    depois = len(df)

    print(
        f"Registros removidos: {antes - depois}"
    )

    # ========================================================
    # GARANTE ORDEM TEMPORAL
    # ========================================================

    df = df.sort_index()

    return df


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--out",
        default="dataset.parquet",
    )

    args = parser.parse_args()

    # ========================================================
    # BUILD
    # ========================================================

    df = build_dataset()

    # ========================================================
    # VALIDAÇÃO
    # ========================================================

    if df.empty:

        print()
        print(
            "ERRO: o dataset final está vazio."
        )

        print(
            "Verifique se existem dados locais e históricos suficientes."
        )

        return

    # ========================================================
    # SALVAR
    # ========================================================

    df.to_parquet(
        args.out
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    print()
    print("=" * 60)
    print("DATASET GERADO COM SUCESSO")
    print("=" * 60)

    print(
        f"Arquivo: {args.out}"
    )

    print(
        f"Linhas: {len(df)}"
    )

    print(
        f"Colunas: {len(df.columns)}"
    )

    print(
        f"Período: {df.index.min()} até {df.index.max()}"
    )

    print(
        f"Timezone: {df.index.tz}"
    )

    print()
    print("Colunas:")

    for col in df.columns:
        print(
            f"  - {col}"
        )

    print("=" * 60)


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":
    main()