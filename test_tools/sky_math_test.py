#!/usr/bin/env python3
"""Sky Position Panel without a Mount Bridge: the Control Center's own altitude/azimuth maths
must agree with libnova (the Mount Bridge driver's maths), and the fallback data must have the
same shape as the driver's. Run: python3 -I test_tools/sky_math_test.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gui_installer"))
import indi_client as ic  # noqa: E402

# (RA h, Dec deg, lat, lon east, unix time) -> (altitude, azimuth from north) from libnova's
# ln_get_hrz_from_equ(), azimuth shifted by 180 deg (libnova counts from the south).
LIBNOVA = {
    (5.5, 20.0, 49.405, 8.64, 1795600000.0): (-10.8749, 319.4121),
    (17.64, 24.9, 49.405, 8.64, 1795600000.0): (47.5189, 108.4352),
    (0.0, 89.0, 49.405, 8.64, 1795600000.0): (48.6311, 0.9657),
    (12.0, -30.0, -33.9, 151.2, 1795609000.0): (-15.8539, 144.7909),
    (18.6, 24.46, 49.4847, 8.3828, 1795609000.0): (59.6656, 137.5491),
}


def P(state, **el):
    return {"state": state, "elements": {k: str(v) for k, v in el.items()}}


def main():
    for (ra, dec, lat, lon, t), (ea, ez) in LIBNOVA.items():
        a, z = ic.equatorial_to_horizontal(ra, dec, lat, lon, t)
        dz = min(abs(z - ez), 360 - abs(z - ez))
        assert abs(a - ea) < 0.02 and dz < 0.02, ((ra, dec), (a, z), (ea, ez))

    dev = {
        "GEOGRAPHIC_COORD": P("Ok", LAT=49.4847, LONG=8.3828, ELEV=0),
        "EQUATORIAL_EOD_COORD": P("Ok", RA=18.6, DEC=24.46),
        "TARGET_EOD_COORD": P("Ok", RA=0, DEC=0),
    }
    ic.get_properties = lambda **kw: {"PiFinder LX200": dev}
    r = ic.sky_panel_without_bridge(_now=lambda: 1795609000.0)
    assert r["location_known"] and r["mount"] is None and r["mount_configured"] is False and r["held"] is None
    assert abs(r["pifinder"]["alt"] - 59.6656) < 0.02 and r["goto"] is None  # target 0/0 = none
    dev["TARGET_EOD_COORD"] = P("Ok", RA=12.0, DEC=-30.0)
    r = ic.sky_panel_without_bridge(_now=lambda: 1795609000.0)
    assert r["goto"]["below"] is True
    dev["EQUATORIAL_EOD_COORD"] = P("Ok", RA=0, DEC=0)
    assert ic.sky_panel_without_bridge()["pifinder"] is None  # no position yet
    dev["GEOGRAPHIC_COORD"] = P("Ok", LAT=0, LONG=0)
    r = ic.sky_panel_without_bridge()
    assert r["location_known"] is False and r["pifinder"] is None and r["goto"] is None  # unknown location: nothing plotted
    ic.get_properties = lambda **kw: {}
    assert ic.sky_panel_without_bridge() is None

    def gp(**kw):
        if kw.get("device") == "PiFinder Mount Bridge":
            return {}
        return {"PiFinder LX200": {"GEOGRAPHIC_COORD": P("Ok", LAT=49.4, LONG=8.6), "EQUATORIAL_EOD_COORD": P("Ok", RA=5.0, DEC=30.0)}}
    ic.get_properties = gp
    d = ic.mount_bridge_drift()
    assert d["running"] is False and d["sky"]["location_known"] and d["sky"]["pifinder"]
    print("sky math and no-bridge fallback tests passed")


if __name__ == "__main__":
    main()
