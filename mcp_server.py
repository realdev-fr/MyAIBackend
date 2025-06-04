import argparse
import json
import time

import requests
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

    base_url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": API_KEY,
        "units": "metric",  # Get temperature in Celsius
        "lang": "fr"  # Get response in French
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()

        if data.get("cod") == 200:  # Check if the request was successful
            main_weather = data["weather"][0]["description"]
            temperature = data["main"]["temp"]
            feels_like = data["main"]["feels_like"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]  # in m/s

            return (
                f"Le temps à {location} est : {main_weather.capitalize()}. "
                f"Température : {temperature}°C (ressenti : {feels_like}°C). "
                f"Humidité : {humidity}%. Vent : {wind_speed} m/s."
            )
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