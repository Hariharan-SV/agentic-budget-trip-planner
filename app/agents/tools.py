
import os
import requests
import json
from typing import Dict, List, Any
from app.models.trip import PointOfInterest, Trip, DayPlan # Import DayPlan
import google.generativeai as genai
from app.agents.currency_converter import convert_currency
from app.services.scheduler_service import SchedulerService # Import the SchedulerService class
from pydantic import ValidationError # Import ValidationError

# Configure the generative AI model
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Mapping for Google Places price_level to estimated cost in INR
PRICE_LEVEL_TO_ESTIMATED_COST_INR = {
    0: 0.0,      # Free
    1: 150.0,    # Inexpensive (Updated value)
    2: 500.0,    # Moderate (Updated value)
    3: 1000.0,   # Expensive (Updated value)
    4: 3000.0    # Very Expensive (Updated value)
}

# Default cost for POIs where price_level is not provided by Google Places API
DEFAULT_COST_FOR_NO_PRICE_LEVEL_INR = 300.0 # Example: a small entry fee or average cost if price_level is missing

def get_points_of_interest(destination: str) -> Dict[str, Any]:
    """
    A tool to get points of interest for a given destination using the Google Places API.
    This function now only fetches POIs and stores price_level, but does not compute costs.
    """
    # Reverted: Use GEMINI_API_KEY for Google Places API as per user's clarification
    api_key = os.environ.get("GEMINI_API_KEY") 
    if not api_key:
        return {"status": "failure", "reason": "API key for Google Places not configured."}

    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query=points%20of%20interest%20in%20{destination}&key={api_key}"
    response = requests.get(url)

    if response.status_code != 200:
        return {"status": "failure", "reason": f"Google Places API request failed with status code {response.status_code}"}

    data = response.json()
    if data["status"] != "OK":
        return {"status": "failure", "reason": f"Google Places API error: {data.get('error_message', '')}"}

    unique_pois = {}
    for result in data.get("results", []):
        business_status = result.get("business_status")
        # Skip POIs that are permanently closed
        if business_status == "CLOSED_PERMANENTLY":
            print(f"Skipping permanently closed POI: {result.get('name')}")
            continue

        place_id = result.get("place_id", "")
        google_maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None

        poi = PointOfInterest(
            name=result["name"],
            cost=0.0, # Cost initialized to 0.0, will be computed later by compute_and_assign_poi_costs
            latitude=result["geometry"]["location"]["lat"],
            longitude=result["geometry"]["location"]["lng"],
            place_id=place_id,
            rating=result.get("rating"),
            user_ratings_total=result.get("user_ratings_total"),
            business_status=business_status,
            types=result.get('types'),
            description=result.get('formatted_address'),
            price_level=result.get("price_level"), # Extract and store price_level
            image_url=f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={result['photos'][0]['photo_reference']}" if result.get('photos') else None,
            google_maps_url=google_maps_url # Populate google_maps_url
        )
        print(f"DEBUG: POI created in get_points_of_interest: {poi.name}, Google Maps URL: {poi.google_maps_url}") # Added debug print
        
        unique_key = poi.place_id if poi.place_id else (poi.name, round(poi.latitude, 4), round(poi.longitude, 4))
        
        if unique_key in unique_pois:
            existing_poi = unique_pois[unique_key]
            # Retain the POI with the higher rating if a duplicate is found
            if (poi.rating is not None and existing_poi.rating is None) or (poi.rating is not None and existing_poi.rating is not None and poi.rating > existing_poi.rating):
                unique_pois[unique_key] = poi
        else:
            unique_pois[unique_key] = poi

    return {"status": "success", "pois": list(unique_pois.values())}

