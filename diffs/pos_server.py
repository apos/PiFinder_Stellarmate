#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
This module is runs a lightweight
server to accept socket connections
and report telescope position
Protocol based on Meade LX200

This is used by SkySafari (iOS, iPadOS)
"""

import socket
from math import modf
import logging
import re
from multiprocessing import Queue
from typing import Tuple, Union
from PiFinder.calc_utils import ra_to_deg, dec_to_deg, sf_utils
from PiFinder.composite_object import CompositeObject, MagnitudeObject
from PiFinder.multiproclogging import MultiprocLogging
from skyfield.positionlib import position_of_radec
import sys
import time

logger = logging.getLogger("PosServer")

sr_result = None
sequence = 0
ui_queue: Queue

# shortcut for skyfield timescale
ts = sf_utils.ts

def get_local_time(shared_state, _):
    dt = shared_state.datetime()
    if not dt:
        return "00:00:00"
    return dt.strftime("%H:%M:%S")

def get_local_date(shared_state, _):
    dt = shared_state.datetime()
    if not dt:
        return "01/01/01"
    return dt.strftime("%m/%d/%y")

def get_utc_offset(shared_state, _):
    dt = shared_state.datetime()
    if not dt or not dt.tzinfo:
        return "+00"
    offset_hours = int(dt.utcoffset().total_seconds() / 3600)
    return f"{offset_hours:+03}"

def get_longitude(shared_state, _):
    loc = shared_state.location()
    if not loc:
        return "+000*00"
    deg = abs(loc.longitude.degrees)
    sign = "+" if loc.longitude.degrees >= 0 else "-"
    d, m = divmod(deg * 60, 60)
    return f"{sign}{int(d):03}*{int(m):02}"

def get_latitude(shared_state, _):
    loc = shared_state.location()
    if not loc:
        return "+00*00"
    deg = abs(loc.latitude.degrees)
    sign = "+" if loc.latitude.degrees >= 0 else "-"
    d, m = divmod(deg * 60, 60)
    return f"{sign}{int(d):02}*{int(m):02}"

def parse_cm_command(shared_state, input_str: str):
    global sr_result
    if sr_result is None:
        logger.warning("parse_cm_command: No RA/DEC set before :CM#")
        return "0"

    ra = ra_to_deg(*sr_result)
    dec = dec_to_deg(*sr_result)
    logger.debug("parse_cm_command: Synchronizing to RA: %s, DEC: %s", ra, dec)

    # Aktualisiere die interne Teleskopposition
    shared_state.set_solution({"RA": ra, "Dec": dec})
    shared_state.set_datetime(datetime.utcnow())

    # Rückgabe einer Bestätigung
    return " M31 EX GAL MAG 3.5 SZ178.0'#"

def get_telescope_ra(shared_state, _):
    """
    Extract RA from current solution
    format for LX200 protocol
    RA = HH:MM:SS
    """
    solution = shared_state.solution()
    dt = shared_state.datetime()
    if not solution or not dt:
        return "+00*00'01"

    # Convert from J2000 to now epoch
    RA_deg = solution["RA"]
    Dec_deg = solution["Dec"]
    _p = position_of_radec(ra_hours=RA_deg / 15.0, dec_degrees=Dec_deg, epoch=ts.J2000)

    RA_h, _Dec, _dist = _p.radec(epoch=ts.from_datetime(dt))

    hh, mm, ss = RA_h.hms()
    ra_result = f"{hh:02.0f}:{mm:02.0f}:{ss:02.0f}"
    logger.debug("get_telescope_ra: RA result: %s", ra_result)
    return ra_result


def get_telescope_dec(shared_state, _):
    """
    Extract DEC from current solution
    format for LX200 protocol
    DEC = +/- DD*MM'SS
    """
    solution = shared_state.solution()
    dt = shared_state.datetime()
    if not solution or not dt:
        return "+00*00'01"

    # Convert from J2000 to now epoch
    RA_deg = solution["RA"]
    Dec_deg = solution["Dec"]
    _p = position_of_radec(ra_hours=RA_deg / 15.0, dec_degrees=Dec_deg, epoch=ts.J2000)

    _RA_h, Dec, _dist = _p.radec(epoch=ts.from_datetime(dt))

    dec = Dec.degrees
    if dec < 0:
        dec = abs(dec)
        sign = "-"
    else:
        sign = "+"

    mm, hh = modf(dec)
    fractional_mm, mm = modf(mm * 60.0)
    ss = round(fractional_mm * 60.0)

    dec_result = f"{sign}{hh:02.0f}*{mm:02.0f}'{ss:02.0f}"
    logger.debug("get_telescope_dec: Dec result: %s", dec_result)
    return dec_result


def respond_none(shared_state, input_str):
    return None


def respond_zero(shared_state, input_str):
    return "0"


def respond_one(shared_state, input_str):
    return "1"


def not_implemented(shared_state, input_str):
    # return "not implemented"
    return respond_none(shared_state, input_str)


def _match_to_hms(pattern: str, input_str: str) -> Union[Tuple[int, int, int], None]:
    match = re.match(pattern, input_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        return hours, minutes, seconds
    else:
        return None


def parse_sr_command(_, input_str: str):
    global sr_result
    pattern = r":Sr([-+]?\d{2}):(\d{2}):(\d{2})#"
    match = _match_to_hms(pattern, input_str)
    logger.debug("Parsing sr command, match: %s", match)
    if match:
        sr_result = match
        return "1"
    else:
        return "0"


def parse_sd_command(shared_state, input_str: str):
    global sr_result
    pattern = r":Sd([-+]?\d{2})\*(\d{2}):(\d{2})#"
    match = _match_to_hms(pattern, input_str)
    logger.debug("Parsing sd command, match: %s, sr_result: %s", match, sr_result)
    if match and sr_result:
        return handle_goto_command(shared_state, sr_result, match)
    else:
        return "0"


def handle_goto_command(shared_state, ra_parsed, dec_parsed):
    global sequence, ui_queue
    ra = ra_to_deg(*ra_parsed)
    dec = dec_to_deg(*dec_parsed)
    logger.debug("handle_goto_command: ra,dec in deg, JNOW: %s, %s", ra, dec)
    _p = position_of_radec(ra_hours=ra / 15, dec_degrees=dec, epoch=ts.now())
    ra_h, dec_d, _ = _p.radec(epoch=ts.J2000)
    sequence += 1
    comp_ra = float(ra_h._degrees)
    comp_dec = float(dec_d.degrees)
    logger.debug("Goto ra,dec in deg, J2000: %s, %s", comp_ra, comp_dec)
    constellation = sf_utils.radec_to_constellation(comp_ra, comp_dec)
    obj = CompositeObject.from_dict(
        {
            "id": -1,
            "object_id": sys.maxsize - sequence,
            "obj_type": "",
            "ra": comp_ra,
            "dec": comp_dec,
            "const": constellation,
            "size": "",
            "mag": MagnitudeObject([]),
            "catalog_code": "PUSH",
            "sequence": sequence,
            "description": f"Skysafari object nr {sequence}",
        }
    )
    logger.debug("handle_goto_command: Pushing object: %s", obj)
    shared_state.ui_state().add_recent(obj)
    shared_state.ui_state().set_new_pushto(True)
    ui_queue.put("push_object")
    return "1"


# Function to extract command
def extract_command(s):
    match = re.search(r":([A-Za-z]+)", s)
    return match.group(1) if match else None


lx_command_dict = {
    "GD": get_telescope_dec,
    "GR": get_telescope_ra,
    "RS": respond_none,
    "MS": respond_zero,
    "Sd": parse_sd_command,
    "Sr": parse_sr_command,
    "CM": parse_cm_command,
    "Q": respond_none,
    "GL": get_local_time,
    "GC": get_local_date,
    "GG": get_utc_offset,
    "Gg": get_longitude,
    "Gt": get_latitude,
}


def setup_server_socket():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("", 4030))
    server_socket.listen(1)
    return server_socket


def handle_client(client_socket, shared_state):
    client_socket.settimeout(60)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    while True:
        try:
            in_data = client_socket.recv(1024).decode()
            if not in_data:
                break

            logging.debug("Received from skysafari: %s", in_data)
            command = extract_command(in_data)
            if command:
                command_handler = lx_command_dict.get(command, not_implemented)
                out_data = command_handler(shared_state, in_data)
                if out_data:
                    response = out_data if out_data in ("0", "1") else out_data + "#"
                    client_socket.send(response.encode())
        except socket.timeout:
            logging.warning("Connection timed out.")
            break
        except ConnectionResetError:
            logging.warning("Client disconnected unexpectedly.")
            break

    client_socket.close()


def run_server(shared_state, p_ui_queue, log_queue):
    MultiprocLogging.configurer(log_queue)
    global ui_queue
    ui_queue = p_ui_queue
    logger = logging.getLogger(__name__)

    while True:
        try:
            with setup_server_socket() as server_socket:
                logger.info("SkySafari server started and listening")
                while True:
                    client_socket, address = server_socket.accept()
                    logger.debug("New connection from %s", address)
                    handle_client(client_socket, shared_state)
        except Exception:
            logger.exception("Unexpected server error")
            logger.info("Attempting to restart server in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Server shutting down...")
            break
