#!/usr/bin/env python3
import time
import os
from datetime import datetime, timezone, timedelta

KSTARSRC_PATH = os.path.expanduser("/home/stellarmate/.config/kstarsrc")
OUTPUT_FILE = "/tmp/kstars_location.txt"

async def gps_main(gps_queue, console_queue, log_queue):
    MultiprocLogging.configurer(log_queue)
    gps_locked = False
    logger.info("GPS MAIN started")

def get_location_from_kstarsrc():
    in_location_section = False
    values = {}

    with open(KSTARSRC_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and "]" in line:
                in_location_section = (line == "[Location]")
                continue

            if in_location_section and "=" in line:
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()

    lat = float(values.get("Latitude", "0.0"))
    lon = float(values.get("Longitude", "0.0"))
    alt = float(values.get("Elevation", "0.0"))
    city = values.get("CityName", "Unknown")
    country = values.get("CountryName", "Unknown")

    return city, country, lat, lon, alt

def get_local_time_with_offset():
    local_time = datetime.now().astimezone()
    return local_time.isoformat()

while True:
    try:
        city, country, lat, lon, alt = get_location_from_kstarsrc()
        utc_time = datetime.now(timezone.utc).isoformat()
        local_time = get_local_time_with_offset()

        output = f"{city},{country},{lat},{lon},{alt},{utc_time},{local_time}"
        with open(OUTPUT_FILE, "w") as f:
            f.write(output + "\n")

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] KStars Location + Time: {output}")

    except Exception as e:
        error_msg = f"ERROR: {e}"
        with open(OUTPUT_FILE, "w") as f:
            f.write(error_msg + "\n")
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")

    time.sleep(10)