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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_session():
    return secrets.token_urlsafe(32)


def random_string(length):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


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


def get_class_from_session(session):

    doc = db.collection("sessions").document(session).get()

    if not doc.exists:
        return None

    return doc.to_dict()["classid"]


def create_new_day_for_class(classid, currentDate):

    today = currentDate.strftime("%A").lower()

    date_key = str(currentDate)

    doc_ref = db.collection("classes").document(classid)

    doc = doc_ref.get()

    data = doc.to_dict()

    pref = int(data.get("preferences", {}).get("DefaultScheduleIndex", 0))

    if "days" not in data:
        data["days"] = {}

    if date_key not in data["days"]:

        data["days"][date_key] = {
            "subjects": data["schedules"][pref][today],
            "isHoliday?": False,
            "homework": {},
            "comments": ""
        }

        doc_ref.update({"days": data["days"]})


def get_files_for_class(classid):

    files = []

    doc = db.collection("classes").document(classid).get()

    data = doc.to_dict()

    days = data.get("days", {})

    for day, d in days.items():

        for subject in d.get("subjects", []):

            folder = f"{classid}/{day}/{subject}"

            try:

                items = supabase.storage.from_("documents").list(folder)

                for item in items:

                    name = item["name"]

                    path = f"{folder}/{name}"

                    signed = supabase.storage.from_("documents").create_signed_url(path,3600)

                    url = signed.get("signedURL") or signed.get("signed_url")

                    files.append({
                        "day": day,
                        "subject": subject,
                        "name": name,
                        "path": path,
                        "url": url
                    })

            except:
                pass

    return files


@app.post("/modify-day")
async def modify_day(request: Request):

    form = await request.form()

    session = request.cookies.get("session")

    if not session:
        return RedirectResponse("/login",303)

    classid = get_class_from_session(session)

    if not classid:
        return RedirectResponse("/login",303)

    doc_ref = db.collection("classes").document(classid)

    doc = doc_ref.get()

    data = doc.to_dict()

    days = data.get("days", {})


    new_day = form.get("new_day")
    subjects = form.get("subjects")

    if new_day and subjects:

        subject_list = [s.strip() for s in subjects.split(",") if s.strip()]

        days[new_day] = {
            "subjects": subject_list,
            "isHoliday?": False,
            "homework": {},
            "comments": ""
        }


    for key, value in form.items():

        if key.startswith("file_") and hasattr(value,"filename"):

            day,subject = key.replace("file_","").split("_",1)

            file_bytes = await value.read()

            if len(file_bytes) > 5*1024*1024:
                continue

            filename = random_string(6)+"_"+value.filename

            path = f"{classid}/{day}/{subject}/{filename}"

            supabase.storage.from_("documents").upload(
                path,
                file_bytes,
                {"content-type": value.content_type}
            )


        if key.startswith("delete_"):

            path = key.replace("delete_","")

            supabase.storage.from_("documents").remove([path])


        if key.startswith("homework_"):

            day,subject = key.replace("homework_","").split("_",1)

            if day in days:

                days[day].setdefault("homework",{})

                days[day]["homework"][subject] = value


        if key.startswith("comments_"):

            day = key.replace("comments_","")

            if day in days:
                days[day]["comments"] = value


    doc_ref.update({"days":days})

    return RedirectResponse("/app",303)


@app.post("/login")
async def login(request: Request, classid: str = Form(...), password: str = Form(...)):

    document = db.collection("classes").document(classid).get()

    if not document.exists:

        return templates.TemplateResponse("login.html",{"request":request,"error":"Class does not exist"})


    doc = document.to_dict()

    if doc["password"] != password:

        return templates.TemplateResponse("login.html",{"request":request,"error":"Incorrect password"})


    session_id = generate_session()

    db.collection("sessions").document(session_id).set({
        "classid": classid,
        "created": datetime.datetime.utcnow()
    })

    response = RedirectResponse("/app",303)

    response.set_cookie("session",session_id,httponly=True,samesite="lax")

    return response


@app.get("/app")
async def app_page(request: Request):

    session = request.cookies.get("session")

    if not session:
        return RedirectResponse("/login",303)

    classid = get_class_from_session(session)

    if not classid:
        return RedirectResponse("/login",303)

    doc = db.collection("classes").document(classid).get()

    data = doc.to_dict()

    files = get_files_for_class(classid)

    return templates.TemplateResponse(
        "app.html",
        {
            "request":request,
            "class":classid,
            "days":data.get("days",{}),
            "schedules":data.get("schedules",[]),
            "files":files
        }
    )


@app.get("/")
async def homepage(request: Request):

    return templates.TemplateResponse("index.html",{"request":request})
