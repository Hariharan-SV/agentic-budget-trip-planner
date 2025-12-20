
import os
import google.generativeai as genai
from typing import Dict, Any
from app.models.trip import TripRequest
from app.agents.tools import get_points_of_interest, select_pois_by_trip_type, compute_and_assign_poi_costs, schedule_itinerary_tool, generate_creative_descriptions

# Configure the generative AI model
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class PlannerAgent:
    def __init__(self):
        self.llm = genai.GenerativeModel('gemini-2.5-flash')
        self.tools = {
            "get_points_of_interest": get_points_of_interest,
            "select_pois_by_trip_type": select_pois_by_trip_type,
            "compute_and_assign_poi_costs": compute_and_assign_poi_costs,
            "schedule_itinerary": schedule_itinerary_tool,
            "generate_creative_descriptions": generate_creative_descriptions
        }

    def run(self, trip_request: TripRequest, generate_descriptions: bool = False) -> Dict[str, Any]:
        thought = f"Fetching initial points of interest for {trip_request.destination}."
        print(f"Thought: {thought}")

        # Step 1: Get Raw POIs (without costs computed yet)
        action_result = self.tools["get_points_of_interest"](
            destination=trip_request.destination
        )
        if action_result["status"] == "failure":
            return {"status": "failure", "reason": action_result["reason"]}
        raw_pois = action_result["pois"]
        print(f"Observation: Fetched {len(raw_pois)} raw POIs.")

        if not raw_pois:
            return {"status": "failure", "reason": "No points of interest found for the given destination."}

        # Step 2: AI selects POIs based on trip type
        thought = f"Asking AI to select POIs suitable for a '{trip_request.trip_type}' trip from {len(raw_pois)} options."
        print(f"Thought: {thought}")
        ai_selection_result = self.tools["select_pois_by_trip_type"](
            pois=raw_pois,
            trip_type=trip_request.trip_type,
            destination=trip_request.destination # Pass destination for AI context
        )
        if ai_selection_result["status"] == "failure":
            return {"status": "failure", "reason": ai_selection_result["reason"]}
        selected_place_ids = ai_selection_result["selected_place_ids"]
        print(f"Observation: AI selected {len(selected_place_ids)} POIs.")

        # Filter raw POIs to keep only the AI-selected ones
        selected_pois = [poi for poi in raw_pois if poi.place_id in selected_place_ids]

        if not selected_pois:
            return {"status": "failure", "reason": "AI could not select any suitable points of interest for the given trip type."}

        # Step 3: Compute and assign costs to the selected POIs
        thought = f"Computing and assigning costs for the {len(selected_pois)} selected POIs in {trip_request.currency}."
        print(f"Thought: {thought}")
        cost_computation_result = self.tools["compute_and_assign_poi_costs"](
            pois=selected_pois,
            currency=trip_request.currency
        )
        if cost_computation_result["status"] == "failure":
            return {"status": "failure", "reason": cost_computation_result["reason"]}
        costed_pois = cost_computation_result["pois"]
        print(f"Observation: Costs computed for {len(costed_pois)} POIs.")

        # Re-planning loop for budget (now using costed_pois)
        while True:
            thought = f"Attempting to schedule {len(costed_pois)} POIs within the total budget of {trip_request.currency} {trip_request.total_trip_cost}."
            print(f"Thought: {thought}")

            # Action: Schedule itinerary, now with actual per_person_budget and currency
            action_result = self.tools["schedule_itinerary"](
                destination=trip_request.destination, # Pass destination to scheduler
                pois=costed_pois,
                per_person_budget=trip_request.per_person_budget, # Use per_person_budget for scheduling logic
                currency=trip_request.currency
            )

            if action_result["status"] == "success":
                itinerary = action_result["itinerary"]
                if generate_descriptions:
                    thought = "Itinerary successfully planned within budget. Now generating creative descriptions."
                else:
                    thought = "Itinerary successfully planned within budget. Skipping creative description generation."
                print(f"Thought: {thought}")
                break
            else:
                thought = "Current plan is over budget. Attempting to re-plan by removing the most expensive POI."
                print(f"Thought: {thought}")
                if len(costed_pois) > 1:
                    costed_pois.sort(key=lambda x: x.cost, reverse=True)
                    removed_poi = costed_pois.pop(0)
                    print(f"Removed most expensive POI: {removed_poi.name}. Remaining POIs: {len(costed_pois)}.")
                else:
                    return {"status": "failure", "reason": "Cannot create a plan within the given budget even after removing all but one POI."}
        
        # Action: Generate creative descriptions (conditional)
        if generate_descriptions:
            action_result = self.tools["generate_creative_descriptions"](itinerary)
            if action_result["status"] == "success":
                itinerary = action_result["itinerary"]
        
        thought = "Final trip plan is complete."
        print(f"Thought: {thought}")

        return {"status": "success", "itinerary": itinerary.dict()}
