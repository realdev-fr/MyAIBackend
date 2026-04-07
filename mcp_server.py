import argparse
import datetime
import json
import re
import sys
import time
import os
from pathlib import Path
from typing import Annotated
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

import requests
from kasa import Discover
from llama_index.core.tools import ToolMetadata
from mcp.server import FastMCP

load_dotenv()

mcp = FastMCP("discuss")

LLAMA_URL   = os.getenv("LLAMA_URL",   "http://localhost:8080")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "gemma-4-E2B-it-GGUF")
PDF_OUTPUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", str(Path.home() / "Documents" / "PDFs")))
PDF_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@mcp.tool("weather", "Get the weather in a location")
def get_weather(location):
    API_KEY = os.getenv("OPENWEATHER_API_KEY")
    """First use geocoding to get the latitude and longitude"""
    geocoding_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&appid={API_KEY}"
    geocoding_response = requests.get(geocoding_url)
    geocoding_data = geocoding_response.json()
    lat = geocoding_data[0]["lat"]
    lon = geocoding_data[0]["lon"]

    base_url = "http://api.openweathermap.org/data/2.5/forecast"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": API_KEY,
        "lang": "fr"  # Get response in French
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()

        if data.get("cod") == "200":  # Check if the request was successful
            result = data["list"]
            return json.dumps({
                "type": "raw_weather_data",
                "location": location,
                "data": result  # C’est une liste, la météo sur 5 jours par tranche de 3 heures
            })
        elif data.get("cod") == "404":
            return f"Désolé, je n'ai pas pu trouver la météo pour {location}. Veuillez vérifier le nom de la ville."
        else:
            return f"Une erreur s'est produite lors de la récupération de la météo pour {location}: {data.get('message', 'Unknown error')}"

    except requests.exceptions.RequestException as e:
        return f"Impossible de se connecter à l'API météo : {e}"
    except json.JSONDecodeError:
        return "Erreur de décodage JSON de la réponse de l'API météo."
    except KeyError as e:
        return f"Données météo inattendues reçues de l'API : {e}"
    except Exception as e:
        return f"Une erreur s'est produite lors de la récupération de la météo : {e}"

@mcp.tool("time", "Get the current time")
def get_time():

    return f"Le temps est {time.strftime('%H:%M:%S')}"


deviceMap = {
    "salon": os.getenv("KASA_FIRST_DEVICE_IP"),#192.168.1.40
    "Salon Light": os.getenv("KASA_FIRST_DEVICE_IP"),
    "Lumière du salon": os.getenv("KASA_FIRST_DEVICE_IP"),
    "Salon Lumière": os.getenv("KASA_FIRST_DEVICE_IP"),
    "chambre": os.getenv("KASA_SECOND_DEVICE_IP"),
    "Room Light": os.getenv("KASA_SECOND_DEVICE_IP"),
    "Lumière de la chambre": os.getenv("KASA_SECOND_DEVICE_IP"),
    "Chambre Lumière": os.getenv("KASA_SECOND_DEVICE_IP"),
}

@mcp.tool("home_automation_toggle_device", "Toggle the state of a device (like an electrical outlet), on or off")
async def home_automation_toggle_device(device_name, state):
    #print("Device name : ", device_name)
    #print("State : ", state)
    dev = await Discover.discover_single(deviceMap[device_name], username=os.getenv("KASA_USERNAME"), password=os.getenv("KASA_PASSWORD"))
    if state.casefold() == "on":
        await dev.turn_on()
    elif state.casefold() == "off":
        await dev.turn_off()

    message = {
        "result": {
            "status": "success",
            "message": f"{device_name} switched {state.lower()}"
        }
    }
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()
    return message

@mcp.tool("send_email", "Send an email via Gmail SMTP")
def send_email(to_email: str, subject: str, body: str):
    """
    Send an email using Gmail SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body content
    """
    # Configuration Gmail SMTP
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    GMAIL_USER = os.getenv("GMAIL_USER")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    try:
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = subject

        # Ajouter le corps du message
        msg.attach(MIMEText(body, 'plain'))

        # Connexion au serveur SMTP
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Activer le chiffrement TLS
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)

        # Envoyer l'email
        server.send_message(msg)
        server.quit()

        return json.dumps({
            "status": "success",
            "message": f"Email envoyé avec succès à {to_email}"
        })

    except smtplib.SMTPAuthenticationError:
        return json.dumps({
            "status": "error",
            "message": "Erreur d'authentification SMTP. Vérifiez vos identifiants."
        })
    except smtplib.SMTPException as e:
        return json.dumps({
            "status": "error",
            "message": f"Erreur SMTP: {str(e)}"
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Erreur lors de l'envoi de l'email: {str(e)}"
        })

