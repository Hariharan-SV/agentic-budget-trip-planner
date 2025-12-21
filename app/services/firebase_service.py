
import firebase_admin
from firebase_admin import credentials, firestore
import os
from typing import List, Dict, Any, Optional

# Initialize Firebase Admin SDK
# You should replace 'path/to/your/serviceAccountKey.json' with the actual path to your Firebase service account key
# It's recommended to store this path in an environment variable for security
try:
    cred = credentials.Certificate(os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY_PATH"))
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase: {e}")
    db = None

class FirebaseService:
    def __init__(self):
        self.db = db

    def create_user(self, user_id: str, username: str, email: Optional[str] = None) -> Dict[str, Any]:
        if not self.db:
            return {"status": "failure", "reason": "Firebase not initialized."}
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_data = {
                "username": username,
                "trip_ids": [] # Initialize with an empty list of trip IDs
            }
            if email:
                user_data["email"] = email
            user_ref.set(user_data, merge=True) # Use merge=True to create if not exists, or update without overwriting other fields
            return {"status": "success", "message": f"User {username} ({user_id}) created/updated successfully."}
        except Exception as e:
            return {"status": "failure", "reason": f"Failed to create/update user: {e}"}

    def add_trip_id_to_user(self, user_id: str, trip_id: str) -> Dict[str, Any]:
        if not self.db:
            return {"status": "failure", "reason": "Firebase not initialized."}
        try:
            user_ref = self.db.collection('users').document(user_id)
            user_ref.update({
                "trip_ids": firestore.ArrayUnion([trip_id])
            })
            return {"status": "success", "message": f"Trip ID {trip_id} added to user {user_id}."}
        except Exception as e:
            return {"status": "failure", "reason": f"Failed to add trip ID to user: {e}"}

    def save_trip_itinerary(self, user_id: str, trip_id: str, trip_data: dict) -> Dict[str, Any]:
        if not self.db:
            return {"status": "failure", "reason": "Firebase not initialized."}
        try:
            doc_ref = self.db.collection('users').document(user_id).collection('trips').document(trip_id)
            doc_ref.set(trip_data)
            # Also add the trip_id to the user's document
            self.add_trip_id_to_user(user_id, trip_id)
            return {"status": "success", "message": f"Trip {trip_id} saved for user {user_id}."}
        except Exception as e:
            return {"status": "failure", "reason": f"Failed to save trip to Firebase: {e}"}

    def get_trip_itinerary(self, user_id: str, trip_id: str) -> Dict[str, Any]:
        if not self.db:
            return {"status": "failure", "reason": "Firebase not initialized."}
        try:
            doc_ref = self.db.collection('users').document(user_id).collection('trips').document(trip_id)
            doc = doc_ref.get()
            if doc.exists:
                return {"status": "success", "trip_data": doc.to_dict()}
            else:
                return {"status": "failure", "reason": f"Trip {trip_id} not found for user {user_id}."}
        except Exception as e:
            return {"status": "failure", "reason": f"Failed to retrieve trip from Firebase: {e}"}
