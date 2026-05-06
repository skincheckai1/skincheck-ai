import os
import io
import sqlite3
import uvicorn
import resend
import secrets
import traceback
from fastapi import FastAPI, File, UploadFile, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import json
import base64
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER,
    gender TEXT,
    email TEXT UNIQUE,
    password TEXT,
    verified INTEGER DEFAULT 0,
    verification_token TEXT,
    reset_token TEXT,
    reset_token_expires TEXT,
    notifications_enabled INTEGER DEFAULT 1
)
    """)
    cursor.execute('CREATE TABLE IF NOT EXISTS routine (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, content TEXT, date TEXT)')
    
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN birthdate TEXT")
    except:
        pass

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        product TEXT,
        reminder_time TEXT,
        frequency TEXT,
        notes TEXT,
        date_created TEXT
    )
    ''')

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN reset_token_expires TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN age INTEGER")
    except:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN gender TEXT")
    except:
        pass

    conn.commit()
    conn.close()

init_db()

# --- AI CONFIG OPENAI ---
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("Manca OPENAI_API_KEY nel file .env")

client = OpenAI(api_key=OPENAI_API_KEY)

print("API KEY USATA:", OPENAI_API_KEY[:12], "...", OPENAI_API_KEY[-6:])

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if not RESEND_API_KEY:
    raise RuntimeError("Manca RESEND_API_KEY nel file .env")

resend.api_key = RESEND_API_KEY

# I tuoi link Awin
AWIN_LINKS = {
    "Clarins": "https://vostro-link-awin-clarins.com",
    "Biotherm": "https://vostro-link-awin-biotherm.com",
    "Kiehl's": "https://vostro-link-awin-kiehls.com",
    "La Roche-Posay": "https://vostro-link-awin-laroche.com"
}



@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

from fastapi.responses import JSONResponse
import hashlib

@app.post("/register")
async def register(
    name: str = Form(...),
    birthdate: str = Form(...),
    gender: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    token = secrets.token_urlsafe(32)

    expires = (datetime.now() + timedelta(minutes=30)).isoformat()

    try:
        cursor.execute(
            "INSERT INTO users (name, birthdate, gender, email, password, verification_token) VALUES (?, ?, ?, ?, ?, ?)",
            (name, birthdate, gender, email, hashed_password, token)
        )
        conn.commit()
      
        verification_link = f"http://127.0.0.1:8000/verify?token={token}"      
       
        # 📩 INVIO EMAIL
        resend.Emails.send({
            "from": "SkinAtelier <onboarding@resend.dev>",
            "to": [email],
            "subject": "Benvenuto su SkinAtelier ✨",
            "html": f"""
            <div style="font-family: Arial, sans-serif; background-color:#FAF7F2; padding:30px;">
                
                <div style="max-width:500px; margin:auto; background:white; padding:25px; border-radius:20px; box-shadow:0 5px 15px rgba(0,0,0,0.05);">
                    
                    <h2 style="color:#D9B99B; text-align:center;">SkinAtelier ✨</h2>
                    
                    <h3 style="text-align:center;">Benvenuto 👋</h3>
                    
                    <p style="text-align:center; font-size:14px;">
                        Il tuo account è stato creato con successo.
                    </p>
                <div style="text-align:center; margin-top:20px;">
                    <a href="{verification_link}" 
                    style="display:inline-block;padding:12px 20px;background:#000;color:#fff;text-decoration:none;border-radius:8px;">
                        Attiva account 🔐
                    </a>
                </div>    

                    <p style="text-align:center; font-size:14px;">
                        Ora puoi analizzare la tua pelle e ricevere consigli personalizzati 💆‍♀️
                    </p>

                    <div style="text-align:center; margin:25px 0;">
                        <a href="http://127.0.0.1:8000"
                        style="background:#D9B99B; color:white; padding:12px 20px; border-radius:12px; text-decoration:none; font-weight:bold;">
                        Inizia ora
                        </a>
                    </div>

                    <p style="font-size:12px; color:gray; text-align:center;">
                        Questa email è stata inviata automaticamente da SkinAtelier AI
                    </p>

                </div>

            </div>
            """
        })

    except:
        conn.close()
        return JSONResponse({"error": "Email già registrata"})

    conn.close()
    return JSONResponse({"status": "ok"})

@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    hashed_password = hashlib.sha256(password.encode()).hexdigest()

    cursor.execute(
        "SELECT id, notifications_enabled, verified FROM users WHERE email = ? AND password = ?",
        (email, hashed_password)
    )

    res = cursor.fetchone()
    conn.close()

    if not res:
        return JSONResponse({"error": "Credenziali errate"})

    if res[2] == 0:
        return JSONResponse({"error": "Devi verificare la tua email"})

    if not res:
        return JSONResponse({"error": "Credenziali errate"})

    return JSONResponse({
        "user_id": res[0],
        "email": email,
        "notifications_enabled": res[1]
    })

@app.post("/update-notifications")
async def update_notifications(user_id: int = Form(...), enabled: int = Form(...)):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET notifications_enabled = ? WHERE id = ?",
        (enabled, user_id)
    )

    conn.commit()
    conn.close()

    return JSONResponse(content={"status": "ok"})

from fastapi.responses import HTMLResponse

@app.get("/verify")
async def verify(token: str):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE verification_token = ?",
        (token,)
    )

    user = cursor.fetchone()

    if not user:
        conn.close()
        return HTMLResponse("<h2>Token non valido ❌</h2>")

    cursor.execute(
        "UPDATE users SET verified = 1 WHERE id = ?",
        (user[0],)
    )

    conn.commit()
    conn.close()

    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="4; url=/">
        <title>Email verificata</title>
    </head>
    <body style="margin:0; font-family:Arial, sans-serif; background:#FAF7F2; display:flex; align-items:center; justify-content:center; height:100vh;">
        <div style="background:white; padding:35px; border-radius:24px; max-width:420px; text-align:center; box-shadow:0 10px 30px rgba(0,0,0,0.08);">
            <h1 style="color:#D9B99B; margin-bottom:10px;">SkinAtelier ✨</h1>
            <h2 style="margin-bottom:10px;">Email verificata ✅</h2>
            <p style="color:#555;">Il tuo account è ora attivo.</p>
            <p style="color:#555;">Tra pochi secondi verrai riportato al login.</p>
            <a href="/" style="display:inline-block; margin-top:20px; background:#D9B99B; color:white; padding:12px 22px; border-radius:12px; text-decoration:none; font-weight:bold;">
                Vai al login
            </a>
        </div>
    </body>
    </html>
    """)