def _latex_to_unicode(text: str) -> str:
    """Convertit la notation LaTeX mathématique en texte Unicode lisible."""
    # Chiffres/opérateurs + n (ⁿ U+207F présent dans Arial Unicode)
    # Les autres lettres (e, a, b…) restent en ASCII ^x car absentes de la police
    SUP = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")
    SUB = str.maketrans("0123456789",    "₀₁₂₃₄₅₆₇₈₉")

    MATHBB  = {'R': 'ℝ', 'N': 'ℕ', 'Z': 'ℤ', 'Q': 'ℚ', 'C': 'ℂ'}
    # Letterlike Symbols BMP (Arial Unicode OK) — A, C, D, G, J, K, N, O, P, Q, S, T, U, V, W, X, Y, Z
    # n'ont pas d'équivalent BMP → lettre ordinaire
    MATHCAL = {'B': 'ℬ', 'E': 'ℰ', 'F': 'ℱ', 'H': 'ℋ', 'I': 'ℐ', 'L': 'ℒ', 'M': 'ℳ', 'R': 'ℛ'}
    # Ordre important : les plus longs d'abord pour éviter les conflits
    SYMBOLS = [
        (r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)'),
        (r'\\sqrt\{([^}]+)\}',             r'√(\1)'),
        (r'\\mathbb\{([A-Z])\}',  lambda m: MATHBB.get(m.group(1),  m.group(1))),
        (r'\\mathcal\{([A-Z])\}', lambda m: MATHCAL.get(m.group(1), m.group(1))),
        (r'\\infty',        '∞'),  (r'\\int',          '∫'),  (r'\\times',  '×'),
        (r'\\leq',          '≤'),  (r'\\geq',          '≥'),  (r'\\neq',    '≠'),
        (r'\\notin',        '∉'),  (r'\\in\b',         '∈'),  (r'\\subset', '⊂'),
        (r'\\alpha',        'α'),  (r'\\beta',         'β'),  (r'\\gamma',  'γ'),
        (r'\\delta',        'δ'),  (r'\\Delta',        'Δ'),  (r'\\pi\b',   'π'),
        (r'\\theta',        'θ'),  (r'\\lambda',       'λ'),  (r'\\mu\b',   'μ'),
        (r'\\sigma',        'σ'),  (r'\\Sigma',        'Σ'),  (r'\\phi',    'φ'),
        (r'\\omega',        'ω'),  (r'\\Omega',        'Ω'),  (r'\\epsilon','ε'),
        (r'\\ln\b',         'ln'), (r'\\log\b',        'log'),(r'\\cos\b',  'cos'),
        (r'\\sin\b',        'sin'),(r'\\tan\b',        'tan'),(r'\\exp\b',  'exp'),
        (r'\\lim\b',        'lim'),(r'\\sum',          'Σ'),  (r'\\prod',   'Π'),
        (r'\\cdot',         '·'),  (r'\\ldots',        '…'),  (r'\\pm',     '±'),
        (r'\\Leftrightarrow','⟺'),(r'\\Rightarrow',   '⇒'),  (r'\\iff',      '⟺'),
        (r'\\implies',      '⇒'),  (r'\\ell\b',        'ℓ'),
        (r'\\rightarrow',   '→'),  (r'\\leftarrow',    '←'),  (r'\\to\b',     '→'),
        (r'\\forall',       '∀'),  (r'\\exists',       '∃'),
        (r'\\,',            ' '),  (r'\\!',            ''),   (r'\\;',      ' '),
        (r'\\:',            ' '),  (r'\\ ',            ' '),
    ]

    def _sup(s):
        if all(c in "0123456789+-" for c in s):
            return s.translate(SUP)
        return f'^{s}' if len(s) == 1 else f'^({s})'

    def _sub(s):
        if all(c in "0123456789" for c in s):
            return s.translate(SUB)
        return f'_{s}' if len(s) == 1 else f'_({s})'

    def convert(expr: str) -> str:
        e = expr.strip()
        for pat, rep in SYMBOLS:
            e = re.sub(pat, rep, e) if isinstance(rep, str) else re.sub(pat, rep, e)
        # exposants/indices avec accolades
        e = re.sub(r'\^\{([^}]+)\}', lambda m: _sup(m.group(1)), e)
        e = re.sub(r'_\{([^}]+)\}',  lambda m: _sub(m.group(1)), e)
        # exposants/indices simples (chiffre ou lettre unique)
        e = re.sub(r'\^([0-9a-zA-Z])', lambda m: _sup(m.group(1)), e)
        e = re.sub(r'_([0-9a-zA-Z])',  lambda m: _sub(m.group(1)), e)
        # commandes LaTeX restantes + accolades
        e = re.sub(r'\\[a-zA-Z]+\*?', '', e)
        e = e.replace('{', '').replace('}', '')
        return e

    # 1. Blocs display math : \[...\] et $$...$$
    text = re.sub(r'\\\[(.+?)\\\]', lambda m: convert(m.group(1)), text, flags=re.DOTALL)
    text = re.sub(r'\$\$(.+?)\$\$', lambda m: convert(m.group(1)), text, flags=re.DOTALL)
    # 2. Math inline : $...$
    text = re.sub(r'\$(.+?)\$', lambda m: convert(m.group(1)), text)
    # 3. LaTeX nu hors délimiteurs (le LLM omet parfois les $)
    text = convert(text)
    # 4. Supprimer les commandes de structure (\newpage, \hline, etc.)
    text = re.sub(r'\\(newpage|hline|noindent|medskip|bigskip|vspace\{[^}]*\})', '', text)
    return text


