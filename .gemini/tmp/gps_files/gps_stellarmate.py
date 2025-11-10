#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module is for GPS related functions
"""

import asyncio
from PiFinder.multiproclogging import MultiprocLogging
import aiohttp
import sys
import os
from datetime import datetime
import logging

logger = logging.getLogger("GPS")
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

async def read_kstars_location_file(gps_queue):
    logger.info("KStars API reader started (gps_gpsd.py)")
    url = "http://localhost:8624/api/info/location"

    def read_elevation_fallback():
        kstarsrc_path = os.path.expanduser("~/.config/kstarsrc")
        try:
            with open(kstarsrc_path, "r") as f:
                in_location = False
                for line in f:
                    line = line.strip()
                    if line == "[Location]":
                        in_location = True
                    elif in_location:
                        if line.startswith("[") and line != "[Location]":
                            break
                        if line.startswith("Elevation="):
                            try:
                                return float(line.split("=", 1)[1])
                            except ValueError:
                                return 0.0
        except Exception as e:
            logger.warning(f"Could not read elevation from kstarsrc: {e}")
        return 0.0

    last_coords = None

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.debug(f"KStars API raw response: {data}")
                        result = data.get("success", {})
                        lat = float(result.get("latitude", 0))
                        lon = float(result.get("longitude", 0))
                        alt = result.get("altitude")
                        if alt is None or float(alt) == 0.0:
                            alt = read_elevation_fallback()
                            result["altitude"] = alt
                        alt = float(alt)
                        coords = (lat, lon, alt)
                        logger.debug(f"Parsed coordinates: lat={lat}, lon={lon}, alt={alt}")
                        # Always put the message into the queue, even if coordinates are the same
                        # The main loop handles filtering if needed.
                        # if coords == last_coords:
                        #    await asyncio.sleep(5)
                        #    continue
                        last_coords = coords
                        tz = result.get("tz", 0)

                        msg = (
                            "fix",
                            {
                                "lat": lat,
                                "lon": lon,
                                "altitude": alt,
                                "source": "KStarsAPI",
                                "lock": True,
                                "error_in_m": 10,
                            },
                        )
                        logger.info(f"Putting GPS fix message into queue: {msg}")
                        gps_queue.put(msg)

                        if tz:
                            now = datetime.utcnow()
                            msg_time = ("time", {"time": now})
                            gps_queue.put(msg_time)

                        logger.info(f"KStars GPS API fix injected: {msg}")
                    else:
                        logger.warning(f"KStars API error: HTTP {response.status}")
        except Exception as e:
            logger.warning(f"KStars GPS API access error: {e}")
        await asyncio.sleep(5)

async def gps_main(gps_queue, console_queue, log_queue):
    MultiprocLogging.configurer(log_queue)
    logger.info("GPS main started – using ONLY KStars API")
    try:
        await read_kstars_location_file(gps_queue)
    except Exception as e:
        logger.error(f"Error in GPS monitor: {e}")
        await asyncio.sleep(5)

def gps_monitor(gps_queue, console_queue, log_queue):
    asyncio.run(gps_main(gps_queue, console_queue, log_queue))