def suggest_stays_and_restaurants(destination: str, query_type: str) -> Dict[str, Any]:
    """
    A tool to suggest stays (hotels) or restaurants for a given destination using the Google Places API.
    query_type should be either "hotels" or "restaurants".
    """
    api_key = os.environ.get("GEMINI_API_KEY") 
    if not api_key:
        return {"status": "failure", "reason": "API key for Google Places not configured."}

    if query_type not in ["hotels", "restaurants"]:\
        return {"status": "failure", "reason": "Invalid query_type. Must be 'hotels' or 'restaurants'."}

    query = f"{query_type} in {destination}"
    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={query}&key={api_key}"
    response = requests.get(url)

    if response.status_code != 200:
        return {"status": "failure", "reason": f"Google Places API request failed with status code {response.status_code}"}

    data = response.json()
    if data["status"] != "OK":
        return {"status": "failure", "reason": f"Google Places API error: {data.get('error_message', '')}"}

    suggestions = []
    for result in data.get("results", []):
        business_status = result.get("business_status")
        if business_status == "CLOSED_PERMANENTLY":
            continue

        place_id = result.get("place_id", "")
        google_maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else None

        poi = PointOfInterest(
            name=result["name"],
            cost=0.0, # Cost will be computed later if selected
            latitude=result["geometry"]["location"]["lat"],
            longitude=result["geometry"]["location"]["lng"],
            place_id=place_id,
            rating=result.get("rating"),
            user_ratings_total=result.get("user_ratings_total"),
            business_status=business_status,
            types=result.get('types'),
            description=result.get('formatted_address'),
            price_level=result.get("price_level"),
            image_url=f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={result['photos'][0]['photo_reference']}" if result.get('photos') else None,
            google_maps_url=google_maps_url
        )
        suggestions.append(poi)
    
    return {"status": "success", "pois": suggestions}

def select_pois_by_trip_type(pois: List[PointOfInterest], trip_type: str, destination: str) -> Dict[str, Any]:
    """
    A tool that uses Gemini to select relevant POIs based on the trip type.
    Returns a list of place_ids for the selected POIs.
    """
    # print(f"DEBUG: Starting select_pois_by_trip_type with trip_type: {trip_type} and destination: {destination}")
    # print(f"DEBUG: Input POIs count: {len(pois)}")
    
    if not GEMINI_API_KEY:
        print("DEBUG: GEMINI_API_KEY not set for AI selection.")
        return {"status": "failure", "reason": "GEMINI_API_KEY not set for AI selection."}
    
    model = genai.GenerativeModel('gemini-2.5-flash')

    poi_data_for_ai = []
    for poi in pois:
        poi_data_for_ai.append({
            "place_id": poi.place_id,
            "name": poi.name,
            "description": poi.description,
            "types": poi.types,
            "rating": poi.rating,
            "price_level": poi.price_level,
            "google_maps_url": poi.google_maps_url # Ensure google_maps_url is passed to AI
        })
    # print(f"DEBUG: POI data prepared for AI: {json.dumps(poi_data_for_ai, indent=2)}")

    prompt = f"""
    You are an AI travel planner. Given a list of Points of Interest (POIs) for {destination},
    select the most suitable POIs for a '{trip_type}' trip.
    
    Consider the following guidelines:
    - For 'family' trips, prioritize parks, museums, educational sites, and generally safe and enjoyable places for all ages. Avoid places primarily focused on nightlife or adult entertainment.
    - For 'friends' trips, consider a wider range including cafes, unique experiences, adventure activities, and vibrant spots.
    
    Return only a JSON list of the 'place_id's of the selected POIs. Do not include any other text or explanation.
    
    Here is the list of POIs in JSON format:
    {json.dumps(poi_data_for_ai, indent=2)}
    """
    # print(f"DEBUG: AI Prompt: {prompt}")
    
    try:
        response = model.generate_content(prompt)
        # print(f"DEBUG: AI Raw Response: {response.text}")
        
        # Clean the response text to remove markdown formatting
        cleaned_response_text = response.text.replace('```json', '').replace('```', '').strip()
        # print(f"DEBUG: AI Cleaned Response: {cleaned_response_text}")
        
        selected_place_ids = json.loads(cleaned_response_text)
        if isinstance(selected_place_ids, list) and all(isinstance(pid, str) for pid in selected_place_ids):
            # print(f"DEBUG: AI successfully selected {len(selected_place_ids)} POIs for '{trip_type}' trip.")
            return {"status": "success", "selected_place_ids": selected_place_ids}
        else:
            # print(f"DEBUG: AI returned an invalid format: {response.text}")
            return {"status": "failure", "reason": f"AI returned an invalid format: {response.text}"}
    except Exception as e:
        # print(f"DEBUG: Error during AI POI selection: {e}")
        return {"status": "failure", "reason": f"Failed to select POIs using AI: {str(e)}"}

