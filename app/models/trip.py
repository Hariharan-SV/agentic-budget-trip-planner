
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class PointOfInterest(BaseModel):
    name: str
    cost: float
    latitude: float
    longitude: float
    place_id: str
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    business_status: Optional[str] = None
    types: Optional[List[str]] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[int] = None # Added price_level to the model

class Trip(BaseModel):
    destination: str
    trip_type: str
    budget: float
    currency: str
    pois: List[PointOfInterest]
    total_cost: float
    # Other potential fields like start_date, end_date, etc.

class Itinerary(BaseModel):
    destination: str # Added destination to the Itinerary model
    pois: List[PointOfInterest]
    total_cost: float
    currency: str

class TripRequest(BaseModel):
    destination: str
    per_person_budget: float
    days: int
    currency: Optional[str] = 'INR'
    trip_type: Literal["family", "friends"] = "friends"
    headcount: int = 1

    @property
    def total_trip_cost(self) -> float:
        return self.per_person_budget * self.headcount
