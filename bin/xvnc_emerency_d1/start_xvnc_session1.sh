#!/bin/bash

export DISPLAY=:1

# Starte Xvfb
/usr/bin/Xvfb :1 -screen 0 1600x1200x16 &
sleep 2

echo "Warte auf /tmp/.X11-unix/X1..."
for i in {1..10}; do
  [ -S /tmp/.X11-unix/X1 ] && break
  sleep 1
done

if [ ! -S /tmp/.X11-unix/X1 ]; then
  echo "Xvfb Socket wurde nicht gefunden – Abbruch"
  exit 1
fi

# Starte LXDE Session
lxsession -s LXDE-pi -e LXDE &

# Starte x11vnc
/usr/bin/x11vnc -display :1 -rfbport 5900 -nopw -forever -logfile /tmp/x11vnc_display1.log

