from pymongo import MongoClient
from bson import ObjectId
from core.config import MONGO_URI

client = MongoClient(MONGO_URI)
db = client["school_database"]
collection = db["students"]

def save_student_report(report):
    """Saves the generated student report to MongoDB."""
    result = collection.insert_one(report)
    report["_id"] = str(result.inserted_id)
    return report