def compute_and_assign_poi_costs(pois: List[PointOfInterest], currency: str) -> Dict[str, Any]:
    """
    A Python function to compute and assign costs to a list of PointOfInterest objects.
    This function now correctly uses the price_level attribute from the POI object.
    """
    costed_pois = []
    for poi in pois:
        # Use price_level from the POI object for cost computation
        if poi.price_level is not None:
            estimated_cost_inr = PRICE_LEVEL_TO_ESTIMATED_COST_INR.get(poi.price_level, DEFAULT_COST_FOR_NO_PRICE_LEVEL_INR)
        else:
            estimated_cost_inr = DEFAULT_COST_FOR_NO_PRICE_LEVEL_INR
        
        converted_cost = estimated_cost_inr
        if currency != 'INR':
            conversion_result = convert_currency(estimated_cost_inr, "INR", currency)
            if conversion_result["status"] == "failure":
                return conversion_result # Propagate the error
            converted_cost = conversion_result["converted_amount"]

        poi.cost = converted_cost # Assign the computed cost
        costed_pois.append(poi)

    return {"status": "success", "pois": costed_pois}

def schedule_day_wise_itinerary(
    destination: str,
    destination_coords: Dict[str, float],
    duration_days: int,
    points_of_interest: List[PointOfInterest]
) -> Dict[str, Any]:
    """
    A tool to schedule a day-wise itinerary based on a list of POIs and trip duration,
    leveraging Google Distance Matrix and Gemini for intelligent grouping and routing.
    """
    scheduler = SchedulerService()  
    schedule_result = scheduler.schedule_itinerary(destination, destination_coords, duration_days, points_of_interest)
    
    if schedule_result["status"] == "success":
        # CORRECTED: Return DayPlan objects directly, not their model_dump()
        return {"status": "success", "day_plans": schedule_result["day_plans"]}
    else:
        # Add a print statement for clearer failure indication at the tool level
        print(f"Thought: Scheduling failed for {destination}. Reason: {schedule_result.get('reason', 'Unknown scheduling error')}")
        return schedule_result

def generate_poi_descriptions_tool(pois: List[PointOfInterest], destination: str) -> Dict[str, Any]:
    """
    A tool to generate brief, engaging descriptions for a list of Points of Interest using Gemini.
    """
    if not GEMINI_API_KEY:
        return {"status": "failure", "reason": "GEMINI_API_KEY not set for AI description generation."}
    
    model = genai.GenerativeModel('gemini-2.5-flash')
    updated_pois = []
    
    for poi_item in pois:
        # Ensure we are working with a PointOfInterest object
        if isinstance(poi_item, dict):
            try:
                poi = PointOfInterest(**poi_item)
            except ValidationError as e:
                print(f"Warning: Pydantic validation error when converting dict to PointOfInterest in description tool: {e}")
                continue
        elif isinstance(poi_item, PointOfInterest):
            poi = poi_item
        else:
            print(f"Warning: Unexpected type {type(poi_item)} encountered in generate_poi_descriptions_tool. Skipping POI.")
            continue

        print(f"DEBUG(desc_tool): Processing POI of type: {type(poi)}, name: {getattr(poi, 'name', 'N/A')}")
        prompt = f"""
        Provide a brief, engaging description for {poi.name} in {destination}.
        Highlight why it's a significant or interesting place to visit.
        Keep it concise, under 50 words.
        """
        try:
            print(f"Trying to generate description for {prompt}")
            response = model.generate_content(prompt)
            print(f"received f{response}")
            if response and response.candidates:
                poi.description = response.candidates[0].content.parts[0].text
            else:
                poi.description = f"No description available for {poi.name}."
        except Exception as e:
            print(f"Error generating description for {poi.name}: {e}")
            poi.description = f"Could not generate description for {poi.name}."
        updated_pois.append(poi)
    
    print(f"DEBUG(desc_tool): Final updated_pois list contains types: {[type(p) for p in updated_pois]}")
    # CORRECTED: Return a list of PointOfInterest objects directly
    return {"status": "success", "pois": updated_pois}
