from fastapi import FastAPI, Request, Form, UploadFile
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


classes = {
    None: {
        "password": None,
        "schedules": [],
        "preferences": {},
        "days": {}
    }
}


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


@app.get("/health")
async def show_health():
    return {
        "status": "ok",
        "time": datetime.datetime.utcnow().isoformat()
    }


def create_new_day_for_class(classid: str, currentDate):

    today = currentDate.strftime("%A").lower()
    date_key = str(currentDate)

    doc_ref = db.collection("classes").document(classid)
    doc = doc_ref.get()

    if not doc.exists:
        return

    data = doc.to_dict()

    preference = int(data.get("preferences", {}).get("DefaultScheduleIndex", 0))

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


async def create_missing_days(classid: str):

    document = db.collection("classes").document(classid).get()

    if not document.exists:
        return

    data = document.to_dict()

    today = date.today()

    if str(today) not in data.get("days", {}):
        create_new_day_for_class(classid, today)


def get_class_from_session(session_id):

    doc = db.collection("sessions").document(session_id).get()

    if not doc.exists:
        return None

    return doc.to_dict()["classid"]


def get_files_for_class(classid):

    files = []

    document = db.collection("classes").document(classid).get()

    if not document.exists:
        return files

    data = document.to_dict()

    days = data.get("days", {})

    for day, daydata in days.items():

        subjects = daydata.get("subjects", [])

        for subject in subjects:

            folder = f"{classid}/{day}/{subject}"

            try:

                items = supabase.storage.from_("documents").list(folder)

                for item in items:

                    filename = item.get("name")

                    if not filename:
                        continue

                    path = f"{folder}/{filename}"

                    signed = supabase.storage.from_("documents").create_signed_url(
                        path,
                        3600
                    )

                    url = signed.get("signedURL") or signed.get("signed_url")

                    files.append({
                        "day": day,
                        "subject": subject,
                        "name": filename,
                        "path": path,
                        "url": url
                    })

            except Exception:
                pass

    return files


@app.post("/modify-day")
async def modify_day(request: Request):

    form = await request.form()

    session = request.cookies.get("session")

    if not session:
        return RedirectResponse("/login", status_code=303)

    classid = get_class_from_session(session)

    if not classid:
        return RedirectResponse("/login", status_code=303)

    class_doc = db.collection("classes").document(classid).get()

    data = class_doc.to_dict()

    days = data.get("days", {})

    for key, value in form.items():

        # FILE UPLOAD
        if key.startswith("file_") and hasattr(value, "filename"):

            parts = key.replace("file_", "").split("_", 1)

            if len(parts) != 2:
                continue

            day, subject = parts

            file_bytes = await value.read()

            if len(file_bytes) > 5 * 1024 * 1024:
                continue

            filename = f"{random_string(6)}_{value.filename}"

            path = f"{classid}/{day}/{subject}/{filename}"

            try:

                supabase.storage.from_("documents").upload(
                    path,
                    file_bytes,
                    {"content-type": value.content_type}
                )

            except Exception as e:

                logger.warning(f"Upload failed {path}: {e}")

        # DELETE FILE
        if key.startswith("delete_"):

            path = key.replace("delete_", "")

            try:
                supabase.storage.from_("documents").remove([path])
            except Exception as e:
                logger.warning(f"Delete failed {path}: {e}")

        # HOMEWORK
        if key.startswith("homework_"):

            parts = key.replace("homework_", "").split("_", 1)

            if len(parts) != 2:
                continue

            day, subject = parts

            if day in days:

                if "homework" not in days[day]:
                    days[day]["homework"] = {}

                days[day]["homework"][subject] = value

        # COMMENTS
        if key.startswith("comments_"):

            day = key.replace("comments_", "")

            if day in days:
                days[day]["comments"] = value

    db.collection("classes").document(classid).update({
        "days": days
    })

    return RedirectResponse("/app", status_code=303)


@app.post("/login")
async def login(request: Request, classid: str = Form(...), password: str = Form(...)):

    document = db.collection("classes").document(classid).get()

    if not document.exists:

        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Class does not exist"}
        )

    doc = document.to_dict()

    if doc["password"] != password:

        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect password"}
        )

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
        return RedirectResponse("/login", status_code=303)

    classid = get_class_from_session(session)

    if not classid:
        return RedirectResponse("/login", status_code=303)

    await create_missing_days(classid)

    document = db.collection("classes").document(classid).get()

    doc = document.to_dict()

    files = get_files_for_class(classid)

    return templates.TemplateResponse(
        "app.html",
        {
            "request": request,
            "class": classid,
            "schedules": doc.get("schedules", []),
            "days": doc.get("days", {}),
            "files": files
        }
    )


@app.post("/register")
async def register(request: Request, classid: str = Form(...), password: str = Form(...), schedule: UploadFile = Form(...)):

    existing = db.collection("classes").document(classid).get()

    if existing.exists:

        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Class already exists"}
        )

    try:

        schedule_bytes = await schedule.read()

        schedule_json = json.loads(schedule_bytes.decode())

    except Exception:

        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Invalid schedule file"}
        )

    template = copy.deepcopy(classes)

    template[classid] = template.pop(None)

    template[classid]["password"] = password
    template[classid]["schedules"] = schedule_json
    template[classid]["preferences"] = {"DefaultScheduleIndex": 0}

    db.collection("classes").document(classid).set(template[classid])

    create_new_day_for_class(classid, date.today())

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
        {"request": request}
    )


@app.get("/")
async def homepage(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )
