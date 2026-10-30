#!/usr/bin/env python3
"""Popula o Reponto com dados de demonstração (usuário, mercados, produtos e vendas).

Cria um usuário demo com dois mercados de portes diferentes, um catálogo de
produtos de várias categorias e um histórico de vendas retroativas com padrão
realista: mais movimento na sexta e no sábado, leve crescimento ao longo do
período e alguns produtos terminando com estoque baixo (geram alertas).

O estoque inicial de cada produto é calculado para cobrir todo o histórico e
terminar no nível escolhido em `final_days` (dias de venda que sobram na prateleira).

Uso:
    python scripts/popular_demo.py
    python scripts/popular_demo.py --days 60 --api http://localhost:8000

Só depende da stdlib. Rodar de novo com o mesmo e-mail pula os mercados que já existem.
"""

import argparse
import json
import math
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

APP_TZ = timezone(timedelta(hours=-3))

# Fator por dia da semana (seg=0 ... dom=6)
WEEKDAY_FACTOR = [0.85, 0.85, 0.95, 1.0, 1.15, 1.35, 0.9]

# (nome, preço, unidades vendidas por dia em média, unidades por compra (mín, máx), dias de estoque no fim)
MARKETS = [
    {
        "name": "Mercadinho Dona Maria",
        "location": "Vila Mariana, São Paulo/SP",
        "customers_per_day": 120,
        "cycle_unit": "semanal",
        "tickets_per_day": 22,
        "products": [
            ("Pão Francês", 0.90, 70, (4, 10), 2),
            ("Leite Integral 1L", 5.49, 18, (1, 3), 8),
            ("Ovos Brancos (dúzia)", 11.90, 6, (1, 1), 1),
            ("Banana Prata (kg)", 6.99, 9, (1, 2), 4),
            ("Tomate (kg)", 8.49, 6, (1, 2), 9),
            ("Arroz Branco 5kg", 27.90, 3, (1, 1), 12),
            ("Feijão Carioca 1kg", 8.79, 4, (1, 2), 10),
            ("Café Torrado 500g", 18.90, 3, (1, 1), 1),
            ("Refrigerante Guaraná 2L", 8.99, 8, (1, 2), 9),
            ("Cerveja Lata 350ml", 3.79, 20, (2, 6), 7),
            ("Detergente 500ml", 2.49, 4, (1, 2), 14),
            ("Papel Higiênico 12 rolos", 21.90, 2, (1, 1), 11),
            ("Creme Dental 90g", 4.99, 3, (1, 2), 13),
        ],
    },
    {
        "name": "Supermercado Bom Preço",
        "location": "Centro, Santo André/SP",
        "customers_per_day": 400,
        "cycle_unit": "quinzenal",
        "tickets_per_day": 30,
        "products": [
            ("Pão de Forma 500g", 9.49, 14, (1, 2), 16),
            ("Leite Integral 1L", 5.29, 45, (2, 6), 18),
            ("Queijo Muçarela Fatiado 200g", 12.90, 10, (1, 2), 3),
            ("Iogurte Natural 170g", 3.49, 16, (1, 4), 15),
            ("Frango Inteiro Congelado (kg)", 13.90, 12, (1, 2), 17),
            ("Carne Moída (kg)", 39.90, 8, (1, 2), 4),
            ("Linguiça Toscana (kg)", 24.90, 6, (1, 2), 19),
            ("Arroz Branco 5kg", 26.90, 9, (1, 1), 20),
            ("Macarrão Espaguete 500g", 4.59, 14, (1, 3), 22),
            ("Óleo de Soja 900ml", 7.99, 10, (1, 2), 5),
            ("Açúcar Refinado 1kg", 4.99, 9, (1, 2), 18),
            ("Água Mineral 1,5L", 2.99, 30, (2, 6), 16),
            ("Suco de Uva Integral 1L", 14.90, 5, (1, 2), 24),
            ("Sorvete de Chocolate 1,5L", 22.90, 3, (1, 1), 20),
            ("Sabão em Pó 1,6kg", 19.90, 4, (1, 1), 21),
            ("Shampoo 350ml", 15.90, 3, (1, 1), 2),
            ("Ração para Cachorro 3kg", 49.90, 2, (1, 1), 19),
        ],
    },
]


def parse_args():
    p = argparse.ArgumentParser(description="Popula o Reponto com dados de demonstração")
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--email", default="demo@reponto.com.br")
    p.add_argument("--password", default="reponto123")
    p.add_argument("--name", default="Conta Demonstração")
    p.add_argument("--days", type=int, default=60, help="dias de histórico de vendas")
    p.add_argument("--seed", type=int, default=2026)
    return p.parse_args()


