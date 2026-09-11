"""
Gera previsões de temperatura e umidade para t+1h, t+2h e t+3h a partir do
estado mais recente da estação, e grava o resultado na tabela `previsoes`.

Pensado para rodar de hora em hora via cron (junto com o historical_ingest.py
"recent", que deve rodar um pouco antes para garantir dados externos frescos).

Uso:
    python predict_service.py --models-dir modelos/
"""

import argparse
import os
from datetime import timedelta

import joblib
import pandas as pd
from sqlalchemy import text

from features import build_feature_frame, get_engine, HORIZONS

MODELO_VERSAO = os.getenv("MODELO_VERSAO", "v1")


def load_models(models_dir: str):
    feature_cols = joblib.load(os.path.join(models_dir, "feature_cols.joblib"))
    models = {}
    for h in HORIZONS:
        models[("temp", h)] = joblib.load(os.path.join(models_dir, f"modelo_temp_{h}h.joblib"))
        models[("umid", h)] = joblib.load(os.path.join(models_dir, f"modelo_umid_{h}h.joblib"))
    return models, feature_cols


def get_latest_features(engine, feature_cols: list) -> tuple[pd.Timestamp, pd.DataFrame]:
    # 72h de histórico é suficiente para os lags/rolling de até 24h + folga.
    # Usamos horário local naive (sem timezone) para bater com o resto do pipeline.
    since = (pd.Timestamp.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    df = build_feature_frame(engine, since=since)
    df = df.dropna(subset=feature_cols)

    if df.empty:
        raise RuntimeError(
            "Não há nenhuma linha recente com todas as features completas. "
            "Verifique se o historical_ingest.py e a coleta local estão em dia."
        )

    last_row = df.iloc[[-1]]  # dataframe com 1 linha, mantém formato para o modelo
    last_timestamp = df.index[-1]
    return last_timestamp, last_row[feature_cols]


def generate_predictions(models_dir: str):
    engine = get_engine()
    models, feature_cols = load_models(models_dir)

    last_timestamp, X = get_latest_features(engine, feature_cols)

    rows = []
    for h in HORIZONS:
        temp_pred = float(models[("temp", h)].predict(X)[0])
        umid_pred = float(models[("umid", h)].predict(X)[0])
        timestamp_previsto = last_timestamp + timedelta(hours=h)
        rows.append((timestamp_previsto, h, temp_pred, umid_pred, MODELO_VERSAO))
        print(f"t+{h}h ({timestamp_previsto}): temp={temp_pred:.1f}°C  umid={umid_pred:.1f}%")

    with engine.begin() as conn:
        conn.execute(
            text("""
                 INSERT INTO previsoes
                 (timestamp_previsto, horizonte_horas, temperatura_prevista, umidade_prevista, modelo_versao)
                 VALUES (:ts, :h, :temp, :umid, :versao)
                 """),
            [
                {"ts": ts, "h": h, "temp": temp, "umid": umid, "versao": versao}
                for ts, h, temp, umid, versao in rows
            ],
        )

    print(f"{len(rows)} previsões gravadas (baseadas em dados até {last_timestamp}).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models-dir", default="modelos")
    args = parser.parse_args()

    generate_predictions(args.models_dir)


if __name__ == "__main__":
    main()