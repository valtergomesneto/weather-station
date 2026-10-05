"""
Treina modelos de previsão de temperatura, umidade e pressão atmosférica
para t+1h, t+2h, t+3h, comparando com o baseline de persistência (naive).

Uso:
    python train_model.py --data dataset.parquet --out-dir modelos/
"""

import argparse
import os

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

HORIZONS = [1, 2, 3]
TEST_FRACTION = 0.2

# (prefixo do alvo, nome da coluna "atual" usada como baseline de persistência)
VARIAVEIS = [
    ("temp", "temperatura"),
    ("umid", "umidade"),
    ("pressao", "pressao"),
]


def time_based_split(df: pd.DataFrame, test_fraction: float):
    n_test = int(len(df) * test_fraction)
    return df.iloc[:-n_test], df.iloc[-n_test:]


def get_feature_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if not c.startswith(("temp_t+", "umid_t+", "pressao_t+"))]


def evaluate(y_true, y_pred, label: str):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    print(f"  {label:<24} MAE={mae:.3f}  RMSE={rmse:.3f}")
    return mae, rmse


def train_for_target(train, test, feature_cols, target_col, baseline_col):
    X_train, y_train = train[feature_cols], train[target_col]
    X_test, y_test = test[feature_cols], test[target_col]

    baseline_pred = test[baseline_col]
    evaluate(y_test, baseline_pred, f"{target_col} (persistência)")

    model = GradientBoostingRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        random_state=42,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    evaluate(y_test, y_pred, f"{target_col} (modelo)")

    return model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="dataset.parquet")
    parser.add_argument("--out-dir", default="modelos")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    df = pd.read_parquet(args.data)
    train, test = time_based_split(df, TEST_FRACTION)
    feature_cols = get_feature_columns(df)

    print(f"Treino: {len(train)} linhas | Teste: {len(test)} linhas")
    print(f"Features usadas: {len(feature_cols)}\n")

    for h in HORIZONS:
        print(f"=== Horizonte t+{h}h ===")

        for prefixo, baseline_col in VARIAVEIS:
            target_col = f"{prefixo}_t+{h}h"
            modelo = train_for_target(train, test, feature_cols, target_col, baseline_col)
            joblib.dump(modelo, os.path.join(args.out_dir, f"modelo_{prefixo}_{h}h.joblib"))

        print()

    joblib.dump(feature_cols, os.path.join(args.out_dir, "feature_cols.joblib"))
    print(f"Modelos salvos em: {args.out_dir}/")


if __name__ == "__main__":
    main()