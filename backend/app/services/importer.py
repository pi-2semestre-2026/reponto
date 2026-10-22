"""ERP/PDV file import — the integration entry point.

Small markets already keep their data in a PDV/ERP; re-typing the catalog and
the sales history is the main adoption barrier. This module accepts the CSV/TXT
export as it comes out of those systems (';', ',', tab or '|'; UTF-8 or
Windows-1252; decimal comma; dd/mm/yyyy dates), maps the columns by their
header names and detects the file kind:

  - "sales":   one row per item sold (date + product + quantity [+ price, receipt])
  - "catalog": one row per product (product + price/cost/stock, no date)

Rules that keep the ERP as the source of truth:
  - imported sales are HISTORY: they feed the learning but never move stock;
  - the catalog import sets price, cost and the current stock;
  - the same file (same hash) cannot be imported twice into the same market.
"""

import csv
import datetime as dt
import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.services.clock import LOCAL_TZ

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 50_000

# Canonical field -> accepted header names (already normalized: lowercase,
# no accents, single spaces). Order inside FIELD_ORDER decides who wins a
# header when two fields could claim it.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": ("data", "data venda", "data da venda", "dt", "dt venda", "dt emissao", "data emissao",
             "emissao", "data movimento", "dt movimento", "dia", "date", "sale date"),
    "time": ("hora", "horario", "hora venda", "hora da venda", "time"),
    "receipt": ("cupom", "numero cupom", "n cupom", "cupom fiscal", "nf", "nfce", "nfc e", "nota", "numero nota",
                "venda", "id venda", "n venda", "numero venda", "documento", "doc", "pedido", "ticket", "coo",
                "receipt", "order id"),
    "sku": ("codigo", "cod", "cod produto", "codigo produto", "sku", "ean", "gtin", "codigo barras",
            "cod barras", "codigo de barras", "referencia", "ref", "plu", "code"),
    "product": ("produto", "descricao", "descricao produto", "desc produto", "nome", "nome produto",
                "item", "mercadoria", "desc", "product", "product name", "name", "description"),
    "quantity": ("quantidade", "qtd", "qtde", "qt", "quant", "qtd vendida", "quantidade vendida",
                 "quantity", "qty", "unidades"),
    "unit_price": ("preco", "preco unitario", "preco unit", "valor unitario", "vl unit", "vlr unit",
                   "vl unitario", "vlr unitario", "preco venda", "pv", "price", "unit price"),
    "total": ("total", "valor total", "vl total", "vlr total", "subtotal", "total item", "valor liquido"),
    "value": ("valor", "vl", "vlr", "value"),
    "stock": ("estoque", "saldo", "estoque atual", "qtd estoque", "saldo estoque", "quantidade estoque",
              "stock", "on hand"),
    "cost": ("custo", "preco custo", "custo unitario", "vl custo", "vlr custo", "preco de custo", "cost"),
    "unit": ("unidade", "un", "und", "unid", "medida", "unidade medida", "unit", "uom"),
}
FIELD_ORDER = ("date", "time", "receipt", "sku", "product", "quantity", "unit_price", "total",
               "cost", "stock", "unit", "value")

# Too generic to match inside a longer header ("Valor Venda" is not a receipt id).
CONTAINMENT_EXCLUDE = {"venda", "item", "dia", "doc", "nota", "ref", "nome", "desc", "name", "code"}

FIELD_LABELS = {
    "date": "Data", "time": "Hora", "receipt": "Cupom/venda", "sku": "Código", "product": "Produto",
    "quantity": "Quantidade", "unit_price": "Preço unitário", "total": "Valor total", "value": "Valor",
    "stock": "Estoque", "cost": "Custo", "unit": "Unidade",
}

DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")

UNIT_ALIASES = {
    "un": "unidade", "und": "unidade", "unid": "unidade", "unidade": "unidade", "pc": "unidade", "pç": "unidade",
    "kg": "kg", "g": "g", "gr": "g", "l": "L", "lt": "L", "litro": "L", "ml": "ml",
    "pct": "pacote", "pacote": "pacote", "cx": "caixa", "caixa": "caixa", "dz": "dz", "duzia": "dz",
}


class ImportError_(ValueError):
    """Raised with a PT-BR message that can be shown to the user."""


def normalize_header(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or "").strip().lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(text: str) -> str:
    return normalize_header(text)


def file_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------- decoding


def decode(raw: bytes) -> tuple[str, str]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc), ("utf-8" if enc == "utf-8-sig" else "windows-1252")
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace"), "latin-1"


def sniff_delimiter(text: str) -> str:
    head = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(head, delimiters=";,\t|").delimiter
    except csv.Error:
        counts = {d: head.count(d) for d in ";,\t|"}
        return max(counts, key=counts.get) if any(counts.values()) else ";"


# ---------------------------------------------------------------- mapping


def map_columns(headers: list[str]) -> dict[str, int]:
    """Canonical field -> column index. Exact synonym match first, then a
    containment match ("qtd vendida un" -> quantity)."""
    norm = [normalize_header(h) for h in headers]
    mapping: dict[str, int] = {}
    taken: set[int] = set()

    for fld in FIELD_ORDER:
        for syn in SYNONYMS[fld]:
            idx = next((i for i, h in enumerate(norm) if h == syn and i not in taken), None)
            if idx is not None:
                mapping[fld] = idx
                taken.add(idx)
                break
    for fld in FIELD_ORDER:
        if fld in mapping:
            continue
        for idx, h in enumerate(norm):
            if idx in taken or not h:
                continue
            words = set(h.split())
            if any(
                len(s) >= 3 and s not in CONTAINMENT_EXCLUDE and (s in h if " " in s else s in words)
                for s in SYNONYMS[fld]
            ):
                mapping[fld] = idx
                taken.add(idx)
                break
    return mapping


def detect_kind(mapping: dict[str, int]) -> str:
    has_product = "product" in mapping or "sku" in mapping
    if not has_product:
        raise ImportError_("Não encontramos a coluna de produto (ex.: 'Produto', 'Descrição' ou 'Código').")
    if "date" in mapping and "quantity" in mapping:
        return "sales"
    if any(k in mapping for k in ("stock", "unit_price", "cost", "value")):
        return "catalog"
    if "date" in mapping:
        raise ImportError_("Arquivo de vendas sem a coluna de quantidade (ex.: 'Qtd' ou 'Quantidade').")
    raise ImportError_(
        "Não reconhecemos o tipo do arquivo. Para vendas: Data, Produto e Quantidade. "
        "Para cadastro: Produto e Preço/Custo/Estoque."
    )


# ---------------------------------------------------------------- values


def detect_decimal_comma(rows: list[list[str]], numeric_cols: list[int]) -> bool:
    comma = dot = 0
    for row in rows[:500]:
        for c in numeric_cols:
            if c >= len(row):
                continue
            v = row[c].strip()
            if re.fullmatch(r"-?[\d.]*\d,\d+", v):
                comma += 1
            elif re.fullmatch(r"-?\d+\.\d{1,2}", v) or re.fullmatch(r"-?\d+\.\d{4,}", v):
                dot += 1
    return comma >= dot


def parse_number(value: str, decimal_comma: bool) -> Decimal | None:
    v = str(value or "").strip()
    v = re.sub(r"(?i)r\$|\s", "", v)
    if not v or v in {"-", "--"}:
        return None
    if decimal_comma:
        v = v.replace(".", "").replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def parse_date(value: str) -> dt.datetime | None:
    """Accepts a date, or a date + time in the same cell."""
    v = str(value or "").strip()
    if not v:
        return None
    v = v.replace("T", " ")
    date_part, _, time_part = v.partition(" ")
    day = None
    for fmt in DATE_FORMATS:
        try:
            day = dt.datetime.strptime(date_part, fmt).date()
            break
        except ValueError:
            continue
    if day is None:
        return None
    clock = parse_time(time_part) if time_part else None
    return dt.datetime.combine(day, clock or dt.time(12, 0), tzinfo=LOCAL_TZ)


def parse_time(value: str) -> dt.time | None:
    v = str(value or "").strip()[:8]
    for fmt in TIME_FORMATS:
        try:
            return dt.datetime.strptime(v, fmt).time()
        except ValueError:
            continue
    return None


def normalize_unit(value: str) -> str:
    v = normalize_header(value)
    return UNIT_ALIASES.get(v, (value or "unidade").strip()[:20] or "unidade")


