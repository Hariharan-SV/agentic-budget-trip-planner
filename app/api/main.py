
from fastapi import FastAPI, HTTPException
from app.models.trip import TripRequest, Trip # Import Trip model
from app.agents.planner_agent import PlannerAgent
from app.services.firebase_service import FirebaseService # Import FirebaseService
from typing import Literal, Optional, List
from pydantic import BaseModel

app = FastAPI()
planner_agent = PlannerAgent()
firebase_service = FirebaseService() # Initialize FirebaseService

class UserCreateRequest(BaseModel):
    username: str
    email: Optional[str] = None # Added optional email field

class PlanFinalizeRequest(BaseModel):
    selected_poi_place_ids: List[str]
    generate_descriptions: bool = False

@app.post("/users/{user_id}")
def create_user(user_id: str, request: UserCreateRequest):
    try:
        result = firebase_service.create_user(user_id, request.username, request.email) # Pass email
        if result["status"] == "success":
            return {"message": result["message"], "user_id": user_id}
        else:
            raise HTTPException(status_code=400, detail=result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan/initiate")
def plan_trip_initiate(trip_request: TripRequest, user_id: Optional[str] = None):
    try:
        initiate_result = planner_agent.plan_trip_initiate(trip_request)
        if initiate_result["status"] == "success":
            return {"message": initiate_result["message"], "pois": initiate_result["pois"]}
        else:
            raise HTTPException(status_code=400, detail=initiate_result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan/finalize")
def plan_trip_finalize(request: PlanFinalizeRequest, user_id: Optional[str] = None):
    try:
        finalize_result = planner_agent.plan_trip_finalize(
            selected_poi_place_ids=request.selected_poi_place_ids,
            generate_descriptions=request.generate_descriptions,
            user_id=user_id
        )
        if finalize_result["status"] == "success":
            return finalize_result["trip"]
        else:
            raise HTTPException(status_code=400, detail=finalize_result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/plan_default")
def plan_default_trip(finalize_plan: Optional[bool] = True, user_id: Optional[str] = None):
    try:
        # Create a default trip request
        default_trip_request = TripRequest(
            destination="Bengaluru",
            per_person_budget=5000.0,
            days=3,
            currency="INR",
            trip_type="friends",
            headcount=2
        )
        
        if finalize_plan:
            # Call the unified 'run' method to get the complete itinerary
            result = planner_agent.run(default_trip_request, generate_descriptions=True, user_id=user_id)
            if result["status"] == "success":
                return result["trip"]
            else:
                raise HTTPException(status_code=400, detail=finalize_result["reason"])
        else:
            # Only initiate the trip plan, do not finalize
            initiate_result = planner_agent.plan_trip_initiate(default_trip_request)
            if initiate_result["status"] == "success":
                # Return the list of suggested POIs for user selection
                return {"message": "Trip plan initiated. Please select POIs to finalize.", "pois": initiate_result["pois"]}
            else:
                raise HTTPException(status_code=400, detail=initiate_result["reason"])

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trips/{user_id}/{trip_id}")
def save_or_update_trip(user_id: str, trip_id: str, trip: Trip):
    try:
        save_result = firebase_service.save_trip_itinerary(user_id, trip_id, trip.model_dump())
        if save_result["status"] == "success":
            return {"message": save_result["message"], "trip_id": trip_id}
        else:
            raise HTTPException(status_code=400, detail=save_result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trips/{user_id}/{trip_id}")
def get_saved_trip(user_id: str, trip_id: str):
    try:
        result = firebase_service.get_trip_itinerary(user_id, trip_id)
        if result["status"] == "success":
            return result["trip_data"]
        else:
            raise HTTPException(status_code=404, detail=result["reason"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def read_root():
    return {"message": "Welcome to the AI-Powered Trip Planner API"}
