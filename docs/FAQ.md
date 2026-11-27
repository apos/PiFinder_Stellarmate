# FAQ

[Deutsch](FAQ_de.md) · [README](../README.md)

## Does PFSM keep running when the phone's screen is locked?

**Yes.** Everything that controls runs on the Pi: the Mount Bridge (an INDI driver) and the Control Center service, including the
pause during guiding and alignments and its self-repair. The web page only shows and sends your clicks.

- With the screen locked the browser freezes the page. When you unlock, it refreshes and takes the right to operate back (the
  Control Center gives it to one browser at a time and releases it after 15 seconds of silence).
- The page's regular refreshes send no commands.
- **One exception:** *One-Click Setup* (also started by a coupling button when the setup is not finished) runs step by step
  **in the browser**. If the screen locks meanwhile, it stops or breaks off: keep the screen on until it is done.

KStars/Ekos and the mount are not affected by the phone at all.