@app.post("/forgot-password")
async def forgot_password(email: str = Form(...)):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return JSONResponse({"error": "Email non trovata"})

    token = secrets.token_urlsafe(32)
    expires = (datetime.now() + timedelta(minutes=30)).isoformat()

    cursor.execute(
        "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
        (token, expires, user[0])
    )

    conn.commit()
    conn.close()

    reset_link = f"http://127.0.0.1:8000/reset-password?token={token}"

    resend.Emails.send({
        "from": "SkinAtelier <onboarding@resend.dev>",
        "to": [email],
        "subject": "Reset password SkinAtelier 🔐",
        "html": f"""
        <div style="font-family:Arial,sans-serif;background:#FAF7F2;padding:30px;">
            <div style="max-width:500px;margin:auto;background:white;padding:25px;border-radius:20px;text-align:center;">
                <h2 style="color:#D9B99B;">SkinAtelier ✨</h2>
                <h3>Reset password 🔐</h3>
                <p>Hai richiesto di cambiare la password.</p>
                <a href="{reset_link}" style="display:inline-block;margin-top:20px;background:#D9B99B;color:white;padding:12px 22px;border-radius:12px;text-decoration:none;font-weight:bold;">
                    Cambia password
                </a>
                <p style="font-size:12px;color:gray;margin-top:20px;">Se non sei stato tu, ignora questa email.</p>
            </div>
        </div>
        """
    })

    return JSONResponse({"status": "ok"})

