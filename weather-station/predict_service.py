"""
Gera previsões de temperatura, umidade e pressão para t+1h, t+2h e t+3h
a partir do estado mais recente da estação, e grava o resultado na
tabela `previsoes`.

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

MODELO_VERSAO = os.getenv("MODELO_VERSAO", "v2-pressao")
VARIAVEIS = ["temp", "umid", "pressao"]


def load_models(models_dir: str):
    feature_cols = joblib.load(os.path.join(models_dir, "feature_cols.joblib"))
    models = {}
    for h in HORIZONS:
        for prefixo in VARIAVEIS:
            models[(prefixo, h)] = joblib.load(
                os.path.join(models_dir, f"modelo_{prefixo}_{h}h.joblib")
            )
    return models, feature_cols


def get_latest_features(engine, feature_cols: list) -> tuple[pd.Timestamp, pd.DataFrame]:
    since = (pd.Timestamp.now() - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    df = build_feature_frame(engine, since=since)
    df = df.dropna(subset=feature_cols)

    if df.empty:
        raise RuntimeError(
            "Não há nenhuma linha recente com todas as features completas. "
            "Verifique se o historical_ingest.py e a coleta local estão em dia."
        )

    last_row = df.iloc[[-1]]
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
        pressao_pred = float(models[("pressao", h)].predict(X)[0])
        timestamp_previsto = last_timestamp + timedelta(hours=h)

        rows.append((timestamp_previsto, h, temp_pred, umid_pred, pressao_pred, MODELO_VERSAO))
        print(
            f"t+{h}h ({timestamp_previsto}): "
            f"temp={temp_pred:.1f}°C  umid={umid_pred:.1f}%  pressao={pressao_pred:.1f}hPa"
        )

    with engine.begin() as conn:
        conn.execute(
            text("""
                 INSERT INTO previsoes
                 (timestamp_previsto, horizonte_horas, temperatura_prevista,
                  umidade_prevista, pressao_prevista, modelo_versao)
                 VALUES (:ts, :h, :temp, :umid, :pressao, :versao)
                 """),
            [
                {"ts": ts, "h": h, "temp": temp, "umid": umid, "pressao": pressao, "versao": versao}
                for ts, h, temp, umid, pressao, versao in rows
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