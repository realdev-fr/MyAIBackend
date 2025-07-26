import argparse
import json
import time
from typing import Annotated

import requests
from kasa import Discover
from llama_index.core.tools import ToolMetadata
from mcp.server import FastMCP

mcp = FastMCP("discuss")

@mcp.tool("weather", "Get the weather in a location")
def get_weather(location):
    API_KEY = "4324d968d209b453e923f375fa2ce14b"
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

        print(data.get("cod"))

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
    "salon": "192.168.1.40",
    "Salon Light": "192.168.1.40",
    "Lumière du salon": "192.168.1.40",
    "Salon Lumière": "192.168.1.40",
    "chambre": "192.168.1.18",
    "Room Light": "192.168.1.18",
    "Lumière de la chambre": "192.168.1.18",
    "Chambre Lumière": "192.168.1.18",
}

@mcp.tool("home_automation_toggle_device", "Toggle the state of a device (like an electrical outlet), on or off")
async def home_automation_toggle_device(device_name, state):
    print("Device name : ", device_name)
    print("State : ", state)
    dev = await Discover.discover_single(deviceMap[device_name], username="natheitz.nh@gmail.com", password="Louneige07,")
    if state.casefold() == "on":
        await dev.turn_on()
    elif state.casefold() == "off":
        await dev.turn_off()

if __name__ == "__main__":
    # Start the server
    print("🚀Starting server... ")

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