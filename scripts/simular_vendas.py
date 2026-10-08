#!/usr/bin/env python3
"""Simulador de vendas para validar a taxa aprendida do Reponto.

O que faz:
  1. Autentica (ou registra) um usuário demo.
  2. Cria um mercado e o produto "água" se ainda não existirem.
  3. Reabastece o histórico com vendas retroativas (--days-back), usando o
     sold_at retroativo da API — cada venda anterior a hoje entra com menos
     peso na média (meia-vida de --half-life via env EMA_HALF_LIFE_DAYS).
  4. Entra em loop: vende --qty unidades a cada --interval segundos e repõe
     o estoque automaticamente (com a quantidade que a própria IA recomenda)
     quando o estoque cai ao mínimo.

Como validar: o "observado" deve aproximar-se do ritmo de vendas do dia e a
"taxa aprendida" deve convergir para alpha × observado + (1 - alpha) × prior,
com o alpha subindo conforme o número de vendas na janela cresce.

Uso:
    python3 scripts/simular_vendas.py
    python3 scripts/simular_vendas.py --days-back 21 --qty 4 --interval 5 --max-sales 50

Só depende da stdlib (sem requests/pandas).
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

APP_TZ = timezone(timedelta(hours=-3))


def parse_args():
    p = argparse.ArgumentParser(description="Simulador de vendas do Reponto")
    p.add_argument("--api", default="http://localhost:8001", help="URL da API")
    p.add_argument("--email", default="simulador@demo.com.br")
    p.add_argument("--password", default="simulador123")
    p.add_argument("--market-name", default="Mercado do Simulador")
    p.add_argument("--product-name", default="Água Mineral 500ml")
    p.add_argument("--price", type=float, default=2.49)
    p.add_argument("--days-back", type=int, default=14, help="dias de histórico retroativo (só no 1º run do produto)")
    p.add_argument("--sales-per-day", type=int, default=2, help="vendas por dia no histórico retroativo")
    p.add_argument("--qty", type=int, default=2, help="unidades por venda no loop ao vivo")
    p.add_argument("--interval", type=float, default=20, help="segundos entre vendas ao vivo")
    p.add_argument("--max-sales", type=int, default=0, help="para após N vendas ao vivo (0 = infinito, Ctrl+C para)")
    return p.parse_args()


def request(api, method, path, token=None, body=None):
    req = urllib.request.Request(
        api + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise SystemExit(f"ERRO {e.code} em {method} {path}: {detail}")


def now_sp():
    return datetime.now(APP_TZ)


def auth(api, email, password):
    tok = request(api, "POST", "/auth/login", body={"email": email, "password": password}).get("access_token")
    if tok:
        print(f"[auth] logado como {email}")
        return tok
    raise SystemExit("login falhou sem mensagem clara")


def register(api, email, password):
    print(f"[auth] sem conta ainda — registrando {email}")
    return request(api, "POST", "/auth/register", body={"name": "Simulador", "email": email, "password": password})["access_token"]


def ensure_market(api, token, name):
    markets = request(api, "GET", "/markets", token)
    for m in markets:
        if m["name"] == name:
            print(f"[mercado] usando '{name}' (ciclo de {m['replenishment_cycle_days']} dias, {m['customers_per_day']} clientes/dia)")
            return m
    m = request(api, "POST", "/markets", token, body={
        "name": name, "location": "São Paulo/SP",
        "customers_per_day": 150, "cycle_unit": "semanal", "replenishment_cycle_days": 7,
    })
    print(f"[mercado] criado '{name}' (id {m['id']})")
    return m


def ensure_product(api, token, market, name, price):
    products = request(api, "GET", f"/markets/{market['id']}/products", token)
    for prod in products:
        if prod["name"] == name:
            print(f"[produto] usando '{name}' — categoria {prod['category_name']}, estoque {prod['stock']}")
            return prod, False
    prod = request(api, "POST", f"/markets/{market['id']}/products", token, body={
        "name": name, "price": price, "stock": 0, "unit": "unidade",
    })
    for _ in range(60):
        prod = get_product(api, token, market["id"], prod["id"])
        if prod["status"] == "ready":
            break
        time.sleep(1)
    print(f"[produto] criado '{name}' — categoria {prod['category_name']}")
    return prod, True


def get_product(api, token, market_id, product_id):
    products = request(api, "GET", f"/markets/{market_id}/products", token)
    for prod in products:
        if prod["id"] == product_id:
            return prod
    raise SystemExit(f"produto {product_id} sumiu do mercado?!")


def sell(api, token, market_id, product_id, qty, sold_at=None):
    body = {"market_id": market_id, "items": [{"product_id": product_id, "quantity": qty}]}
    if sold_at:
        body["sold_at"] = sold_at
    return request(api, "POST", "/sales", token, body)


def backfill(api, token, market, product, days_back, per_day, qty):
    today = now_sp().date()
    total = days_back * per_day
    print(f"[histórico] criando {total} vendas retroativas ({days_back} dias × {per_day}/dia, {qty} un cada)...")
    n = 0
    for offset in range(days_back, 0, -1):
        day = (today - timedelta(days=offset)).isoformat()
        for _ in range(per_day):
            sell(api, token, market["id"], product["id"], qty, sold_at=f"{day}T15:00:00Z")
            n += 1
            if n % 5 == 0:
                print(f"[histórico] {n}/{total} vendas...")
    print(f"[histórico] pronto: {n} vendas retroativas criadas")


def restock(api, token, product, qty):
    recommended = float(product["recommended_quantity"] or 0)
    delta = max(recommended, qty * 5, 10)
    request(api, "POST", f"/products/{product['id']}/stock", token, body={
        "delta": delta, "reason": "Reposição automática (simulador)",
    })
    return delta


def fmt(x):
    return f"{float(x):.3f}"


def report(api, token, product_id, detailed):
    lp = request(api, "GET", f"/products/{product_id}/learning", token)
    line = (
        f"  vendas na janela: {lp['n_sales']} | confiança: {lp['confidence']} | "
        f"janela: {lp['window_start'][:10]} → {lp['window_end'][:10]}"
    )
    print(f"  observado {fmt(lp['observed_rate'])}/d | prior {fmt(lp['prior_rate'])}/d "
          f"({lp['source']}) | α {lp['alpha']:.2f} | aprendida {fmt(lp['final_rate'])}/d")
    print(line)
    if detailed:
        print(f"  {lp['formula']}")
        print(f"  mín {lp['min_stock']} | máx {lp['max_stock']} | recomendado comprar {lp['recommended_quantity']}")
        print(f"  participação: {lp['data_share_pct']}% seus dados / {lp['dataset_share_pct']}% dataset")


def main():
    args = parse_args()
    api = args.api.rstrip("/")

    try:
        token = auth(api, args.email, args.password)
    except SystemExit:
        token = register(api, args.email, args.password)
        print(f"[auth] registrado e logado como {args.email}")

    market = ensure_market(api, token, args.market_name)
    product, created = ensure_product(api, token, market, args.product_name, args.price)

    if created:
        backfill(api, token, market, product, args.days_back, args.sales_per_day, args.qty)
    else:
        print("[histórico] produto já existia — pulando backfill (apague o produto se quiser refazer)")

    print(f"\n=== loop ao vivo: {args.qty} un a cada {args.interval}s (Ctrl+C para sair) ===\n")
    live = 0
    try:
        while True:
            product = get_product(api, token, market["id"], product["id"])
            stock = float(product["stock"])
            min_stock = float(product["min_stock"])

            if stock < args.qty or stock <= min_stock:
                delta = restock(api, token, product, args.qty)
                product = get_product(api, token, market["id"], product["id"])
                print(f">>> estoque {stock:g} baixo — repostos +{delta:g} (IA recomendava "
                      f"{product['recommended_quantity']}) → estoque {float(product['stock']):g}")

            sell(api, token, market["id"], product["id"], args.qty)
            live += 1
            stamp = now_sp().strftime("%H:%M:%S")
            print(f"[{stamp}] venda #{live}: {args.qty} un | estoque {float(product['stock']) - args.qty:g}")

            report(api, token, product["id"], detailed=(live % 10 == 0 or live == 1))
            print()

            if args.max_sales and live >= args.max_sales:
                print(f"atingido --max-sales={args.max_sales}. Veja a evolução no painel da app.")
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\nencerrado após {live} vendas ao vivo. Veja a evolução no painel da app.")


if __name__ == "__main__":
    main()
