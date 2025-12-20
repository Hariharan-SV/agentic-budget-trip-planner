
from typing import Dict, List, Union
from app.models.trip import PointOfInterest, Itinerary

def schedule_itinerary(destination: str, pois: List[PointOfInterest], budget: float, currency: str) -> Dict[str, Union[str, Itinerary]]:
    """
    Schedules the itinerary and checks if it's within budget.

    Args:
        destination: The destination of the trip.
        pois: A list of PointOfInterest objects.
        budget: The total budget for the trip.
        currency: The currency of the budget.

    Returns:
        A dictionary with a status and either the itinerary or a reason for failure.
    """
    # print(f"DEBUG: Scheduling itinerary for destination: {destination}, budget: {budget} {currency}")
    # print(f"DEBUG: POIs to schedule: {[poi.name for poi in pois]}")

    total_cost = sum(poi.cost for poi in pois)
    # print(f"DEBUG: Calculated total cost: {total_cost} {currency}")

    if total_cost > budget:
        # print(f"DEBUG: Budget exceeded. Total cost {total_cost} > Budget {budget}")
        return {
            "status": "failure",
            "reason": "budget_exceeded"
        }
    
    # In a real application, this is where you would call the Google Distance Matrix API 
    # to calculate travel times and create an optimized schedule.
    # For this example, we'll just assume a simple linear itinerary.
    
    itinerary = Itinerary(destination=destination, pois=pois, total_cost=total_cost, currency=currency) # Pass destination here
    # print(f"DEBUG: Itinerary successfully created: {itinerary.dict()}")
    
    return {
        "status": "success",
        "itinerary": itinerary
    }
