from pymongo import MongoClient
from core.config import MONGODB_URI
from bson import ObjectId

client = MongoClient(MONGODB_URI)
db = client['notesight']

users_collection = db['users']
reports_collection = db['reports']

def save_student_report(report, report_id=None):
    if report_id:
        reports_collection.update_one(
            {"_id": ObjectId(report_id)},
            {"$set": report}
        )
    else:
        result = reports_collection.insert_one(report)
        report['_id'] = str(result.inserted_id)
    return report


def close_connection():
    client.close()