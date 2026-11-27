/*
    PiFinder Mount Bridge - internal INDI client

    Connects to the local indiserver as a plain client (same pattern as the
    stock indi_skysafari driver's SkySafariClient) and watches two devices:
    the PiFinder position source and whichever real mount device is active.
    Never speaks any mount-specific protocol - only the generic
    EQUATORIAL_EOD_COORD / ON_COORD_SET properties every INDI telescope
    driver already exposes.
*/

#pragma once

#include "baseclient.h"
#include "basedevice.h"

#include <deque>
#include <mutex>
#include <string>
#include <atomic>

class PiFinderBridgeClient : public INDI::BaseClient
{
    public:
        PiFinderBridgeClient();

        void setDevices(const std::string &piFinderName, const std::string &mountName);

        // Cold-start property-binding race (#159): setDevices() + connectServer()
        // ask for the properties once; if indiserver or a watched driver had not
        // registered yet, the ones isReady() depends on may never arrive. Call
        // once per TimerHit() tick while !isReady(): no-ops during a short grace
        // period, then reconnects to indiserver (which asks again for everything)
        // on a bounded backoff, slowly afterwards. Returns true on ticks where a
        // logged retry was made. See bindingGaveUp() for the final-failure case.
        // Never use watchProperty() for this: see the comment in the function.
        bool retryMissingPropertiesIfNeeded();

        // True once BINDING_RETRY_MAX_ATTEMPTS has been exhausted without
        // isReady() ever becoming true - a genuinely absent/misconfigured
        // device (wrong name in Active devices, driver not actually
        // running), not just a slow cold-start race. Reset by setDevices()
        // (a fresh Connect() deserves a fresh attempt).
        bool bindingGaveUp() const { return m_bindingGaveUp; }

        // Third, fully independent device (#181) - purely mirrors
        // PiFinder's position via Sync for visualization/testing, never
        // participates in isReady()/getMountRADE()/sendMountCoords(). Safe
        // to call repeatedly (e.g. whenever the user retypes the device
        // name) - re-watching an already-watched device name is a no-op on
        // the libindi side. Pass an empty name to stop watching.
        void setShadowDevice(const std::string &shadowName);
        bool isShadowReady() const;
        bool syncShadowCoords(double ra, double dec);

        bool isReady() const;

        bool getPiFinderRADE(double &ra, double &dec) const;
        bool getMountRADE(double &ra, double &dec) const;

        // Observer location (degrees, latitude north, longitude east in
        // -180..180) as the INDI world knows it: the standard
        // GEOGRAPHIC_COORD property of the PiFinder device first, then of the
        // mount - KStars and the StellarMate app write it to every device they
        // drive, so it is the location the user actually set. An all-zero
        // value is INDI's "never set" default and counts as unknown. `source`
        // names where it came from (for the log). False: nothing usable.
        bool getObserverLocation(double &lat, double &lon, std::string &source) const;

        // The last Goto target the user sent (JNow, hours/degrees): either to the
        // mount (KStars slews the mount directly) or to the PiFinder device
        // (push-to, Goto Forward, a Dobsonian without mount) - whichever property
        // was updated more recently. RA 0 / Dec 0 is INDI's "never set" default
        // and counts as none. False: no target on either device.
        // `fromPiFinder` (optional): true when the PiFinder device's target is the newer one, false for the mount's;
        // `setTime` (optional): epoch seconds at which this Bridge saw that target property update (0 if unknown).
        bool getLastGotoTarget(double &ra, double &dec, bool *fromPiFinder = nullptr, long *setTime = nullptr) const;

        // The last push-to target requested via a Goto() on the PiFinder
        // device - distinct from getPiFinderRADE(), which is PiFinder's live
        // solved position and never changes just because a target was set.
        bool getPiFinderTargetRADE(double &ra, double &dec) const;

        // Edge-triggered companion to getPiFinderTargetRADE() above (added
        // for the Goto-Forward mode-switch safety fix, see
        // handleGotoForward()/ISNewSwitch() in pifinder_mount_bridge.cpp).
        // getPiFinderTargetRADE() only ever answers "what is PiFinder's
        // target *right now*" - it cannot tell "a fresh Goto request just
        // arrived" apart from "the same value has been sitting there since
        // before", which is exactly the ambiguity that made a value-only
        // comparison unsafe (turning Goto-Forward mode on could immediately
        // re-fire whatever target happened to already be there). This flag
        // is set in updateProperty() on every genuine TARGET_EOD_COORD
        // update from the PiFinder device - including a request for the
        // *same* RA/Dec as before, since libindi's own INDI::Telescope::
        // ISNewNumber() re-publishes that property on every incoming Goto
        // request regardless of whether the value changed (verified against
        // this project's own PiFinder LX200 driver, see lx200_pifinder.cpp's
        // Goto() comment) - so a fresh click always sets this, even for an
        // unchanged target, while a target that's merely still sitting there
        // from before never does. consumePiFinderTargetPending() reads and
        // clears it atomically so each real event is only ever acted on once.
        bool consumePiFinderTargetPending();

