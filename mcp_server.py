import argparse
import time

from mcp.server import FastMCP

mcp = FastMCP("discuss")

@mcp.tool("weather", "Get the weather in a location")
def get_weather(location):
    return f"Le temps dans {location} est beau."

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