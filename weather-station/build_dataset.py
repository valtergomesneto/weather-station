"""
Monta o dataset de treino unindo dados locais (ESP32, incluindo pressão
atmosférica) e históricos externos (Open-Meteo), com features calculadas
pelo módulo features.py — a mesma lógica usada pelo predict_service.py
em produção.

Uso:
    python build_dataset.py --out dataset.parquet
"""

import argparse

from features import build_feature_frame, get_engine, HORIZONS


def add_targets(df):
    for h in HORIZONS:
        df[f"temp_t+{h}h"] = df["temperatura"].shift(-h)
        df[f"umid_t+{h}h"] = df["umidade"].shift(-h)
        df[f"pressao_t+{h}h"] = df["pressao"].shift(-h)
    return df


def build_dataset():
    print()
    print("=" * 60)
    print("CONSTRUINDO DATASET")
    print("=" * 60)

    print("Conectando ao PostgreSQL...")
    engine = get_engine()

    print("Montando features (local + externo, lags, rolling, ciclos)...")
    df = build_feature_frame(engine)
    print(f"Registros após merge: {len(df)}")

    print("Criando targets...")
    df = add_targets(df)

    target_cols = (
            [f"temp_t+{h}h" for h in HORIZONS]
            + [f"umid_t+{h}h" for h in HORIZONS]
            + [f"pressao_t+{h}h" for h in HORIZONS]
    )
    feature_cols = [c for c in df.columns if not c.startswith(("temp_t+", "umid_t+", "pressao_t+"))]

    print("Removendo registros incompletos...")
    antes = len(df)
    df = df.dropna(subset=feature_cols + target_cols)
    depois = len(df)
    print(f"Registros removidos: {antes - depois}")

    df = df.sort_index()
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dataset.parquet")
    args = parser.parse_args()

    df = build_dataset()

    if df.empty:
        print()
        print("ERRO: o dataset final está vazio.")
        print("Verifique se existem dados locais e históricos suficientes.")
        return

    df.to_parquet(args.out)

    print()
    print("=" * 60)
    print("DATASET GERADO COM SUCESSO")
    print("=" * 60)
    print(f"Arquivo: {args.out}")
    print(f"Linhas: {len(df)}")
    print(f"Colunas: {len(df.columns)}")
    print(f"Período: {df.index.min()} até {df.index.max()}")
    print()
    print("Colunas:")
    for col in df.columns:
        print(f"  - {col}")
    print("=" * 60)


if __name__ == "__main__":
    main()