        // What somebody else did to the mount since the last call; the newest event wins.
        //   GOTO         - a GoTo this Bridge did not send (KStars, the StellarMate app, any INDI client): the mount driver
        //                  published new target coordinates (TARGET_EOD_COORD) away from where the mount is. A Sync does not
        //                  change that property; releasing a direction button does, but copies the current position into it.
        //   ABORT        - TELESCOPE_ABORT_MOTION was sent to the mount (by anybody, this Bridge included).
        //   HAND_MOTION  - a direction button (TELESCOPE_MOTION_NS / WE) was pressed.
        enum class MountEvent { NONE, GOTO, ABORT, HAND_MOTION };
        // `ra`/`dec` (JNow, hours/degrees) are set for GOTO only. Consumed on read.
        MountEvent consumeMountEvent(double &ra, double &dec);

        // Why the last new mount target was not taken as a GoTo (empty: nothing to tell; the echo of an own GoTo is not told).
        // Consumed on read - the driver logs it, so a GoTo that went unnoticed can be explained afterwards.
        std::string consumeIgnoredTargetNote();

        // Seconds since another client switched the mount to Sync (ON_COORD_SET), i.e. a jump of the mount's position that
        // follows is that client's Sync and no movement. A very large value if never seen.
        double secondsSinceForeignMountSync() const;

        // How many times another client has switched the mount to Sync since this process started.
        int foreignMountSyncs() const { return m_foreignSyncCount; }

        // True while the mount is actively slewing (EQUATORIAL_EOD_COORD busy).
        bool isMountSlewing() const;

        // The mount's own TELESCOPE_PARK state. False: the mount has no park
        // property (nothing known); otherwise `parked` says whether PARK is on.
        bool getMountParked(bool &parked) const;

        // coordSetName is one of the mount's ON_COORD_SET switch names, e.g. "SYNC", "TRACK", "SLEW"
        bool sendMountCoords(double ra, double dec, const char *coordSetName);

        // Sends a Goto to the PiFinder LX200 device itself, not the mount -
        // exactly what an external LX200 client (KStars, SkySafari, the
        // on-device menu) already does for a push-to, so PiFinder treats it
        // identically: a new PUSH-catalog entry, its own on-device
        // arrows/UI re-targeting to it. Needed because correcting the
        // mount alone (sendMountCoords()) leaves PiFinder's own belief
        // about "what am I pushed-to" untouched - see "Align to Held
        // Target"'s own header comment in pifinder_mount_bridge.cpp.
        bool sendPiFinderCoords(double ra, double dec, const char *coordSetName);

        // Seconds since the last successful sendMountCoords() call - the one
        // choke point every self-initiated correction (Auto-correct Sync/
        // Goto, Goto-Forward's HOLDING re-sync, Multi-Point Alignment, the
        // manual "Sync mount from PiFinder" trigger, ...) already funnels
        // through, so this needs no per-call-site bookkeeping. Published via
        // PiFinderMountBridge's own CORRECTION_AGE property (2026-09-01,
        // basic-memory pifinder-stellarmate/00105/#239's follow-up) so
        // indi_pifinder_simulator can tell "the mount is Busy because WE
        // just told it to move" apart from "the mount is Busy because
        // something external commanded it" - without this, a simulated
        // PiFinder that naively follows any mount Busy state ends up
        // chasing its own driver's corrections instead of detecting them.
        // A very large value (never set this run) until the first call.
        double secondsSinceLastMountCommand() const;

        // True (once) if, since the last sendMountCoords() call, the mount's
        // own EQUATORIAL_EOD_COORD reported IPS_ALERT - every INDI telescope
        // driver's native way of saying it refused or could not complete a
        // Goto/Sync (e.g. an elevation or cable-wrap/axis-limit rejection).
        // Consumed on read (clears itself once returned true) so callers
        // that poll on a timer don't get stuck re-handling the same event
        // forever - also cleared by the next sendMountCoords() call.
        // outMessage receives the driver's own log text if one was seen.
        // Thread-safe: the underlying INDI::BaseClient runs its own incoming-
        // traffic thread (per its own doc comment on connectServer()), so
        // updateProperty()/newMessage() - which set the state this reads -
        // fire on a different thread than the driver's TimerHit(), which
        // calls this. See m_mountRejectMutex.
        bool mountRejectedLastCoords(std::string &outMessage);

