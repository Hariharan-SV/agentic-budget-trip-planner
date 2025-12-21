# app/services/scheduler_service.py
import os
import requests
import json
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from app.models.trip import PointOfInterest, DayPlan
from pydantic import ValidationError

class SchedulerService:
    def __init__(self):
        self.google_maps_api_key = os.environ.get("GEMINI_API_KEY")
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        if not self.google_maps_api_key:
            print("WARNING: GOOGLE_MAPS_API_KEY not set. Distance Matrix API will not work.")
        if not self.gemini_api_key:
            print("WARNING: GEMINI_API_KEY not set. AI-driven scheduling will not work.")
        else:
            genai.configure(api_key=self.gemini_api_key)

    def _get_distance_matrix(self, origins: List[PointOfInterest], destinations: List[PointOfInterest]) -> Dict[str, Any]:
        """
        Fetches distance matrix using Google Distance Matrix API, handling MAX_ELEMENTS_EXCEEDED by chunking.
        """
        if not self.google_maps_api_key:
            return {"status": "failure", "reason": "Google Maps API key not configured."}
        
        # API limits: 100 elements (origins * destinations <= 100)
        # Max 10 origins and 10 destinations per request
        block_size = 10 

        num_origins = len(origins)
        num_destinations = len(destinations)

        # Initialize a matrix to store results, mimicking the structure of a full API response
        full_matrix_rows = []
        origin_addresses = [p.name for p in origins] # Store names for convenience
        destination_addresses = [p.name for p in destinations] # Store names

        for i in range(0, num_origins, block_size):
            origin_chunk = origins[i : i + block_size]
            origins_str_chunk = "|".join([f"{p.latitude},{p.longitude}" for p in origin_chunk])
            
            current_row_elements = [None] * num_destinations # Initialize elements for current origins

            for j in range(0, num_destinations, block_size):
                destination_chunk = destinations[j : j + block_size]
                destinations_str_chunk = "|".join([f"{p.latitude},{p.longitude}" for p in destination_chunk])

                url = "https://maps.googleapis.com/maps/api/distancematrix/json"
                params = {
                    "origins": origins_str_chunk,
                    "destinations": destinations_str_chunk,
                    "key": self.google_maps_api_key,
                    "units": "metric"
                }

                try:
                    response = requests.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    if data["status"] == "OK":
                        # Populate the current_row_elements with results from this chunk
                        for row_idx, row in enumerate(data["rows"]):
                            for element_idx, element in enumerate(row["elements"]):
                                # Calculate the global index for the destination
                                global_dest_idx = j + element_idx
                                # Calculate the global index for the origin in the full matrix
                                global_origin_idx = i + row_idx

                                # Ensure full_matrix_rows has enough rows
                                while len(full_matrix_rows) <= global_origin_idx:
                                    full_matrix_rows.append({"elements": [None] * num_destinations})
                                
                                full_matrix_rows[global_origin_idx]["elements"][global_dest_idx] = element
                                
                    else:
                        # If a chunk fails, return failure for the whole operation
                        return {"status": "failure", "reason": f"Distance Matrix API error in chunk: {data.get('error_message', data['status'])}"}
                except requests.exceptions.RequestException as e:
                    return {"status": "failure", "reason": f"Error calling Distance Matrix API in chunk: {e}"}
            
        # Construct the final matrix response in a format similar to the original API response
        final_matrix_response = {
            "destination_addresses": destination_addresses,
            "origin_addresses": origin_addresses,
            "rows": full_matrix_rows,
            "status": "OK"
        }

        return {"status": "success", "matrix": final_matrix_response}

    def _generate_itinerary_with_gemini(self, destination: str, duration_days: int, pois_data: List[Dict[str, Any]], distance_matrix: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses Gemini to generate a day-wise itinerary based on POIs and distance matrix.
        """
        if not self.gemini_api_key:
            return {"status": "failure", "reason": "Gemini API key not configured."}

        model = genai.GenerativeModel('gemini-2.5-flash')

        prompt = f"""
        You are an AI travel planner. Given a list of Points of Interest (POIs) for a {duration_days}-day trip to {destination},
        and a distance matrix indicating travel times between these POIs, create a detailed day-wise itinerary.

        The goal is to group geographically close POIs together for each day to minimize travel time.
        Each day should have a logical flow and avoid excessive travel.

        Here are the POIs in JSON format:
        {json.dumps(pois_data, indent=2)}

        Here is the Google Distance Matrix API response in JSON format (contains distances and durations):
        {json.dumps(distance_matrix, indent=2)}

        Constraints:
        - The trip is for {duration_days} days.
        - Try to distribute the POIs somewhat evenly across the days, but prioritize geographical proximity and logical grouping.
        - The output must be a JSON object, representing a list of daily plans.
        - Each daily plan should include:
            - "day_number": int (e.g., 1, 2, 3)
            - "points_of_interest": List of POI objects (each with 'name', 'place_id', 'latitude', 'longitude', 'cost', 'description', 'google_maps_url', 'image_url). The order of POIs within a day should be optimized for travel.
            - "total_cost_for_day": float (sum of costs of POIs for that day)

        Example of desired JSON output format (DO NOT include ```json or ```):
        [
            {{
                "day_number": 1,
                "points_of_interest": [
                    {{
                        "name": "POI A",
                        "cost": 10.0,
                        "latitude": 1.0,
                        "longitude": 1.0,
                        "place_id": "xyz",
                        "description": "...",
                        "google_maps_url": "...",
                        "image_url": "..."
                    }},
                    {{
                        "name": "POI B",
                        "cost": 15.0,
                        "latitude": 1.1,
                        "longitude": 1.1,
                        "place_id": "abc",
                        "description": "...",
                        "google_maps_url": "...",
                        "image_url": "..."
                    }}
                ],
                "total_cost_for_day": 25.0
            }}
            // ... more day plans
        ]
        """
        try:
            response = model.generate_content(prompt)
            # print(f"Gemini Raw Response: {response.text}")

            # Clean the response to remove markdown formatting if present
            cleaned_response_text = response.text.replace('```json', '').replace('```', '').strip()

            day_plans_data = json.loads(cleaned_response_text)

            # Validate the structure and safely parse
            if isinstance(day_plans_data, list) and all(isinstance(dp, dict) and "day_number" in dp and "points_of_interest" in dp for dp in day_plans_data):
                parsed_day_plans = []
                for dp_data in day_plans_data:
                    pois = []
                    for poi_item in dp_data.get("points_of_interest", []):
                        if isinstance(poi_item, dict): # ADDED THIS CHECK
                            try:
                                # Ensure essential fields are present or provide defaults
                                # before instantiating PointOfInterest
                                safe_poi_item = {
                                    "name": poi_item.get("name", "Unknown POI"),
                                    "cost": poi_item.get("cost", 0.0),
                                    "latitude": poi_item.get("latitude", 0.0),
                                    "longitude": poi_item.get("longitude", 0.0),
                                    "place_id": poi_item.get("place_id"),
                                    "rating": poi_item.get("rating"),
                                    "user_ratings_total": poi_item.get("user_ratings_total"),
                                    "business_status": poi_item.get("business_status"),
                                    "types": poi_item.get("types"),
                                    "description": poi_item.get("description"),
                                    "price_level": poi_item.get("price_level"),
                                    "google_maps_url": poi_item.get("google_maps_url"),
                                    "image_url": poi_item.get("image_url")
                                }
                                pois.append(PointOfInterest(**safe_poi_item))
                            except ValidationError as ve:
                                print(f"Warning: Pydantic validation failed for a POI item from Gemini: {ve}")
                            except Exception as e:
                                print(f"Warning: Unexpected error parsing POI item from Gemini: {e}")
                        else:
                            print(f"Warning: Expected POI item to be a dictionary, but got: {type(poi_item)} - {poi_item}")

                    parsed_day_plans.append(DayPlan(
                        day_number=dp_data["day_number"],
                        points_of_interest=pois,
                        total_cost_for_day=dp_data.get("total_cost_for_day", 0.0)
                    ))
                return {"status": "success", "day_plans": parsed_day_plans}
            else:
                return {"status": "failure", "reason": f"Gemini returned an invalid itinerary format: {response.text}"}
        except json.JSONDecodeError as e:
            return {"status": "failure", "reason": f"Failed to parse Gemini's itinerary response as JSON: {e}. Raw response: {response.text}"}
        except Exception as e:
            return {"status": "failure", "reason": f"Error generating itinerary with Gemini: {e}"}

    def schedule_itinerary(
        self,
        destination: str,
        destination_coords: Dict[str, float],  # lat/lon of the destination city center
        duration_days: int,
        points_of_interest: List[PointOfInterest]
    ) -> Dict[str, Any]:
        """
        Orchestrates the scheduling of a day-wise itinerary using Google Distance Matrix
        and Gemini for intelligent grouping and routing.
        """
        if not points_of_interest:
            return {"status": "success", "day_plans": []}

        # 1. Prepare POI data for Gemini and Distance Matrix
        pois_data_for_gemini = []
        for poi in points_of_interest:
            pois_data_for_gemini.append({
                "name": poi.name,
                "place_id": poi.place_id,
                "latitude": poi.latitude,
                "longitude": poi.longitude,
                "cost": poi.cost,
                "description": poi.description,
                "google_maps_url": poi.google_maps_url,
                "image_url": poi.image_url
            })

        # 2. Get Distance Matrix
        matrix_result = self._get_distance_matrix(points_of_interest, points_of_interest)

        if matrix_result["status"] == "failure":
            return matrix_result  # Propagate the error

        distance_matrix = matrix_result["matrix"]

        # 3. Use Gemini to generate the itinerary
        gemini_itinerary_result = self._generate_itinerary_with_gemini(
            destination,
            duration_days,
            pois_data_for_gemini,
            distance_matrix
        )

        if gemini_itinerary_result["status"] == "failure":
            return gemini_itinerary_result  # Propagate the error

        return {"status": "success", "day_plans": [dp.model_dump() for dp in gemini_itinerary_result["day_plans"]]}
