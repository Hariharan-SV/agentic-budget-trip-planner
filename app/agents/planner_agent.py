
import os
import google.generativeai as genai
from typing import Dict, Any, List, Optional
from app.models.trip import TripRequest, PointOfInterest, DayPlan, Trip # Import DayPlan and Trip
from app.agents.tools import (
    get_points_of_interest,
    select_pois_by_trip_type,
    compute_and_assign_poi_costs,
    schedule_day_wise_itinerary, # Use the new tool
    generate_poi_descriptions_tool, # Use the new tool for descriptions
    suggest_stays_and_restaurants # Import the new tool
)
from app.services.firebase_service import FirebaseService # Import FirebaseService
from pydantic import ValidationError # Import ValidationError

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
            "schedule_day_wise_itinerary": schedule_day_wise_itinerary, # Updated tool reference
            "generate_poi_descriptions_tool": generate_poi_descriptions_tool, # Corrected tool reference
            "suggest_stays_and_restaurants": suggest_stays_and_restaurants # Add the new tool
        }
        self.current_trip_request: Optional[TripRequest] = None
        self.available_pois: List[PointOfInterest] = [] # This should store PointOfInterest objects
        self.destination_coords: Dict[str, float] = {}
        self.firebase_service = FirebaseService() # Initialize FirebaseService

    def _get_destination_coordinates(self, destination: str) -> Dict[str, float]:
        # TODO: Integrate a dedicated GeoCoding API (e.g., Google Geocoding API) here
        # to get the central coordinates of the destination city for more accurate routing.
        print(f"Thought: Attempting to get coordinates for {destination}.")
        # Placeholder for now. Replace with actual API call.
        return {"latitude": 0.0, "longitude": 0.0} 

    def plan_trip_initiate(self, trip_request: TripRequest) -> Dict[str, Any]:
        self.current_trip_request = trip_request
        self.available_pois = [] # Reset available POIs for a new request

        thought = f"Fetching initial points of interest for {trip_request.destination}."
        print(f"Thought: {thought}")

        # Step 1: Get Raw POIs (returns List[PointOfInterest])
        action_result = self.tools["get_points_of_interest"](
            destination=trip_request.destination
        )
        if action_result["status"] == "failure":
            return {"status": "failure", "reason": action_result["reason"]}
        raw_pois = action_result["pois"]
        print(f"DEBUG(planner_agent): Type of raw_pois from get_points_of_interest: {[type(p) for p in raw_pois[:min(5, len(raw_pois))]]}") # Debug log

        if not raw_pois:
            return {"status": "failure", "reason": "No points of interest found for the given destination."}
        
        # Store the fetched POIs (which are PointOfInterest objects) directly
        self.available_pois = raw_pois
        print(f"DEBUG(planner_agent): Type of self.available_pois after storing: {[type(p) for p in self.available_pois[:min(5, len(self.available_pois))]]}") # Debug log

        # Try to get destination coordinates. For simplicity, we can use the first POI's coords as a proxy
        # or a dedicated geocoding tool. For now, a placeholder.
        self.destination_coords = self._get_destination_coordinates(trip_request.destination)
        if (not self.destination_coords.get("latitude") and not self.destination_coords.get("longitude")) and self.available_pois:
            self.destination_coords = {
                "latitude": self.available_pois[0].latitude,
                "longitude": self.available_pois[0].longitude
            }
            print(f"Thought: Using first POI's coordinates as destination coordinates for initial planning: {self.destination_coords}")

        # Step 2: AI selects POIs based on trip type (expects List[PointOfInterest], returns List[str] of place_ids)
        thought = f"Asking AI to select POIs suitable for a '{trip_request.trip_type}' trip from {len(raw_pois)} options."
        print(f"Thought: {thought}")
        ai_selection_result = self.tools["select_pois_by_trip_type"](
            pois=raw_pois, # Pass PointOfInterest objects
            trip_type=trip_request.trip_type,
            destination=trip_request.destination # Pass destination for AI context
        )
        if ai_selection_result["status"] == "failure":
            return {"status": "failure", "reason": ai_selection_result["reason"]}
        selected_place_ids = ai_selection_result["selected_place_ids"]
        print(f"Observation: AI selected {len(selected_place_ids)} POIs.")

        # Filter available POIs (which are PointOfInterest objects) to keep only the AI-selected ones
        self.available_pois = [poi for poi in self.available_pois if poi.place_id in selected_place_ids]
        print(f"DEBUG(planner_agent): Type of self.available_pois after AI selection: {[type(p) for p in self.available_pois[:min(5, len(self.available_pois))]]}") # Debug log

        if not self.available_pois:
            return {"status": "failure", "reason": "AI could not select any suitable points of interest for the given trip type."}

        # Present the filtered POIs to the user for selection (as dictionaries for API response)
        return {
            "status": "success",
            "message": "Here are some points of interest I found. Please select the ones you'd like to include in your trip.",
            "pois": [poi.model_dump() for poi in self.available_pois] # Convert to dicts for API response
        }

    def plan_trip_finalize(self, selected_poi_place_ids: List[str], generate_descriptions: bool = False, user_id: Optional[str] = None) -> Dict[str, Any]:
        if not self.current_trip_request:
            return {"status": "failure", "reason": "No trip request initiated. Please start a trip plan first."}
        if not self.available_pois: # self.available_pois should be List[PointOfInterest] here
            return {"status": "failure", "reason": "No available POIs to select from. Please start a trip plan first."}

        # Filter the available POIs (PointOfInterest objects) based on user's selection
        user_selected_pois = [poi for poi in self.available_pois if poi.place_id in selected_poi_place_ids]
        print(f"DEBUG(planner_agent): Type of user_selected_pois: {[type(p) for p in user_selected_pois[:min(5, len(user_selected_pois))]]}") # Debug log

        if not user_selected_pois:
            return {"status": "failure", "reason": "No valid POIs selected by the user."}

        # Step 3: Compute and assign costs to the user-selected POIs (expects List[PointOfInterest], returns List[PointOfInterest])
        thought = f"Computing and assigning costs for the {len(user_selected_pois)} user-selected POIs in {self.current_trip_request.currency}."
        print(f"Thought: {thought}")
        cost_computation_result = self.tools["compute_and_assign_poi_costs"](
            pois=user_selected_pois,
            currency=self.current_trip_request.currency
        )
        if cost_computation_result["status"] == "failure":
            return {"status": "failure", "reason": cost_computation_result["reason"]}
        costed_user_selected_pois = cost_computation_result["pois"]
        print(f"Observation: Costs computed for {len(costed_user_selected_pois)} POIs.")
        print(f"DEBUG(planner_agent): Type of costed_user_selected_pois: {[type(p) for p in costed_user_selected_pois[:min(5, len(costed_user_selected_pois))]]}") # Debug log

        final_trip = None
        re_planning_attempts = 0
        MAX_REPLANNING_ATTEMPTS = 5 # Prevent infinite loops

        while final_trip is None and re_planning_attempts < MAX_REPLANNING_ATTEMPTS:
            if not costed_user_selected_pois:
                return {"status": "failure", "reason": "Cannot create a plan within the given budget even after removing all POIs."}

            # Step 4: Schedule day-wise itinerary (expects List[PointOfInterest], returns List[DayPlan])
            thought = f"Attempt {re_planning_attempts + 1}: Scheduling a {self.current_trip_request.days}-day itinerary for {self.current_trip_request.destination} with {len(costed_user_selected_pois)} selected POIs.\nTotal trip budget: {self.current_trip_request.total_trip_cost} {self.current_trip_request.currency}."
            print(f"Thought: {thought}")

            # Ensure destination_coords are set, use a fallback if not explicitly defined
            if (not self.destination_coords.get("latitude") and not self.destination_coords.get("longitude")):
                if costed_user_selected_pois:
                    self.destination_coords = {
                        "latitude": costed_user_selected_pois[0].latitude,
                        "longitude": costed_user_selected_pois[0].longitude
                    }
                    print(f"Thought: Fallback: Using first selected POI's coordinates as destination coordinates for scheduling: {self.destination_coords}")
                else:
                    return {"status": "failure", "reason": "Could not determine destination coordinates for scheduling."}

            schedule_result = self.tools["schedule_day_wise_itinerary"](
                destination=self.current_trip_request.destination,
                destination_coords=self.destination_coords,
                duration_days=self.current_trip_request.days,
                points_of_interest=costed_user_selected_pois
            )

            if schedule_result["status"] == "failure":
                return schedule_result # Propagate scheduling errors
            
            # day_plans from schedule_day_wise_itinerary is already List[DayPlan] objects
            day_plans = schedule_result["day_plans"]
            print(f"DEBUG(planner_agent): Type of day_plans from scheduler: {[type(dp) for dp in day_plans[:min(5, len(day_plans))]]}") # Debug log
            
            # Construct the current Trip object for budget check
            current_trip_for_check = Trip(
                destination=self.current_trip_request.destination,
                duration=self.current_trip_request.days,
                number_of_people=self.current_trip_request.headcount,
                budget=self.current_trip_request.total_trip_cost,
                currency=self.current_trip_request.currency,
                preferences=[self.current_trip_request.trip_type], # Fixed type issue
                trip_plan=day_plans # Directly assign List[DayPlan] objects
            )
            
            # Recalculate total estimated cost from the scheduled day_plans
            current_trip_for_check.total_estimated_cost = sum(dp.total_cost_for_day for dp in current_trip_for_check.trip_plan)
            
            if current_trip_for_check.total_estimated_cost <= current_trip_for_check.budget:
                final_trip = current_trip_for_check # Budget is met, assign to final_trip
                print(f"Observation: Itinerary successfully scheduled within budget. Total estimated cost: {final_trip.total_estimated_cost} {final_trip.currency}.")
            else:
                thought = f"Observation: Current plan's estimated cost ({current_trip_for_check.total_estimated_cost} {current_trip_for_check.currency}) exceeds budget ({current_trip_for_check.budget} {current_trip_for_check.currency}). Attempting to re-plan by removing the most expensive POI.\nRemaining POIs: {len(costed_user_selected_pois)}."
                print(f"Thought: {thought}")
                
                if len(costed_user_selected_pois) > 1:
                    # Flatten all POIs to find the most expensive one globally for removal
                    all_pois_flat = []
                    for dp in day_plans:
                        all_pois_flat.extend(dp.points_of_interest)
                    all_pois_flat.sort(key=lambda x: x.cost, reverse=True)
                    
                    most_expensive_poi = all_pois_flat[0]
                    # Remove the most expensive POI from the list for the next scheduling attempt
                    costed_user_selected_pois = [p for p in costed_user_selected_pois if p.place_id != most_expensive_poi.place_id]
                    print(f"Observation: Removed most expensive POI: {most_expensive_poi.name} (Cost: {most_expensive_poi.cost} {current_trip_for_check.currency}). Remaining POIs for re-planning: {len(costed_user_selected_pois)}.")
                else:
                    print("Observation: Only one or zero POIs remaining. Cannot remove more to meet budget.")
                    return {"status": "failure", "reason": "Cannot create a plan within the given budget even after removing all but one POI."}
            
            re_planning_attempts += 1
        
        if final_trip is None:
            return {"status": "failure", "reason": f"Could not create a plan within budget after {MAX_REPLANNING_ATTEMPTS} attempts."}

        # Calculate cost per person for the final trip
        final_trip.cost_per_person = final_trip.total_estimated_cost / final_trip.number_of_people if final_trip.number_of_people > 0 else 0.0

        # Step 5: Generate creative descriptions (conditional)
        if generate_descriptions:
            thought = "Itinerary successfully scheduled. Now generating creative descriptions for each POI."
            print(f"Thought: {thought}")
            # Flatten all POIs from day_plans to pass to the description tool
            all_pois_in_plan = []
            for day_plan in final_trip.trip_plan:
                all_pois_in_plan.extend(day_plan.points_of_interest)
            
            print(f"DEBUG(planner_agent): Type of items in all_pois_in_plan before description tool: {[type(p) for p in all_pois_in_plan[:min(5, len(all_pois_in_plan))]]}") # Debug log
            description_result = self.tools["generate_poi_descriptions_tool"](
                pois=all_pois_in_plan,
                destination=final_trip.destination
            )
            if description_result["status"] == "success":
                updated_pois_from_tool = description_result["pois"]
                print(f"DEBUG(planner_agent): Type of items in updated_pois_from_tool (from desc tool): {[type(p) for p in updated_pois_from_tool[:min(5, len(updated_pois_from_tool))]]}") # Debug log
                updated_pois_map = {p.place_id: p for p in updated_pois_from_tool}
                print(f"DEBUG(planner_agent): Type of values in updated_pois_map: {[type(v) for v in updated_pois_map.values()][:min(5, len(updated_pois_map))]}") # Debug log
                
                for day_plan in final_trip.trip_plan:
                    for i, poi in enumerate(day_plan.points_of_interest):
                        print(f"DEBUG(planner_agent): Before update - Day {day_plan.day_number}, POI {poi.name}, Type: {type(poi)}") # Debug log
                        if poi.place_id in updated_pois_map:
                            # Replace the old POI object with the updated one (including description)
                            day_plan.points_of_interest[i] = updated_pois_map[poi.place_id]
                            print(f"DEBUG(planner_agent): After update - Day {day_plan.day_number}, POI {day_plan.points_of_interest[i].name}, Type: {type(day_plan.points_of_interest[i])}") # Debug log

        # Step 6: Suggest stays and restaurants
        thought = "Suggesting stays and restaurants in the destination."
        print(f"Thought: {thought}")

        stays_result = self.tools["suggest_stays_and_restaurants"](
            destination=self.current_trip_request.destination,
            query_type="hotels"
        )
        if stays_result["status"] == "success":
            final_trip.suggested_stays = [poi.model_dump() for poi in stays_result["pois"]]
            print(f"Observation: Found {len(final_trip.suggested_stays)} suggested stays.")
        else:
            print(f"Observation: Failed to suggest stays: {stays_result['reason']}")

        restaurants_result = self.tools["suggest_stays_and_restaurants"](
            destination=self.current_trip_request.destination,
            query_type="restaurants"
        )
        if restaurants_result["status"] == "success":
            final_trip.suggested_restaurants = [poi.model_dump() for poi in restaurants_result["pois"]]
            print(f"Observation: Found {len(final_trip.suggested_restaurants)} suggested restaurants.")
        else:
            print(f"Observation: Failed to suggest restaurants: {restaurants_result['reason']}")

        # Save the finalized trip to Firebase if user_id is provided
        if user_id:
            thought = f"Saving finalized trip for user {user_id} to Firebase."
            print(f"Thought: {thought}")
            save_result = self.firebase_service.save_trip_itinerary(
                user_id=user_id,
                trip_id=f"{user_id}_{final_trip.destination}_{final_trip.duration}_{final_trip.number_of_people}_{final_trip.total_estimated_cost}", # Simple trip ID
                trip_data=final_trip.model_dump()
            )
            if save_result["status"] == "success":
                print(f"Observation: {save_result['message']}")
            else:
                print(f"Observation: Failed to save trip to Firebase: {save_result['reason']}")

        thought = "Final trip plan is complete."
        print(f"Thought: {thought}")

        return {"status": "success", "trip": final_trip.model_dump()}

    # Re-introducing a 'run' method for backward compatibility with the existing API structure.
    # In a full multi-turn interaction, the API would directly call plan_trip_initiate and plan_trip_finalize.
    def run(self, trip_request: TripRequest, generate_descriptions: bool = False, user_id: Optional[str] = None) -> Dict[str, Any]:
        # Initiate the trip plan to get available POIs
        initiate_result = self.plan_trip_initiate(trip_request)
        if initiate_result["status"] == "failure":
            return initiate_result
        
        # Extract all place_ids from the initially suggested POIs for auto-selection
        # In a real scenario, the user would interact and select a subset of these.
        # IMPORTANT: initiate_result["pois"] is List[dict] due to plan_trip_initiate's return.
        # We need to re-hydrate these into PointOfInterest objects for plan_trip_finalize.
        rehydrated_pois_from_initiate = []
        for poi_data in initiate_result["pois"]:
            try:
                rehydrated_pois_from_initiate.append(PointOfInterest(**poi_data))
            except ValidationError as e:
                print(f"Error: Validation failed rehydrating POI from initiate_result: {e}")
                return {"status": "failure", "reason": f"Internal error: failed to process POIs for finalization: {e}"}
        
        # Update self.available_pois with the rehydrated PointOfInterest objects
        self.available_pois = rehydrated_pois_from_initiate
        
        all_suggested_poi_place_ids = [poi.place_id for poi in self.available_pois if poi.place_id] # Access place_id on object

        # Finalize the trip plan with the auto-selected POIs and pass generate_descriptions
        finalize_result = self.plan_trip_finalize(all_suggested_poi_place_ids, generate_descriptions, user_id) # Pass user_id
        return finalize_result
