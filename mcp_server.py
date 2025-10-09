import argparse
import json
import sys
import time
import os
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

if __name__ == "__main__":
    # Start the server
    #print("🚀Starting server... ")

    # Debug Mode
    #  uv run mcp dev server.py

    # Production Mode
    # uv run server.py --server_type=sse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server_type", type=str, default="sse", choices=["sse", "stdio"]
    )

    args = parser.parse_args()
    mcp.run(args.server_type)