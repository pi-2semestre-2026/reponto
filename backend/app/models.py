import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

STATUS_VALUES = ("processing", "ready", "error")
CONFIDENCE_VALUES = ("baixa", "media", "alta")
SALE_STATUS_VALUES = ("completed", "cancelled")


def gen_uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    markets: Mapped[list["Market"]] = relationship(
        back_populates="owner", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    keywords: Mapped[str] = mapped_column(Text, default="")
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list["Product"]] = relationship(back_populates="category", lazy="selectin")


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(Text, default="")
    customers_per_day: Mapped[int] = mapped_column(Integer, default=100)
    replenishment_cycle_days: Mapped[int] = mapped_column(Integer, default=7)
    cycle_unit: Mapped[str] = mapped_column(String(20), default="semanal")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[User] = relationship(back_populates="markets", lazy="selectin")
    products: Mapped[list["Product"]] = relationship(
        back_populates="market", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    unit: Mapped[str] = mapped_column(String(20), default="unidade")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    max_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    recommended_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    learned_rate: Mapped[float] = mapped_column(Float, default=0.0)
    prior_rate: Mapped[float] = mapped_column(Float, default=0.0)
    observed_rate: Mapped[float] = mapped_column(Float, default=0.0)
    alpha: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[str] = mapped_column(String(10), default="baixa")
    status: Mapped[str] = mapped_column(String(12), default="processing")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    market: Mapped[Market] = relationship(back_populates="products", lazy="selectin")
    category: Mapped[Category | None] = relationship(back_populates="products", lazy="selectin")
    recommendation_logs: Mapped[list["RecommendationLog"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category is not None else None


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=gen_uuid)
    market_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String(12), default="completed", index=True)
    sold_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan", lazy="selectin")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sale_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    product_name: Mapped[str] = mapped_column(String(160))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    sale: Mapped[Sale] = relationship(back_populates="items", lazy="selectin")


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True)
    delta: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationLog(Base):
    __tablename__ = "recommendation_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True)
    trigger: Mapped[str] = mapped_column(String(40))
    prior_rate: Mapped[float] = mapped_column(Float)
    observed_rate: Mapped[float] = mapped_column(Float)
    alpha: Mapped[float] = mapped_column(Float)
    final_rate: Mapped[float] = mapped_column(Float)
    safety_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    max_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    recommended_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    window_start: Mapped[dt.date | None] = mapped_column(DateTime(timezone=False), nullable=True)
    window_end: Mapped[dt.date | None] = mapped_column(DateTime(timezone=False), nullable=True)
    n_sales: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(20), default="model")
    details: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="recommendation_logs", lazy="selectin")


class DatasetAggregate(Base):
    """Small aggregated table built once from the public CSVs at boot.

    Rows: mean units sold per transaction for (category, month, weekday, store-size).
    The raw CSVs are never read again at runtime.
    """

    __tablename__ = "dataset_aggregates"
    __table_args__ = (UniqueConstraint("family", "month", "weekday", "size_bucket", name="uq_dataset_agg"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    family: Mapped[str] = mapped_column(String(60), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True)
    month: Mapped[int] = mapped_column(Integer)
    weekday: Mapped[int] = mapped_column(Integer)
    size_bucket: Mapped[int] = mapped_column(Integer)
    avg_sales_per_tx: Mapped[float] = mapped_column(Float)
    n_days: Mapped[int] = mapped_column(Integer, default=0)


class CategoryPrior(Base):
    """Static per-category fallback prior (units per transaction)."""

    __tablename__ = "category_priors"

    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True)
    prior_rate: Mapped[float] = mapped_column(Float, default=0.35)
    n_days: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(lazy="selectin")


SALE_STATUS_ENUM = Enum(*SALE_STATUS_VALUES, name="sale_status")