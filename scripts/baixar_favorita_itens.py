#!/usr/bin/env python3
"""Baixa o Favorita POR ITEM (Kaggle) para data/raw/favorita_itens/.

Competição: https://www.kaggle.com/competitions/favorita-grocery-sales-forecasting

Antes de rodar (uma vez, pela sua conta):
  1. Aceite as regras da competição na página acima (Join Competition).
  2. Crie um token em Kaggle > Settings > API Tokens e salve só a chave em
     C:\\Users\\<você>\\.kaggle\\access_token (ou access_token.txt). A chave legada
     (kaggle.json na mesma pasta) também funciona. Nunca dentro do repositório.

Uso (raiz do repo, com o venv):
    pip install -e ".[dados]"
    python scripts/baixar_favorita_itens.py

O download vai para o cache do kagglehub; daqui só os arquivos usados são
descompactados (.7z) em data/raw/favorita_itens/ (fora do git).
"""

import shutil
import sys
from pathlib import Path

import kagglehub
import py7zr

COMPETITION = "favorita-grocery-sales-forecasting"
WANTED = ("train.csv", "items.csv", "transactions.csv", "stores.csv", "holidays_events.csv")
DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "favorita_itens"


def main() -> None:
    try:
        path = Path(kagglehub.competition_download(COMPETITION))
    except Exception as e:  # credenciais ausentes ou regras não aceitas
        sys.exit(
            f"Falha no download: {e}\n"
            "Confira: (1) regras da competição aceitas no site; "
            "(2) token em ~/.kaggle/access_token (Kaggle > Settings > API Tokens) ou kaggle.json."
        )
    print("cache do kagglehub:", path)
    DEST.mkdir(parents=True, exist_ok=True)

    for name in WANTED:
        target = DEST / name
        if target.exists() and target.stat().st_size > 0:
            print(f"  {name}: já existe ({target.stat().st_size / 1e6:,.0f} MB), pulando")
            continue
        candidates = list(path.rglob(name + ".7z")) + list(path.rglob(name))
        if not candidates:
            print(f"  {name}: não encontrado no download")
            continue
        src = candidates[0]
        if src.suffix == ".7z":
            print(f"  {name}: descompactando {src.name} ...", flush=True)
            with py7zr.SevenZipFile(src, mode="r") as z:
                z.extract(path=DEST, targets=[name])
        else:
            shutil.copy2(src, target)
        print(f"  {name}: {target.stat().st_size / 1e6:,.0f} MB")

    print("\npronto:", DEST)


if __name__ == "__main__":
    main()
