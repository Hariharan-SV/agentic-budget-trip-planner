# Agentic Budget Trip Planner

## 🎯 Goal
Create **AI‑powered, budget‑aware travel itineraries** that adapt to user constraints (budget, time, preferences) using a **planner agent** with a ReAct reasoning loop. The system intelligently calls tools, validates results, and **re‑plans** when constraints aren’t met, ensuring optimal trips.

## ✨ Unique Features
- **Constraint‑driven planning**: Budget, duration, and user preferences are enforced throughout the planning process.
- **ReAct‑based agent**: Thought → Action → Observation loop with automatic re‑planning on failures.
- **Tool‑centric architecture**: Modular tools (POI retrieval, scheduling, cost estimation) make the system extensible.
- **Live integration** with Google Distance Matrix API for realistic travel time calculations.
- **Rich itinerary output**: Detailed schedule, cost breakdown, and creative POI descriptions.

## 🏗️ Architecture Overview
The high‑level design is documented in [`architecture.txt`](architecture.txt). Core components:
- **Planner Agent** – orchestrates the planning workflow.
- **Tools** – wrappers around services (e.g., POI fetch, scheduler).
- **Scheduler Service** – interacts with external APIs.
- **FastAPI backend** – exposes `/plan` endpoint.

## 🚀 Setup & Installation
1. **Python 3.10+** required.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

## ▶️ Running the Application
```bash
uvicorn app.api.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`. Use the `/plan` endpoint to submit a travel request.

## 📋 Example Request
```bash
curl -X POST http://127.0.0.1:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"destination": "Paris", "budget": 1500, "days": 5}'
```
Response includes a day‑by‑day itinerary with POIs, schedule, and cost breakdown.