def request(api, method, path, token=None, body=None, retries=3):
    req = urllib.request.Request(
        api + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method,
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                return json.loads(data) if data else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(1)
                continue
            raise RuntimeError(f"ERRO {e.code} em {method} {path}: {detail}")


def get_token(api, args):
    try:
        return request(api, "POST", "/auth/login", body={"email": args.email, "password": args.password})["access_token"]
    except RuntimeError:
        return request(api, "POST", "/auth/register", body={
            "name": args.name, "email": args.email, "password": args.password,
        })["access_token"]


def poisson(rng, lam):
    """Sorteio de Poisson (Knuth para lambda pequeno, aproximação normal para grande)."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def plan_sales(spec, days, rng):
    """Gera a lista de cupons [(sold_at_iso, {produto: qtd})] e o total vendido por produto."""
    now = datetime.now(APP_TZ)
    today = now.date()
    tickets = []
    totals = {p[0]: 0 for p in spec["products"]}

    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        wf = WEEKDAY_FACTOR[day.weekday()]
        trend = 0.9 + 0.2 * (1 - offset / max(days, 1))  # cresce ~20% no período
        # hoje: só as horas que já passaram
        open_h, close_h = 7, 21
        if offset == 0:
            close_h = min(close_h, now.hour)
            if close_h <= open_h:
                continue
        day_share = (close_h - open_h) / 14

        n_tickets = max(1, poisson(rng, spec["tickets_per_day"] * wf * trend * day_share))
        day_tickets = [dict() for _ in range(n_tickets)]

        for name, _price, rate, (qmin, qmax), _final in spec["products"]:
            demand = poisson(rng, rate * wf * trend * day_share)
            while demand > 0:
                q = min(demand, rng.randint(qmin, qmax))
                t = rng.choice(day_tickets)
                t[name] = t.get(name, 0) + q
                demand -= q

        for t in day_tickets:
            if not t:
                continue
            minute = rng.randint(open_h * 60, close_h * 60 - 1)
            sold = datetime(day.year, day.month, day.day, minute // 60, minute % 60, rng.randint(0, 59), tzinfo=APP_TZ)
            if sold > now:
                continue
            tickets.append((sold, t))
            for name, q in t.items():
                totals[name] += q

    tickets.sort(key=lambda x: x[0])
    return tickets, totals


def wait_ready(api, token, market_id, expected):
    for _ in range(120):
        prods = request(api, "GET", f"/markets/{market_id}/products", token)
        if len(prods) >= expected and all(p["status"] == "ready" for p in prods):
            return prods
        time.sleep(1)
    return request(api, "GET", f"/markets/{market_id}/products", token)


def populate_market(api, token, spec, days, seed, log):
    rng = random.Random(f"{seed}-{spec['name']}")
    existing = {m["name"]: m for m in request(api, "GET", "/markets", token)}
    if spec["name"] in existing:
        log(f"[{spec['name']}] já existe — pulando")
        return

    market = request(api, "POST", "/markets", token, body={
        "name": spec["name"], "location": spec["location"],
        "customers_per_day": spec["customers_per_day"], "cycle_unit": spec["cycle_unit"],
    })
    log(f"[{spec['name']}] mercado criado (ciclo de {market['replenishment_cycle_days']} dias)")

    tickets, totals = plan_sales(spec, days, rng)

    for name, price, rate, _q, final_days in spec["products"]:
        stock = totals[name] + round(rate * final_days)
        request(api, "POST", f"/markets/{market['id']}/products", token, body={
            "name": name, "price": price, "stock": stock, "unit": "unidade",
        })
    prods = wait_ready(api, token, market["id"], len(spec["products"]))
    ids = {p["name"]: p["id"] for p in prods}
    log(f"[{spec['name']}] {len(prods)} produtos cadastrados e categorizados")

    sale_ids = []
    for i, (sold, items) in enumerate(tickets, 1):
        sale = request(api, "POST", "/sales", token, body={
            "market_id": market["id"],
            "sold_at": sold.isoformat(),
            "items": [{"product_id": ids[n], "quantity": q} for n, q in items.items()],
        })
        sale_ids.append(sale["id"])
        if i % 200 == 0 or i == len(tickets):
            log(f"[{spec['name']}] {i}/{len(tickets)} vendas")

    # Duas vendas canceladas, para mostrar o estorno
    for sid in rng.sample(sale_ids[-50:], 2):
        request(api, "POST", f"/sales/{sid}/cancel", token)
    log(f"[{spec['name']}] pronto: {len(tickets)} vendas (2 canceladas)")


def main():
    args = parse_args()
    api = args.api.rstrip("/")
    token = get_token(api, args)
    lock = threading.Lock()

    def log(msg):
        with lock:
            print(msg, flush=True)

    errors = []

    def worker(spec):
        try:
            populate_market(api, token, spec, args.days, args.seed, log)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
            log(f"[{spec['name']}] falhou: {e}")

    started = time.time()
    threads = [threading.Thread(target=worker, args=(s,)) for s in MARKETS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"\nconcluído em {time.time() - started:.0f}s")
    print(f"login: {args.email} / senha: {args.password}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
