from pydantic import BaseModel, ConfigDict


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    restaurant_name: str
    restaurant_id: str
    item_name: str
    item_id: str
    price: float
    rating: float
    delivery_time_mins: int
    cuisine: str
    city: str
