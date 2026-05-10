from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Restaurant(SQLModel, table=True):
    __tablename__ = "restaurants"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    city: str
    cuisine: str
    rating: float
    address: str
    delivery_time_mins: int
    is_active: bool = Field(default=True)


class MenuItem(SQLModel, table=True):
    __tablename__ = "menu_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    restaurant_id: UUID = Field(foreign_key="restaurants.id")
    name: str
    description: str
    price: float
    category: str
    is_available: bool = Field(default=True)
    # Semantic search vector — populated once at seed time, nullable until then
    embedding: Optional[list] = Field(
        default=None,
        sa_column=Column(Vector(1536), nullable=True),
    )


class PaymentGateway(SQLModel, table=True):
    __tablename__ = "payment_gateways"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    method: str  # upi | card | netbanking | wallet
    success_rate: float
    fee_percent: float
    is_active: bool = Field(default=True)


class FraudRule(SQLModel, table=True):
    __tablename__ = "fraud_rules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    rule_name: str
    rule_type: str
    threshold: float
    action: str  # flag | block | allow
    description: str


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    telegram_chat_id: Optional[str] = Field(default=None)
    name: str
    email: str
    city: str
    preferences: dict = Field(default_factory=dict, sa_column=Column(JSON))


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    restaurant_id: UUID = Field(foreign_key="restaurants.id")
    item_name: str
    amount: float
    status: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    order_id: Optional[UUID] = Field(default=None, foreign_key="orders.id")
    amount: float
    gateway: str
    method: str
    status: str
    fraud_score: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TelegramSession(SQLModel, table=True):
    __tablename__ = "telegram_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chat_id: str = Field(unique=True, index=True)
    active_run_id: Optional[str] = Field(default=None)
    hitl_status: str = Field(default="idle")
    hitl_expires_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
