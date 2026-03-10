from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from firebase_admin import credentials, firestore
import firebase_admin
from supabase import create_client
import datetime
from datetime import date
import json
import copy
import secrets
import string
import random
import logging
from dotenv import load_dotenv
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def generate_session():
    return secrets.token_urlsafe(32)

def random_string(length: int) -> str:
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


#TEMPLATE STRUCTURE

classes = {
    None: {
        "password": None,
        "schedules": [],
        "preferences": {},
    }
}

#constants
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

cred = credentials.Certificate("credentials.json")

try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

db = firestore.client()

load_dotenv("keys.env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("ANON_KEY")
supabase = create_client(url, key)

@app.post("/modify-day")
async def modify_day():
    return

@app.get("/health")
async def show_health():
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat()
    }

def create_new_day_for_class(classid: str, currentDate):
    #e.g currentDate = date.today()
    #essentially the weekday e.g monday tuesday etc
    today = currentDate.strftime("%A").lower()
    date_key = str(currentDate)

    doc_ref = db.collection("classes").document(classid)
    doc = doc_ref.get()
    data = doc.to_dict()

    preference = int(data["preferences"]["DefaultScheduleIndex"])

    if "days" not in data:
        data["days"] = {}

    if date_key not in data["days"]:
        data["days"][date_key] = {
            "subjects": data["schedules"][preference][today],
            "isHoliday?": False
        }

        doc_ref.update({
            "days": data["days"]
        })

def get_class_from_session(session_id):

    doc = db.collection("sessions").document(session_id).get()

    if not doc.exists:
        return None

    return doc.to_dict()["classid"]

async def create_missing_days(classid: str):
    document = db.collection("classes").document(classid).get()
    for days in document["days"]:
        if date.today() not in days:
            create_new_day_for_class(classid)
    return


@app.post("/upload")
async def upload(file: UploadFile = File(...), classid: str = Form(...), reason: str = Form(...), day: str = Form(...)):

    file_bytes = await file.read()

    result = supabase.storage.from_("documents").upload(
        f"{classid}/{reason}/{day}/{file.filename}",
        file_bytes,
        {"content-type": file.content_type}
    )

    return {"result": result}

@app.post("/login")
async def login(request: Request, classid: str = Form(...), password: str = Form(...)):

    document = db.collection("classes").document(classid).get()

    if not document.exists:

        logger.warning(f"Login failed: class '{classid}' does not exist")

        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Class does not exist"
            }
        )

    doc = document.to_dict()

    if doc["password"] != password:

        logger.warning(f"Login failed: incorrect password for '{classid}'")

        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Incorrect password"
            }
        )

    logger.info(f"Login success: {classid}")

    session_id = generate_session()

    db.collection("sessions").document(session_id).set({
        "classid": classid,
        "created": datetime.datetime.utcnow()
    })

    response = RedirectResponse("/app", status_code=303)
    response.set_cookie(
    key="session",
    value=session_id,
    httponly=True,
    samesite="lax"
    )

    return response

@app.get("/app")
async def app_page(request: Request):

    session = request.cookies.get("session")

    if not session:
        return RedirectResponse("/login")

    classid = get_class_from_session(session)

    if not classid:
        return RedirectResponse("/login")

    document = db.collection("classes").document(classid).get()

    doc = document.to_dict()

    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "class": classid,
            "schedules": doc["schedules"],
            "days": doc["days"],
        }
    )

@app.post("/register")
async def register(request: Request, classid: str = Form(...), password: str = Form(...), schedule: UploadFile = File(...)):

    existing = db.collection("classes").document(classid).get()

    if existing.exists:

        logger.warning(f"Register failed: class '{classid}' already exists")

        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Class already exists"
            }
        )

    try:

        schedule_bytes = await schedule.read()
        schedule_json = json.loads(schedule_bytes.decode())

    except Exception as e:

        logger.error(f"Schedule upload failed for '{classid}'")

        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Invalid schedule file"
            }
        )

    template = copy.deepcopy(classes)

    template[classid] = template.pop(None)

    template[classid]["password"] = password
    template[classid]["schedules"] = schedule_json
    template[classid]["preferences"] = {"DefaultScheduleIndex": 0}

    db.collection("classes").document(classid).set(template[classid])

    logger.info(f"Class registered: {classid}")

    create_new_day_for_class(classid=classid)
    return RedirectResponse("/login", status_code=303)

@app.get("/register")
async def show_register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", 
        {"request": request}
    )

@app.get("/login")
async def show_login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
        }
    )

@app.get("/")
async def homepage(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
        }
    )