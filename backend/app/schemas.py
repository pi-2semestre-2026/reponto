import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=2000)
    keywords: str = Field(default="", max_length=2000)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str
    keywords: str
    is_seed: bool


class MarketIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    location: str = Field(default="", max_length=500)
    customers_per_day: int = Field(default=100, ge=1, le=1_000_000)
    cycle_unit: str = Field(default="semanal")
    replenishment_cycle_days: int = Field(default=7, ge=1, le=365)


class MarketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    location: str
    customers_per_day: int
    replenishment_cycle_days: int
    cycle_unit: str
    created_at: dt.datetime


class ProductCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    price: Decimal = Field(ge=0)
    stock: Decimal = Field(ge=0)
    unit: str = Field(default="unidade", max_length=20)


class ProductUpdateIn(BaseModel):
    name: str | None = None
    price: Decimal | None = None
    unit: str | None = None


class StockAdjustIn(BaseModel):
    delta: Decimal
    reason: str = Field(default="", max_length=255)


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    market_id: uuid.UUID
    name: str
    unit: str
    price: Decimal
    stock: Decimal
    min_stock: Decimal
    max_stock: Decimal
    recommended_quantity: Decimal
    learned_rate: float
    prior_rate: float
    observed_rate: float
    alpha: float
    confidence: str
    status: str
    category_id: uuid.UUID | None
    category_name: str | None = None
    created_at: dt.datetime


class SaleItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class SaleCreateIn(BaseModel):
    market_id: uuid.UUID
    items: list[SaleItemIn] = Field(min_length=1)
    sold_at: dt.datetime | None = None


class SaleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: uuid.UUID
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    market_id: uuid.UUID
    total: Decimal
    status: str
    sold_at: dt.datetime
    created_at: dt.datetime
    cancelled_at: dt.datetime | None
    items: list[SaleItemOut]


class LearningLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trigger: str
    prior_rate: float
    observed_rate: float
    alpha: float
    final_rate: float
    safety_stock: Decimal
    min_stock: Decimal
    max_stock: Decimal
    recommended_quantity: Decimal
    window_start: dt.datetime | None
    window_end: dt.datetime | None
    n_sales: int
    source: str
    details: str
    created_at: dt.datetime


class LearningPanelOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    category_name: str | None
    final_rate: float
    prior_rate: float
    observed_rate: float
    alpha: float
    data_share_pct: float
    dataset_share_pct: float
    n_sales: int
    confidence: str
    window_start: dt.datetime | None
    window_end: dt.datetime | None
    source: str
    min_stock: Decimal
    max_stock: Decimal
    recommended_quantity: Decimal
    formula: str
    evolution: list[dict]
    logs: list[LearningLogOut]


class AnalyticsQuery(BaseModel):
    from_date: dt.date
    to_date: dt.date
    market_id: uuid.UUID | None = None


class TopProductOut(BaseModel):
    product_name: str
    category_name: str | None
    quantity: Decimal
    revenue: Decimal


class CategoryRevenueOut(BaseModel):
    category_name: str
    revenue: Decimal
    quantity: Decimal


class DailyPointOut(BaseModel):
    date: dt.date
    revenue: Decimal
    sales_count: int


class PeriodStats(BaseModel):
    revenue: Decimal
    sales_count: int
    items_sold: Decimal
    avg_ticket: Decimal


class LowStockAlert(BaseModel):
    product_id: uuid.UUID
    product_name: str
    market_id: uuid.UUID
    market_name: str
    stock: Decimal
    min_stock: Decimal
    status: str


class MarketOverview(BaseModel):
    market_id: uuid.UUID
    name: str
    customers_per_day: int
    replenishment_cycle_days: int
    products_count: int
    stock_value: Decimal
    low_stock_count: int
    processing_count: int


class AnalyticsOut(BaseModel):
    from_date: dt.date
    to_date: dt.date
    stats: PeriodStats
    previous: PeriodStats
    revenue_change_pct: float | None
    sales_change_pct: float | None
    top_products: list[TopProductOut]
    revenue_by_category: list[CategoryRevenueOut]
    daily_series: list[DailyPointOut]
    stock_by_category: list[CategoryRevenueOut]
    low_stock_alerts: list[LowStockAlert]
    markets_overview: list[MarketOverview]