# ---------------------------------------------------------------- parsing


@dataclass
class ParsedRow:
    line: int
    product: str
    sku: str | None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    sold_at: dt.datetime | None = None
    receipt: str | None = None
    stock: Decimal | None = None
    cost: Decimal | None = None
    unit: str | None = None


@dataclass
class ParsedFile:
    kind: str
    encoding: str
    delimiter: str
    headers: list[str]
    mapping: dict[str, int]
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total_lines: int = 0


def parse_file(raw: bytes) -> ParsedFile:
    if not raw:
        raise ImportError_("Arquivo vazio.")
    if len(raw) > MAX_FILE_BYTES:
        raise ImportError_("Arquivo maior que 5 MB. Exporte um período menor do seu sistema.")
    text, encoding = decode(raw)
    delimiter = sniff_delimiter(text)
    table = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    if len(table) < 2:
        raise ImportError_("O arquivo precisa de uma linha de cabeçalho e pelo menos uma linha de dados.")
    headers, body = table[0], table[1:]
    if len(body) > MAX_ROWS:
        raise ImportError_(f"Arquivo com mais de {MAX_ROWS:,} linhas. Divida a exportação por período.".replace(",", "."))

    mapping = map_columns(headers)
    kind = detect_kind(mapping)
    if kind == "catalog" and "value" in mapping and "unit_price" not in mapping:
        mapping["unit_price"] = mapping.pop("value")
    if kind == "sales" and "value" in mapping and "total" not in mapping and "unit_price" not in mapping:
        mapping["total"] = mapping.pop("value")

    numeric_cols = [mapping[k] for k in ("quantity", "unit_price", "total", "stock", "cost") if k in mapping]
    decimal_comma = detect_decimal_comma(body, numeric_cols)

    parsed = ParsedFile(kind=kind, encoding=encoding, delimiter=delimiter, headers=headers,
                        mapping=mapping, total_lines=len(body))

    def cell(row: list[str], key: str) -> str:
        idx = mapping.get(key)
        return row[idx].strip() if idx is not None and idx < len(row) else ""

    for offset, row in enumerate(body):
        line = offset + 2
        name = cell(row, "product")
        sku = cell(row, "sku") or None
        if not name and not sku:
            parsed.errors.append({"line": line, "message": "Linha sem produto"})
            continue
        item = ParsedRow(line=line, product=(name or sku)[:160], sku=sku[:60] if sku else None)
        if "unit" in mapping:
            item.unit = normalize_unit(cell(row, "unit"))

        if kind == "sales":
            sold_at = parse_date(cell(row, "date"))
            if sold_at is None:
                parsed.errors.append({"line": line, "message": f"Data inválida: '{cell(row, 'date')}'"})
                continue
            if "time" in mapping:
                clock = parse_time(cell(row, "time"))
                if clock:
                    sold_at = sold_at.replace(hour=clock.hour, minute=clock.minute, second=clock.second)
            qty = parse_number(cell(row, "quantity"), decimal_comma)
            if qty is None or qty <= 0:
                parsed.errors.append({"line": line, "message": f"Quantidade inválida: '{cell(row, 'quantity')}'"})
                continue
            unit_price = parse_number(cell(row, "unit_price"), decimal_comma) if "unit_price" in mapping else None
            if unit_price is None and "total" in mapping:
                total = parse_number(cell(row, "total"), decimal_comma)
                if total is not None:
                    unit_price = (total / qty).quantize(Decimal("0.01"))
            item.sold_at = sold_at
            item.quantity = qty
            item.unit_price = unit_price if unit_price is not None and unit_price >= 0 else None
            item.receipt = cell(row, "receipt") or None
        else:
            item.unit_price = parse_number(cell(row, "unit_price"), decimal_comma)
            item.cost = parse_number(cell(row, "cost"), decimal_comma)
            stock = parse_number(cell(row, "stock"), decimal_comma)
            item.stock = stock if stock is None or stock >= 0 else Decimal("0")
        parsed.rows.append(item)

    if not parsed.rows:
        first = parsed.errors[0]["message"] if parsed.errors else "nenhuma linha válida"
        raise ImportError_(f"Nenhuma linha pôde ser lida ({first}).")
    return parsed


def product_key(sku: str | None, name: str) -> str:
    return f"sku:{sku.strip().lower()}" if sku else f"name:{normalize_name(name)}"


