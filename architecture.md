Trip Planner — Architecture (Agentic)

Version: 1.0
Last updated: 2025-12-20

## 1. Overview

This document outlines the architecture for the AI-Powered Trip Planner, an **agentic system** designed to dynamically create travel itineraries that adhere to complex constraints.

The application is centered around a **Planner Agent**. This agent uses a reasoning framework (ReAct) to interpret user goals, break them down into steps, and select the appropriate **Tool** for each step. Critically, the agent can **check the output of its actions against the user's constraints (like budget) and re-plan its approach if those constraints are not met.**

## 2. Core Concepts

*   **Planner Agent**: The "brain" of the system, powered by an LLM (gemini-2.5-flash). It coordinates the use of tools to construct a final plan that meets user-defined goals.
*   **Tools**: Atomic functions that the agent can execute. They are wrappers around the application's services. Tools are designed to return clear status and data, including failures (e.g., `status: 'failure', reason: 'budget_exceeded'`).
*   **Reason-Act (ReAct) Loop**: The agent operates in a cycle of **Thought -> Action -> Observation**. This loop is not just for planning, but also for **validation and correction**.
    1.  **Thought**: The agent decides what to do next. (e.g., "I will attempt to schedule the selected POIs.")
    2.  **Action**: The agent executes a tool. (e.g., Call `schedule_itinerary`.)
    3.  **Observation**: The agent receives the result.
        *   If the tool succeeds, the agent proceeds to the next logical step.
        *   If the tool fails (e.g., budget is exceeded), the agent's next **Thought** is a corrective one. (e.g., "The plan was over budget. I will remove the most expensive POI and re-run the `schedule_itinerary` tool.") This initiates the **re-planning loop**.

---

## 3. Folder Structure & File Descriptions

```
.
├── app/
│   ├── agents/
│   │   ├── planner_agent.py    # Defines the core agent, its LLM, and the ReAct execution loop. Contains the re-planning logic.
│   │   └── tools.py            # Wraps services into tools. Tools are designed to return status objects.
│   ├── api/
│   ├── models/
│   └── services/
│       ├── scheduler_service.py # Logic for scheduling POIs. Returns a detailed status, including whether the budget was met.
(other files as before)
```

---


## 4. High-Level Component Diagram

The component relationships remain the same, but the logic within the **Planner Agent** is now more sophisticated, containing the re-planning loop.

<img width="457" height="684" alt="image" src="https://github.com/user-attachments/assets/3a5431c9-d618-4d3b-a4db-30f13df933b6" />

