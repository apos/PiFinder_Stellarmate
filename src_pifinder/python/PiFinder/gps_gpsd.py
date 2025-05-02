#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module is for GPS related functions
"""

import asyncio
from PiFinder.multiproclogging import MultiprocLogging
from gpsdclient import GPSDClient
import logging

logger = logging.getLogger("GPS")

error_2d = 999
error_3d = 999
error_in_m = 999


def is_tpv_accurate(tpv_dict):
    """
    Check the accuracy of the GPS fix
    """
    global error_2d, error_3d, error_in_m
    # get the ecefpAcc if present, else get sep, else use 499
    # error = tpv_dict.get("ecefpAcc", tpv_dict.get("sep", 499))
    mode = tpv_dict.get("mode")
    logger.debug(
        "GPS: TPV: mode=%s, ecefpAcc=%s, sep=%s, error_2d=%s, error_3d=%s",
        mode,
        # error,
        tpv_dict.get("ecefpAcc", -1),
        tpv_dict.get("sep", -1),
        error_2d,
        error_3d,
    )
    if mode == 2 and error_2d < 1000:
        error_in_m = error_2d
        return True
    if mode == 3 and error_3d < 500:
        error_in_m = error_3d
        return True
    else:
        return False


async def aiter_wrapper(sync_iter):
    """Wrap a synchronous iterable into an asynchronous one."""
    for item in sync_iter:
        yield item
        await asyncio.sleep(0)  # Yield control to the event loop


async def process_sky_messages(client, gps_queue):
    sky_stream = client.dict_stream(filter=["SKY"])
    global error_2d, error_3d
    async for result in aiter_wrapper(sky_stream):
        logger.debug("GPS: SKY: %s", result)
        if result["class"] == "SKY":
            error_2d = result.get("hdop", 999)
            error_3d = result.get("pdop", 999)
        if result["class"] == "SKY" and "nSat" in result:
            sats_seen = result["nSat"]
            sats_used = result["uSat"]
            num_sats = (sats_seen, sats_used)
            msg = ("satellites", num_sats)
            logger.debug("Number of sats seen: %i", sats_seen)
            gps_queue.put(msg)
        await asyncio.sleep(0)  # Yield control to the event loop


async def process_reading_messages(client, gps_queue, console_queue, gps_locked):
    global error_in_m
    tpv_stream = client.dict_stream(convert_datetime=True, filter=["TPV"])
    async for result in aiter_wrapper(tpv_stream):
        if is_tpv_accurate(result):
            # if True:
            logger.debug("last reading is %s", result)
            if result.get("lat") and result.get("lon") and result.get("altHAE"):
                if not gps_locked:
                    gps_locked = True
                    console_queue.put("GPS: Locked")
                    logger.debug("GPS locked")
                msg = (
                    "fix",
                    {
                        "lat": result.get("lat"),
                        "lon": result.get("lon"),
                        "altitude": result.get("altHAE"),
                        "source": "GPS",
                        "lock": True,
                        "error_in_m": error_in_m,
                    },
                )
                logger.debug("GPS fix: %s", msg)
                gps_queue.put(msg)

            if result.get("time"):
                msg = ("time", result.get("time"))
                logger.debug("Setting time to %s", result.get("time"))
                gps_queue.put(msg)
        await asyncio.sleep(0)  # Yield control to the event loop


    asyncio.run(gps_main(gps_queue, console_queue, log_queue))

import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


import os
from datetime import datetime

KSTARS_LOCATION_FILE = "/tmp/kstars_location.txt"

logger = logging.getLogger("GPS")

import sys
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

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

def gps_monitor(gps_queue, console_queue, log_queue):
    asyncio.run(gps_main(gps_queue, console_queue, log_queue))