def preview(parsed: ParsedFile, filename: str) -> dict:
    by_field = {idx: fld for fld, idx in parsed.mapping.items()}
    columns = [
        {"header": h, "field": by_field.get(i), "label": FIELD_LABELS.get(by_field.get(i, ""), None)}
        for i, h in enumerate(parsed.headers)
    ]
    products = {product_key(r.sku, r.product) for r in parsed.rows}
    sample = []
    for r in parsed.rows[:8]:
        sample.append(
            {
                "line": r.line,
                "product": r.product,
                "sku": r.sku,
                "date": r.sold_at.date().isoformat() if r.sold_at else None,
                "quantity": str(r.quantity) if r.quantity is not None else None,
                "unit_price": str(r.unit_price) if r.unit_price is not None else None,
                "stock": str(r.stock) if r.stock is not None else None,
                "cost": str(r.cost) if r.cost is not None else None,
                "receipt": r.receipt,
            }
        )
    dates = [r.sold_at.date() for r in parsed.rows if r.sold_at]
    warnings = []
    unmapped = [c["header"] for c in columns if c["field"] is None and c["header"].strip()]
    if unmapped:
        warnings.append(f"Colunas ignoradas: {', '.join(unmapped[:6])}")
    if parsed.kind == "sales" and "unit_price" not in parsed.mapping and "total" not in parsed.mapping:
        warnings.append("Sem coluna de preço: usaremos o preço do cadastro do produto.")
    if parsed.kind == "sales" and "receipt" not in parsed.mapping:
        warnings.append("Sem número de cupom: as vendas de cada dia serão agrupadas em um registro.")
    if parsed.errors:
        warnings.append(f"{len(parsed.errors)} linha(s) com problema serão ignoradas.")
    return {
        "filename": filename,
        "kind": parsed.kind,
        "encoding": parsed.encoding,
        "delimiter": {";": "ponto e vírgula", ",": "vírgula", "\t": "tab", "|": "barra vertical"}.get(
            parsed.delimiter, parsed.delimiter
        ),
        "columns": columns,
        "total_rows": parsed.total_lines,
        "valid_rows": len(parsed.rows),
        "products": len(products),
        "date_from": min(dates).isoformat() if dates else None,
        "date_to": max(dates).isoformat() if dates else None,
        "sample": sample,
        "errors": parsed.errors[:20],
        "warnings": warnings,
    }


# ---------------------------------------------------------------- persistence


