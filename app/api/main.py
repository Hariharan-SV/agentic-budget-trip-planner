
from fastapi import FastAPI, HTTPException
from app.models.trip import TripRequest
from app.agents.planner_agent import PlannerAgent
from typing import Literal

app = FastAPI()
planner_agent = PlannerAgent()

@app.post("/plan")
def plan_trip(trip_request: TripRequest):
    try:
        result = planner_agent.run(trip_request)
        if result["status"] == "success":
            return result["itinerary"]
        else:
            raise HTTPException(status_code=400, detail=result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI-Powered Trip Planner API"}

@app.get("/plan_default")
def plan_trip_default(
    destination: str = "Bengaluru",
    days: int = 2,
    per_person_budget: float = 5000.0,
    trip_type: Literal["family", "friends"] = "friends",
    headcount: int = 1,
    generate_descriptions: bool = True  # Added toggle parameter
):
    trip_request = TripRequest(
        destination=destination,
        per_person_budget=per_person_budget,
        days=days,
        trip_type=trip_type,
        headcount=headcount
    )
    try:
        result = planner_agent.run(trip_request, generate_descriptions=generate_descriptions) # Pass toggle to agent
        if result["status"] == "success":
            return {**result["itinerary"], "total_trip_cost": trip_request.total_trip_cost}
        else:
            raise HTTPException(status_code=400, detail=result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
