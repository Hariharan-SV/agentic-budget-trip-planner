
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field

class PointOfInterest(BaseModel):
    name: str
    cost: float = 0.0 # Default cost to 0.0, will be assigned later
    latitude: float
    longitude: float
    place_id: Optional[str] = None
    rating: Optional[float] = None
    user_ratings_total: Optional[int] = None
    business_status: Optional[str] = None
    types: Optional[List[str]] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    price_level: Optional[int] = None
    google_maps_url: Optional[str] = None # Added google_maps_url

class DayPlan(BaseModel):
    day_number: int
    points_of_interest: List[PointOfInterest]
    total_cost_for_day: float = 0.0

class Trip(BaseModel):
    destination: str
    duration: int # Duration in days
    number_of_people: int
    budget: float # Total budget for the trip
    currency: str = 'INR' # Currency for the budget
    preferences: List[str] = Field(default_factory=list)
    trip_plan: List[DayPlan] = Field(default_factory=list)
    total_estimated_cost: float = 0.0
    cost_per_person: float = 0.0
    suggested_stays: List[Dict[str, Any]] = Field(default_factory=list) # New field for suggested stays
    suggested_restaurants: List[Dict[str, Any]] = Field(default_factory=list) # New field for suggested restaurants

class TripRequest(BaseModel):
    destination: str
    per_person_budget: float
    days: int
    currency: Optional[str] = 'INR'
    trip_type: Literal["family", "friends", "solo"] = "solo" # Added "solo"
    headcount: int = 1

    @property
    def total_trip_cost(self) -> float:
        return self.per_person_budget * self.headcount
