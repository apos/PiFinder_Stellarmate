#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module is for GPS related functions
"""
import asyncio
import aiohttp
import os
import datetime
import logging
from PiFinder.multiproclogging import MultiprocLogging

logger = logging.getLogger("GPS.stellarmate")

async def get_kstars_location():
    """
    Fetches location from KStars API
    """
    url = "http://localhost:8624/api/info/location"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("success", {})
                    lat = float(result.get("latitude", 0))
                    lon = float(result.get("longitude", 0))
                    alt = result.get("altitude")
                    if alt is None or float(alt) == 0.0:
                        alt = 0.0
                    alt = float(alt)
                    return lat, lon, alt
    except Exception as e:
        logger.warning(f"KStars GPS API access error: {e}")
    return None, None, None

def gps_monitor(gps_queue, console_queue, log_queue):
    """
    Monitors KStars for location and puts it on the queue
    """
    MultiprocLogging.configurer(log_queue)
    logger.info("GPS KStars monitor started")

    loop = asyncio.get_event_loop()
    while True:
        lat, lon, alt = loop.run_until_complete(get_kstars_location())

        if lat is not None:
            fix = (
                "fix",
                {
                    "lat": lat,
                    "lon": lon,
                    "altitude": alt,
                    "source": "KStarsAPI",
                    "error_in_m": 10,
                    "lock": True,
                    "lock_type": 3,
                },
            )
            gps_queue.put(fix)

            tm = ("time", {"time": datetime.datetime.now()})
            gps_queue.put(tm)
            logger.info(f"KStars GPS API fix injected: {fix}")
        else:
            logger.warning("Could not get location from KStars")

        loop.run_until_complete(asyncio.sleep(5))