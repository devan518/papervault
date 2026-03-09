import firebase_admin
from firebase_admin import credentials, firestore
import json
cred = credentials.Certificate("credentials.json")
firebase_admin.initialize_app(cred)

db = firestore.client()


docs = db.collection("classes").stream()

for doc in docs:
    print(doc.id)
    print(json.dumps(doc.to_dict(), indent=2))