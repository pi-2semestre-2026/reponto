"""Scenario presets and the virtual product catalog.

Prices/costs are cosmetic (cash HUD); demand levels come from the REAL
category baselines (app.services.seed_data) multiplied by a per-SKU
strength factor, so the simulator plays in the same units the recommender
uses.
"""

from dataclasses import dataclass, field


@dataclass
class Scenario:
    key: str
    name: str
    customers_per_day: int
    description: str
    product_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProductSpec:
    key: str
    name: str
    category: str
    price: float
    strength: float
    ups: float = 1.5
    min_strength: float = 0.0
    max_strength: float = 0.0

    def strength_for(self, rng) -> float:
        lo, hi = (self.min_strength, self.max_strength) if self.max_strength else (self.strength, self.strength)
        return rng.uniform(lo, hi)


PRICE_BY_CATEGORY: dict[str, float] = {
    "Hortifrúti": 5.4,
    "Padaria": 1.6,
    "Bebidas": 6.9,
    "Laticínios e Ovos": 7.6,
    "Carnes e Aves": 27.9,
    "Mercearia": 11.4,
    "Congelados e Frios": 18.9,
    "Limpeza": 8.4,
    "Higiene e Beleza": 9.7,
    "Pet e Bebê": 44.9,
}

PRODUCTS: dict[str, dict] = {
    "banana": {"name": "Banana Prata (kg)", "category": "Hortifrúti", "strength": (0.9, 1.5), "ups": 1.2},
    "tomate": {"name": "Tomate Italiano (kg)", "category": "Hortifrúti", "strength": (0.5, 1.0), "ups": 1.0},
    "maca": {"name": "Maçã Fuji (kg)", "category": "Hortifrúti", "strength": (0.4, 0.9), "ups": 1.1},
    "cebola": {"name": "Cebola Nacional (kg)", "category": "Hortifrúti", "strength": (0.6, 1.1), "ups": 1.0},
    "pao_frances": {"name": "Pão Francês (un)", "category": "Padaria", "strength": (0.8, 1.4), "ups": 5.0},
    "bolo": {"name": "Bolo de Cenoura (fatia)", "category": "Padaria", "strength": (0.3, 0.7), "ups": 1.0},
    "pao_forma": {"name": "Pão de Forma (un)", "category": "Padaria", "strength": (0.4, 0.8), "ups": 1.0},
    "refri": {"name": "Refrigerante 2L", "category": "Bebidas", "strength": (0.7, 1.3), "ups": 1.6},
    "cerveja": {"name": "Cerveja Lata 350ml", "category": "Bebidas", "strength": (0.8, 1.6), "ups": 6.0},
    "suco": {"name": "Suco de Uva 1L", "category": "Bebidas", "strength": (0.3, 0.7), "ups": 1.0},
    "agua": {"name": "Água Mineral 500ml", "category": "Bebidas", "strength": (0.6, 1.2), "ups": 2.0},
    "leite": {"name": "Leite Integral 1L", "category": "Laticínios e Ovos", "strength": (0.9, 1.5), "ups": 1.8},
    "ovo": {"name": "Ovo Branco (dúzia)", "category": "Laticínios e Ovos", "strength": (0.5, 1.0), "ups": 1.0},
    "iogurte": {"name": "Iogurte de Morango (un)", "category": "Laticínios e Ovos", "strength": (0.4, 0.9), "ups": 4.0},
    "frango": {"name": "Frango Inteiro (kg)", "category": "Carnes e Aves", "strength": (0.4, 0.9), "ups": 1.4},
    "linguica": {"name": "Linguiça Toscana (kg)", "category": "Carnes e Aves", "strength": (0.3, 0.8), "ups": 1.0},
    "arroz": {"name": "Arroz Tipo 1 5kg", "category": "Mercearia", "strength": (0.7, 1.3), "ups": 1.2},
    "feijao": {"name": "Feijão Carioca 1kg", "category": "Mercearia", "strength": (0.6, 1.1), "ups": 1.1},
    "cafe": {"name": "Café Torrado 500g", "category": "Mercearia", "strength": (0.5, 1.0), "ups": 1.0},
    "oleo": {"name": "Óleo de Soja 900ml", "category": "Mercearia", "strength": (0.4, 0.9), "ups": 1.2},
    "pizza": {"name": "Pizza Congelada", "category": "Congelados e Frios", "strength": (0.3, 0.7), "ups": 1.6},
    "sorvete": {"name": "Sorvete 2L", "category": "Congelados e Frios", "strength": (0.2, 0.6), "ups": 1.0},
    "detergente": {"name": "Detergente 500ml", "category": "Limpeza", "strength": (0.4, 0.9), "ups": 1.0},
    "sanitaria": {"name": "Água Sanitária 2L", "category": "Limpeza", "strength": (0.3, 0.7), "ups": 1.0},
    "creme_dental": {"name": "Creme Dental 90g", "category": "Higiene e Beleza", "strength": (0.3, 0.7), "ups": 1.0},
    "shampoo": {"name": "Shampoo 350ml", "category": "Higiene e Beleza", "strength": (0.2, 0.6), "ups": 1.0},
    "racao": {"name": "Ração para Cães 10kg", "category": "Pet e Bebê", "strength": (0.1, 0.4), "ups": 1.0},
}

SCENARIOS: dict[str, Scenario] = {
    "bairro": Scenario(
        key="bairro",
        name="Mercado do bairro",
        customers_per_day=45,
        description="Zapateria da esquina: movimento constante, prateleira curta.",
        product_keys=[
            "banana", "tomate", "pao_frances", "bolo", "refri", "cerveja", "leite",
            "ovo", "arroz", "feijao", "cafe", "detergente", "creme_dental", "sorvete",
        ],
    ),
    "medio": Scenario(
        key="medio",
        name="Supermercado de bairro",
        customers_per_day=180,
        description="Três caixas, açougue e padaria: volume médio, categoria cheia.",
        product_keys=[
            "banana", "tomate", "maca", "cebola", "pao_frances", "pao_forma", "refri",
            "cerveja", "agua", "leite", "ovo", "iogurte", "frango", "arroz", "feijao",
            "cafe", "oleo", "pizza", "detergente", "sanitaria",
        ],
    ),
    "grande": Scenario(
        key="grande",
        name="Supermercado de rede",
        customers_per_day=520,
        description="Rede com estacionamento: caixa alta, tudo venta.",
        product_keys=list(PRODUCTS.keys()),
    ),
}

DEFAULT_PRODUCT_COUNT_LIMIT = len(PRODUCTS)


def build_catalog(scenario: Scenario, rng) -> list[dict]:
    """Instantiate the scenario's products with randomized strength and prices."""
    catalog = []
    for key in scenario.product_keys:
        spec = PRODUCTS[key]
        base_price = PRICE_BY_CATEGORY[spec["category"]]
        strength = rng.uniform(*spec["strength"])
        price = round(base_price * rng.uniform(0.85, 1.25), 2)
        catalog.append(
            {
                "key": key,
                "name": spec["name"],
                "category": spec["category"],
                "strength": strength,
                "price": price,
                "cost": round(price * 0.68, 2),
                "ups": spec["ups"],
            }
        )
    return catalog