        // Reads the mount's own TELESCOPE_MOUNT_TYPE switch (every INDI::Telescope
        // has it: MOUNT_ALTAZ / MOUNT_EQ_FORK / MOUNT_EQ_GEM) and maps it to
        // PiFinder's own "Alt/Az" / "EQ" setting values. Returns false if the
        // mount hasn't reported this property yet (not connected, or a driver
        // that doesn't set it).
        bool getMountType(std::string &outType) const;

        // TELESCOPE_SLEW_RATE, by index position rather than item name -
        // same "mount-agnostic, no assumed item names" reasoning as
        // getMountType(). Returns 0 if the mount doesn't expose slew rates
        // at all (some simulators/drivers don't) - callers must treat that
        // as "not supported", not "index 0 selected".
        int getSlewRateCount() const;
        bool setSlewRateIndex(int index);

        // Emergency stop: sends TELESCOPE_ABORT_MOTION to the active mount
        // immediately. Deliberately does NOT gate on isReady() (which also
        // requires PiFinder's own properties) - the mount should be
        // stoppable even if PiFinder's side is broken/stale, arguably
        // exactly the situation this is most needed in. See #179.
        bool abortMount();

    protected:
        void newDevice(INDI::BaseDevice dp) override;
        void newProperty(INDI::Property property) override;
        void updateProperty(INDI::Property property) override;
        void removeProperty(INDI::Property property) override;
        void newMessage(INDI::BaseDevice baseDevice, int messageID) override;

    private:
        void forgetProperties();
        void watchAllDevices();
        void noteMountTarget(INDI::Property property);
        void noteMountEvent(MountEvent event, double ra = 0.0, double dec = 0.0);
        void noteIgnoredTarget(const char *why, double ra, double dec);
        bool justBound() const;
        std::string m_piFinderName;
        std::string m_mountName;
        bool m_piFinderOnline = false;
        bool m_mountOnline = false;

        INDI::PropertyViewNumber *m_piFinderEqNP = nullptr;
        INDI::PropertyViewNumber *m_piFinderTargetNP = nullptr;
        INDI::PropertyViewNumber *m_mountEqNP = nullptr;
        INDI::PropertyViewNumber *m_piFinderGeoNP = nullptr;
        INDI::PropertyViewNumber *m_mountGeoNP = nullptr;
        INDI::PropertyViewNumber *m_mountTargetNP = nullptr;
        std::atomic<long> m_lastMountTargetTime { 0 };
        std::atomic<long> m_lastPiFinderTargetTime { 0 };
        INDI::PropertyViewSwitch *m_mountOnCoordSetSP = nullptr;
        INDI::PropertyViewSwitch *m_mountParkSP = nullptr;
        INDI::PropertyViewSwitch *m_piFinderOnCoordSetSP = nullptr;
        INDI::PropertyViewSwitch *m_mountMountTypeSP = nullptr;
        INDI::PropertyViewSwitch *m_mountAbortSP = nullptr;
        INDI::PropertyViewSwitch *m_mountSlewRateSP = nullptr;

        // #159 cold-start property-binding retry - tick-counted (against
        // TimerHit()'s own ~2s period), same idiom as the driver's own
        // SETTLE_TICKS/MAX_FRESHNESS_WAIT_TICKS, not wall-clock timing.
        static constexpr int BINDING_RETRY_GRACE_TICKS = 2;    // ~4s: let the original subscription resolve on its own first
        static constexpr int BINDING_RETRY_INTERVAL_TICKS = 2; // ~4s between retry attempts
        static constexpr int BINDING_RETRY_MAX_ATTEMPTS = 3;   // "a handful", ~16s total budget incl. grace
        // After those, the subscription is asked for again every ~30 s for as long as the Bridge is not ready, instead of never again:
        // a mount whose driver connects late (OnStep after a profile switch) must still be bound without anybody restarting the Bridge.
        static constexpr int BINDING_RETRY_LONG_INTERVAL_TICKS = 15;
        // A PiFinder target update in the first seconds after (re)binding is the property being re-sent to us, not a push-to from a human.
        static constexpr long TARGET_EVENT_IGNORE_AFTER_BIND_SEC = 10;
        long m_bindTime = 0;
        int m_bindingRetryTicksElapsed = 0;
        int m_bindingRetryCooldownTicks = 0;
        int m_bindingRetryAttempts = 0;
        bool m_bindingGaveUp = false;

