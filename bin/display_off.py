#!/usr/bin/env python3
"""
Turn off the PiFinder OLED display (SSD1351, 128x128, SPI0).
Run as ExecStopPost in pifinder.service, or manually after stopping pifinder.
Uses only luma.oled from the venv — no PiFinder code needed.
"""
import sys
import time

try:
    from luma.core.interface.serial import spi
    from luma.oled.device import ssd1351
except ImportError:
    sys.exit(0)  # luma not installed — nothing to do

try:
    serial = spi(device=0, port=0, bus_speed_hz=16000000, gpio_DC=24, gpio_RST=25)
    device = ssd1351(serial, width=128, height=128)
    device.hide()
    time.sleep(0.1)
    device.cleanup()
except Exception:
    pass  # hardware not available or already off