@app.get("/reset-password")
async def reset_password_page(token: str):
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <title>Reset Password</title>
    </head>
    <body style="margin:0; font-family:Arial; background:#FAF7F2; display:flex; align-items:center; justify-content:center; height:100vh;">
        <div style="background:white; padding:35px; border-radius:24px; max-width:420px; width:100%; text-align:center;">
            <h1 style="color:#D9B99B;">SkinAtelier ✨</h1>
            <h2>Nuova password</h2>

            <form method="POST" action="/reset-password">
                <input type="hidden" name="token" value="{token}">
                <input type="password" name="new_password" placeholder="Nuova password" required
                       style="width:90%; padding:14px; border:1px solid #ddd; border-radius:12px; margin:15px 0;">

                <button type="submit"
                        style="background:#D9B99B; color:white; border:0; padding:14px 22px; border-radius:12px; font-weight:bold; cursor:pointer;">
                    Salva nuova password
                </button>
            </form>
        </div>
    </body>
    </html>
    """)

@app.post("/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    hashed_password = hashlib.sha256(new_password.encode()).hexdigest()

    cursor.execute(
        "SELECT id, reset_token_expires FROM users WHERE reset_token = ?",
        (token,)
    )

    user = cursor.fetchone()

    if not user:
        conn.close()
        return HTMLResponse("<h2>Token non valido ❌</h2>")

    if not user[1]:
        conn.close()
        return HTMLResponse("<h2>Token non valido o scaduto ❌</h2>")

    expires = datetime.fromisoformat(user[1])

    if datetime.now() > expires:
        cursor.execute(
            "UPDATE users SET reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
            (user[0],)
        )
        conn.commit()
        conn.close()
        return HTMLResponse("<h2>Token scaduto ❌</h2><p>Richiedi un nuovo reset password.</p>")

    if not user:
        conn.close()
        return HTMLResponse("<h2>Token non valido ❌</h2>")

    cursor.execute(
        "UPDATE users SET password = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
        (hashed_password, user[0])
    )

    conn.commit()
    conn.close()

    return HTMLResponse("""
    <h2>✅ Password aggiornata!</h2>
    <p>Ora puoi tornare all'app e fare login.</p>
    <a href="/">Vai al login</a>
    """)

@app.post("/analyze")
async def analyze(user_id: int = Form(...), file: UploadFile = File(...)):
    try:
        img_data = await file.read()
        img_base64 = base64.b64encode(img_data).decode("utf-8")

        conn = sqlite3.connect("skincheck.db")
        cursor = conn.cursor()
        cursor.execute("SELECT name, birthdate, gender FROM users WHERE id = ?", (user_id,))
        profile = cursor.fetchone()
        conn.close()

        from datetime import date

        name = profile[0] if profile else "Utente"
        birthdate = profile[1] if profile else None
        gender = profile[2] if profile else "non specificato"

        if birthdate:
            birth = datetime.strptime(birthdate, "%Y-%m-%d").date()
            today = date.today()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        else:
            age = "non specificata"

        profile_prompt = f"""
        Agisci come assistente dermatologico estetico e beauty advisor.

        Profilo utente:
        - Nome: {name}
        - Età: {age}
        - Genere: {gender}

        Regole fondamentali:
        - Se età < 25: focus acne, sebo, pori, pelle giovane
        - Se età 25-35: prevenzione rughe, luminosità, vitamina C, SPF
        - Se età 35-50: anti-age, retinolo, elasticità, macchie
        - Se età > 50: pelle sensibile, nutrizione profonda, barriera cutanea

        IMPORTANTE:
        Adatta SEMPRE prodotti e routine in base all'età.
        Non dare consigli generici.
        """

        json_prompt = """
        Analizza la pelle nella foto e restituisci SOLO JSON valido.
        Non scrivere markdown.
        Non scrivere testo fuori dal JSON.

        Struttura obbligatoria:
        {
        "eta_utente": "eta calcolata",
        "analisi_tecnica": "descrizione chiara della pelle",
        "tipo_pelle": "grassa/secca/mista/sensibile/normale",
        "problemi_rilevati": ["problema 1", "problema 2"],
        "routine_mattina": ["step 1", "step 2", "step 3"],
        "routine_sera": ["step 1", "step 2", "step 3"],
        "trattamenti_settimanali": ["trattamento 1", "trattamento 2"],
        "ingredienti_consigliati": ["Niacinamide", "Acido Salicilico", "Retinolo"],
        "prodotti": [
            {
            "nome": "nome prodotto reale",
            "marca": "CeraVe",
            "piattaforma": "Amazon",
            "categoria": "detergente/siero/crema/SPF",
            "fascia": "top/economico",
            "quando_usarlo": "mattina/sera/mattina e sera",
            "frequenza": "1 volta al giorno / 2 volte al giorno / 2-3 volte a settimana",
            "istruzioni_applicazione": "come applicarlo sulla pelle",
            "orario_consigliato": "08:00 / 14:00 / 21:00",
            "motivo": "perché è consigliato"
            }
        ],
        "promemoria": [
            {
            "titolo": "Applica crema idratante",
            "prodotto": "nome prodotto",
            "orario": "08:00",
            "frequenza": "ogni giorno",
            "note": "applicare dopo la detersione"
            }
        ],
        "disclaimer": "Questa è un'analisi basata su IA, consulta un medico per diagnosi ufficiali."
        }

        Regole:
        - massimo 4 prodotti
        - Amazon: CeraVe, La Roche-Posay, Avène, Eucerin
        - YesStyle: COSRX, Beauty of Joseon, Anua, Isntree
        - tono professionale, rassicurante e semplice
        """

        prompt = profile_prompt + json_prompt

        response = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:{file.content_type};base64,{img_base64}"
                        }
                    ]
                }
            ]
        )

        raw_text = response.output_text.strip()

        if raw_text.startswith("```json"):
            raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text.replace("```", "").strip()

        data = json.loads(raw_text)

        data["eta_utente"] = age
        data["genere_utente"] = gender

        for prodotto in data.get("prodotti", []):
            marca = prodotto.get("marca", "")
            piattaforma = prodotto.get("piattaforma", "")
            query = prodotto.get("nome", "").replace(" ", "+")
            prodotto["image_url"] = f"https://placehold.co/120x120/F5EFE8/8A6A55?text={query}"  

            if piattaforma.lower() == "amazon":
                 prodotto["affiliate_link"] = f"https://www.amazon.it/s?k={query}&tag=TUOTAG-21"
            elif piattaforma.lower() == "yesstyle":
                prodotto["affiliate_link"] = f"https://www.yesstyle.com/en/search.html?q={query}"
            else:
                prodotto["affiliate_link"] = "#"

        date_now = datetime.now().strftime("%Y-%m-%d")

        conn = sqlite3.connect("skincheck.db")
        cursor = conn.cursor()

        # salva analisi
        cursor.execute(
            "INSERT INTO routine (user_id, content, date) VALUES (?, ?, ?)",
            (user_id, json.dumps(data, ensure_ascii=False), date_now)
        )

        # 🔥 salva promemoria
        for reminder in data.get("promemoria", []):
            cursor.execute(
                """
                INSERT INTO reminders (
                    user_id, title, product, reminder_time, frequency, notes, date_created
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    reminder.get("titolo", ""),
                    reminder.get("prodotto", ""),
                    reminder.get("orario", ""),
                    reminder.get("frequenza", ""),
                    reminder.get("note", ""),
                    date_now
                )
            )

        conn.commit()
        conn.close()

        return JSONResponse(content={"result": data})

    except Exception as e:
        print("ERRORE ANALYZE:")
        traceback.print_exc()
        return JSONResponse(content={"result": f"Errore: {str(e)}"}, status_code=500)