@mcp.tool("generate_pdf", "Generate a PDF with a the provided content, subject, and filename and eventually a style")
def generate_pdf(
    content,
    subject,
    filename,
    style: str = "default",
) -> str:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    # Police Unicode avec couverture math complète (∞ ∈ ∫ ≤ ℝ etc.)
    _ARIAL_UNI = "/Library/Fonts/Arial Unicode.ttf"
    _ARIAL_UNI2 = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    _font_path = _ARIAL_UNI if Path(_ARIAL_UNI).exists() else (_ARIAL_UNI2 if Path(_ARIAL_UNI2).exists() else None)
    if _font_path:
        pdfmetrics.registerFont(TTFont("UniFont", _font_path))
        FONT_BODY = "UniFont"
        FONT_BOLD = "UniFont"
    else:
        FONT_BODY = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"

    content = _latex_to_unicode(content)

    # Nom du fichier
    if not filename:
        slug = re.sub(r"[^a-z0-9]+", "_", subject[:40].lower()).strip("_")
        filename = f"{slug}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    output_path = PDF_OUTPUT_DIR / filename

    # Styles
    body_style   = ParagraphStyle("body",   fontName=FONT_BODY, fontSize=11, leading=16, spaceAfter=4, alignment=TA_JUSTIFY)
    h1_style     = ParagraphStyle("h1",     fontName=FONT_BOLD, fontSize=18, leading=24, spaceAfter=8)
    h2_style     = ParagraphStyle("h2",     fontName=FONT_BOLD, fontSize=14, leading=20, spaceAfter=6)
    h3_style     = ParagraphStyle("h3",     fontName=FONT_BOLD, fontSize=12, leading=16, spaceAfter=4)
    bullet_style = ParagraphStyle("bullet", fontName=FONT_BODY, fontSize=11, leading=15, leftIndent=20, spaceAfter=3)
    meta_style   = ParagraphStyle("meta",   fontName=FONT_BODY, fontSize=8,  leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#999999"))

    def inline(t):
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"\*(.+?)\*",     r"<i>\1</i>", t)
        return t

    # Story
    story = []
    now = datetime.datetime.now().strftime("%d/%m/%Y")
    story += [Paragraph(f"Sujet : {subject} · {now}", meta_style), Spacer(1, 4),
              HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A1A2E")), Spacer(1, 14)]

    for line in content.split("\n"):
        s = line.strip()
        if not s:                         story.append(Spacer(1, 6))
        elif s.startswith("### "):        story.append(Paragraph(inline(s[4:]), h3_style))
        elif s.startswith("## "):         story.append(Paragraph(inline(s[3:]), h2_style))
        elif s.startswith("# "):          story.append(Paragraph(inline(s[2:]), h1_style))
        elif s.startswith(("- ", "* ")): story.append(Paragraph(f"• {inline(s[2:])}", bullet_style))
        else:                             story.append(Paragraph(inline(s), body_style))

    #story += [Spacer(1, 20), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")),
              #Paragraph(f"Contenu généré par {LLAMA_MODEL} via llama.cpp", meta_style)]

    doc = SimpleDocTemplate(str(output_path), pagesize=A4,
                            leftMargin=2.5*cm, rightMargin=2.5*cm,
                            topMargin=2.5*cm, bottomMargin=2.5*cm)
    doc.build(story)
    return f"✅ PDF généré : {output_path}"


@mcp.tool("list_pdfs", "Liste les PDFs déjà générés")
def list_pdfs() -> str:
    pdfs = sorted(PDF_OUTPUT_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pdfs:
        return f"Aucun PDF dans {PDF_OUTPUT_DIR}"
    lines = [f"📁 {PDF_OUTPUT_DIR}"]
    for p in pdfs:
        mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        lines.append(f"  • {p.name}  ({p.stat().st_size // 1024} Ko, {mtime})")
    return "\n".join(lines)

if __name__ == "__main__":
    # Start the server
    #print("🚀Starting server... ")

    # Debug Mode
    #  uv run mcp dev server.py

    # Production Mode
    # uv run server.py --server_type=sse

    parser = argparse.ArgumentParser()
    # parser.add_argument(
    #     "--server_type", type=str, default="sse", choices=["sse", "stdio"]
    # )
    parser.add_argument(
        "--server_type", type=str, default="sse", choices=["sse", "stdio", "streamable-http"]
    )

    args = parser.parse_args()
    mcp.run(args.server_type)