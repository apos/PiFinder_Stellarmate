#!/bin/bash
# Datei: start_xvnc_session1.sh

# Funktion: Beende alle zugehörigen Prozesse
if [[ "$1" == "--killall" ]]; then
    echo "Beende alle Prozesse der parallelen VNC/Xvfb-Session :1..."

    pkill -f "xterm.*:1"
    pkill -f "websockify.*6081"
    pkill -f "x11vnc.*:1"
    pkill -f "openbox.*:1"
    pkill -f "Xvfb :1"

    # Beende nur echten KStars, ignoriere Wrapper
    pgrep -af "/usr/bin/kstars" | awk '{print $1}' | xargs -r kill -9

    echo "Alle relevanten Prozesse wurden beendet."
    exit 0
fi

# Starte Xvfb auf Display :1, falls nicht bereits läuft
if ! pgrep -f "Xvfb :1" > /dev/null; then
    echo "Starte Xvfb :1 ..."
    Xvfb :1 -screen 0 1900x1100x16 &
    sleep 2
else
    echo "Xvfb :1 läuft bereits."
fi

## Starte Fenstermanager, falls nicht bereits läuft
#if ! pgrep -f "openbox.*:1" > /dev/null; then
#    echo "Starte openbox ..."
#    DISPLAY=:1 openbox &
#    sleep 1
#else
#    echo "openbox auf :1 läuft bereits."
#fi

# Starte LXDE Desktop Session (lxsession), falls nicht bereits läuft
if ! pgrep -f "lxsession.*:1" > /dev/null; then
    echo "Starte LXDE ..."
    DISPLAY=:1 lxsession -s LXDE-pi -e LXDE &
    sleep 2
else
    echo "LXDE (lxsession) auf :1 läuft bereits."
fi

# Starte x11vnc für :1, falls nicht bereits läuft
if ! pgrep -f "x11vnc.*:1" > /dev/null; then
    echo "Starte x11vnc mit Logging ..."
    x11vnc -display :1 -rfbport 5901 -nopw -forever -logfile /tmp/x11vnc_display1.log &
    sleep 2
    echo "x11vnc-Logfile unter /tmp/x11vnc_display1.log"
else
    echo "x11vnc auf :1 läuft bereits."
fi

# Starte noVNC auf Port 6081, falls nicht bereits läuft
if ! pgrep -f "websockify.*6081" > /dev/null; then
    echo "Starte noVNC auf Port 6081 ..."
    /opt/noVNC/utils/novnc_proxy --vnc localhost:5901 --listen 6081 --web /opt/noVNC &
    sleep 2
else
    echo "noVNC auf Port 6081 läuft bereits."
fi

# Starte xterm nur einmal
if ! pgrep -f "xterm.*:1" > /dev/null; then
    echo "Starte xterm ..."
    DISPLAY=:1 xterm &
    sleep 1
else
    echo "xterm auf :1 läuft bereits."
fi

# Starte KStars nur, wenn es nicht läuft (aber ignoriere wrapper und defuncts)
if ! pgrep -f "/usr/bin/kstars" > /dev/null; then
    echo "Starte KStars ..."
    setsid env DISPLAY=:1 /usr/bin/kstars &
else
    echo "KStars läuft bereits (nur /usr/bin/kstars geprüft)."
fi