@app.get("/get-history/{user_id}")
async def get_history(user_id: int):
    conn = sqlite3.connect('skincheck.db')
    cursor = conn.cursor()
    cursor.execute("SELECT content, date FROM routine WHERE user_id = ? ORDER BY id DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return JSONResponse(content=[{"content": r[0], "date": r[1]} for r in rows])

@app.get("/get-reminders/{user_id}")
async def get_reminders(user_id: int):
    conn = sqlite3.connect("skincheck.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT title, reminder_time, frequency, date_created
        FROM reminders
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))

    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append({
            "title": r[0],
            "time": r[1],
            "frequency": r[2],
            "date": r[3]
        })

    return JSONResponse(content=result)

@app.post("/chat-skin")
async def chat_skin(message: str = Form(...)):

    prompt = f"""
    Sei un consulente skincare professionale.

    Rispondi SOLO in JSON valido.
    Non scrivere markdown.

    L'utente chiede:
    {message}

    Struttura obbligatoria:
    {{
        "risposta": "consiglio semplice e professionale",
        "routine": ["step 1", "step 2", "step 3"],
        "prodotto_consigliato": {{
            "nome": "nome prodotto consigliato",
            "marca": "marca",
            "motivo": "perché è utile",
            "link": "https://www.amazon.it/s?k=skincare"
        }}
    }}

    Regole:
    - Non fare diagnosi mediche
    - Consiglia sempre 1 prodotto acquistabile
    - Usa tono rassicurante
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Sei un consulente skincare esperto."},
            {"role": "user", "content": prompt}
        ]
    )

    raw = response.choices[0].message.content.strip()

    if raw.startswith("```json"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    elif raw.startswith("```"):
        raw = raw.replace("```", "").strip()

    data = json.loads(raw)

    return JSONResponse(data)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)