async def apply_import(session, market, user, parsed: ParsedFile, raw: bytes, filename: str) -> dict:
    """Write the parsed file into the market. Returns counters plus the product
    ids the caller must (re)process in background: new ones get categorized,
    existing ones get their recommendation recalculated."""
    from sqlalchemy import select

    from app.models import Category, ImportBatch, Product, Sale, SaleItem, StockAdjustment, gen_uuid
    from app.services.seed_data import DEFAULT_CATEGORY_NAME

    digest = file_hash(raw)
    duplicate = await session.scalar(
        select(ImportBatch.id).where(ImportBatch.market_id == market.id, ImportBatch.file_hash == digest)
    )
    if duplicate:
        raise DuplicateImport("Este arquivo já foi importado neste mercado.")

    products = (await session.execute(select(Product).where(Product.market_id == market.id))).scalars().all()
    by_sku = {p.sku.strip().lower(): p for p in products if p.sku}
    by_name = {normalize_name(p.name): p for p in products}
    default_cat = await session.scalar(select(Category).where(Category.name == DEFAULT_CATEGORY_NAME))
    created: dict = {}
    touched: set = set()

    def find(row: ParsedRow):
        if row.sku and row.sku.strip().lower() in by_sku:
            return by_sku[row.sku.strip().lower()]
        return by_name.get(normalize_name(row.product))

    def create(row: ParsedRow, price: Decimal | None) -> "Product":
        p = Product(
            id=gen_uuid(),
            market_id=market.id,
            category_id=default_cat.id if default_cat else None,
            name=row.product.strip(),
            sku=row.sku,
            unit=row.unit or "unidade",
            price=price if price is not None else Decimal("0"),
            cost=row.cost if row.cost is not None else Decimal("0"),
            stock=row.stock if row.stock is not None else Decimal("0"),
            status="processing",
        )
        session.add(p)
        created[p.id] = p
        if p.sku:
            by_sku[p.sku.strip().lower()] = p
        by_name[normalize_name(p.name)] = p
        return p

    sales_created = 0
    if parsed.kind == "sales":
        rows = sorted(parsed.rows, key=lambda r: r.sold_at)
        last_price: dict[str, Decimal] = {}
        for r in rows:
            if r.unit_price is not None:
                last_price[product_key(r.sku, r.product)] = r.unit_price

        groups: dict[tuple, list[ParsedRow]] = {}
        for r in rows:
            key = (r.receipt, r.sold_at.date()) if r.receipt else (None, r.sold_at)
            groups.setdefault(key, []).append(r)

        for group in groups.values():
            sale = Sale(
                id=gen_uuid(),
                market_id=market.id,
                user_id=user.id,
                status="completed",
                source="import",
                sold_at=min(r.sold_at for r in group),
            )
            total = Decimal("0")
            for r in group:
                product = find(r) or create(r, last_price.get(product_key(r.sku, r.product)))
                unit_price = r.unit_price if r.unit_price is not None else Decimal(product.price or 0)
                subtotal = (unit_price * r.quantity).quantize(Decimal("0.01"))
                total += subtotal
                sale.items.append(
                    SaleItem(
                        product_id=product.id,
                        product_name=product.name,
                        category_id=product.category_id,
                        quantity=r.quantity,
                        unit_price=unit_price,
                        subtotal=subtotal,
                    )
                )
                touched.add(product.id)
            sale.total = total
            session.add(sale)
            sales_created += 1
    else:
        for r in parsed.rows:
            p = find(r)
            if p is None:
                create(r, r.unit_price)
                continue
            if r.unit_price is not None:
                p.price = r.unit_price
            if r.cost is not None:
                p.cost = r.cost
            if r.unit:
                p.unit = r.unit
            if r.sku and not p.sku:
                p.sku = r.sku
            if r.stock is not None and p.id not in created and Decimal(p.stock or 0) != r.stock:
                session.add(
                    StockAdjustment(product_id=p.id, delta=r.stock - Decimal(p.stock or 0), reason="Importação do ERP (saldo)")
                )
                p.stock = r.stock
            elif r.stock is not None:
                p.stock = r.stock
            touched.add(p.id)

    updated_ids = [pid for pid in touched if pid not in created]
    dates = [r.sold_at.date() for r in parsed.rows if r.sold_at]
    session.add(
        ImportBatch(
            market_id=market.id,
            user_id=user.id,
            filename=filename[:255],
            file_hash=digest,
            kind=parsed.kind,
            rows=len(parsed.rows),
            products_created=len(created),
            products_updated=len(updated_ids),
            sales_created=sales_created,
        )
    )
    await session.commit()

    if parsed.kind == "sales":
        await sync_item_categories(session, market.id)

    return {
        "kind": parsed.kind,
        "rows_imported": len(parsed.rows),
        "rows_skipped": len(parsed.errors),
        "products_created": len(created),
        "products_updated": len(updated_ids),
        "sales_created": sales_created,
        "items_created": len(parsed.rows) if parsed.kind == "sales" else 0,
        "date_from": min(dates).isoformat() if dates else None,
        "date_to": max(dates).isoformat() if dates else None,
        "errors": parsed.errors[:20],
        "created_ids": list(created.keys()),
        "updated_ids": updated_ids,
    }


class DuplicateImport(ImportError_):
    pass


async def sync_item_categories(session, market_id) -> None:
    """Imported items copy the product's category at import time. If the AI
    was still categorizing (catalog imported seconds before the sales), that
    is the provisional default; align them with the products already ready.
    Products still processing are fixed by the categorizer when it finishes."""
    from sqlalchemy import text

    await session.execute(
        text(
            """
            UPDATE sale_items si
               SET category_id = p.category_id
              FROM products p, sales s
             WHERE si.product_id = p.id
               AND si.sale_id = s.id
               AND s.market_id = :mid
               AND s.source = 'import'
               AND p.status = 'ready'
               AND si.category_id IS DISTINCT FROM p.category_id
            """
        ),
        {"mid": market_id},
    )
    await session.commit()
