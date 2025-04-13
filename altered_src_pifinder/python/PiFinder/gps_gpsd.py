#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module is for GPS related functions (KStars-only mode)
"""

import asyncio
from PiFinder.multiproclogging import MultiprocLogging
import logging
import os
from datetime import datetime

logger = logging.getLogger("GPS")

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

error_2d = 999
error_3d = 999
error_in_m = 999


async def read_kstars_location_file(gps_queue):
    logger.info("KStars reader started (gps_gpsd.py)")
    last_line = ""
    while True:
        try:
            if os.path.exists(KSTARS_LOCATION_FILE):
                with open(KSTARS_LOCATION_FILE, "r") as f:
                    line = f.readline().strip()
                    if not line or line == last_line or line.startswith("ERROR"):
                        await asyncio.sleep(5)
                        continue

                    parts = line.split(",")
                    if len(parts) >= 6:
                        lat = float(parts[2])
                        lon = float(parts[3])
                        alt = float(parts[4])
                        time_utc = parts[5]

                        msg = (
                            "fix",
                            {
                                "lat": lat,
                                "lon": lon,
                                "altitude": alt,
                                "source": "KStars",
                                "lock": True,
                                "error_in_m": 10,
                            },
                        )

                        parsed_time = datetime.fromisoformat(time_utc)
                        time_msg = ("time", {"time": parsed_time})

                        gps_queue.put(msg)
                        gps_queue.put(time_msg)

                        logger.info(f"KStars GPS fix injected: {msg}")
                        last_line = line
        except Exception as e:
            logger.warning(f"KStars GPS reader error: {e}")
        await asyncio.sleep(5)


async def gps_main(gps_queue, console_queue, log_queue):
    MultiprocLogging.configurer(log_queue)
    logger.info("GPS main started – using ONLY KStars")

    try:
        await read_kstars_location_file(gps_queue)
    except Exception as e:
        logger.error(f"Error in GPS monitor: {e}")
        await asyncio.sleep(5)


# To run the GPS monitor
def gps_monitor(gps_queue, console_queue, log_queue):
    asyncio.run(gps_main(gps_queue, console_queue, log_queue))