        // Written from updateProperty()/newMessage() (INDI::BaseClient's own
        // I/O thread), read/written from sendMountCoords()/
        // mountRejectedLastCoords() (the driver's TimerHit() thread) - needs
        // real synchronization, not just "worked in testing so far".
        mutable std::mutex m_mountRejectMutex;
        bool m_mountRejectedLastCoords = false;
        std::string m_mountRejectMessage;

        // 0 = never sent this run - secondsSinceLastMountCommand() reports a
        // large sentinel in that case, see its own comment.
        std::atomic<long> m_lastMountCommandTime { 0 };

        // The GoTos this Bridge sent itself: the mount driver publishes their coordinates as its target too, and that echo
        // must not count as somebody else's GoTo. An entry is used up by its echo or expires.
        struct OwnGoto
        {
            double ra, dec;
            long time;
        };
        static constexpr long OWN_GOTO_ECHO_SEC = 60;
        static constexpr double OWN_GOTO_ECHO_ARCMIN = 1.0;
        // A new target this close to the mount's position is not a GoTo (a direction button was released).
        static constexpr double TARGET_AT_MOUNT_ARCMIN = 0.5;
        // A switch to Sync within this time of our own command is our own.
        static constexpr double OWN_COMMAND_SWITCH_SEC = 5.0;
        std::mutex m_mountEventMutex;   // events are written by the client's I/O thread and read by TimerHit()
        std::deque<OwnGoto> m_ownGotos;
        MountEvent m_mountEvent = MountEvent::NONE;
        double m_mountEventRA = 0.0, m_mountEventDec = 0.0;
        std::string m_ignoredTargetNote;
        std::atomic<long> m_lastForeignSyncTime { 0 };
        std::atomic<int> m_foreignSyncCount { 0 };

        // Guards m_piFinderTargetPending - same cross-thread reasoning as
        // m_mountRejectMutex above (written from updateProperty()'s I/O
        // thread, read/cleared from the driver's TimerHit() thread). Own
        // mutex rather than reusing m_mountRejectMutex - unrelated state,
        // no reason to couple their locking.
        mutable std::mutex m_piFinderTargetMutex;
        bool m_piFinderTargetPending = false;

        std::string m_shadowName;
        bool m_shadowOnline = false;
        INDI::PropertyViewNumber *m_shadowEqNP = nullptr;
        INDI::PropertyViewSwitch *m_shadowOnCoordSetSP = nullptr;

        // Root-cause fix (2026-09-05, same incident/reasoning as
        // indi_pifinder_simulator's own isUsableCoordinate() - see that
        // file's header comment for the full incident writeup: a real
        // OnStep mount at Dec 90/NCP published a NaN EQUATORIAL_EOD_COORD
        // with no other explanation found live; indilib/indi#2167
        // documents an independent, still-unresolved OnStep crash under
        // the same "sync near NCP" condition). getPiFinderRADE()/
        // getMountRADE()/getPiFinderTargetRADE() below used to return
        // whatever the snooped INDI value currently held with NO
        // finiteness/range check - a NaN mount reading would have flowed
        // straight into pifinder_mount_bridge.cpp's drift calculation,
        // slew-rate selection and reposition-detection baseline, which
        // actually commands the REAL mount (a much bigger blast radius
        // than the Simulator's own display-only position). Every existing
        // caller already treats a `false` return (no data snooped yet, the
        // normal case right after startup) as "skip this tick, do nothing"
        // - a rejected bad reading now reuses that exact same, already
        // safe code path instead of a new one, so a bad reading can never
        // reach sendMountCoords()/the real mount. Rate-limited: a
        // persistently misbehaving mount driver logs the condition
        // periodically via stderr (this class has no LOGF_WARN - it is an
        // INDI::BaseClient, not an INDI::DefaultDevice - but indiserver
        // captures driver stderr the same way IDLog() output already is,
        // see basic-memory's INDI-debugging note on that), not once per
        // TimerHit() tick.
        static constexpr long BAD_COORD_WARN_INTERVAL_SEC = 45;
        mutable long m_lastBadCoordWarnTime = 0;
        bool isUsableCoordinateForWarn(const char *sourceLabel, double ra, double dec) const;
};
