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

#include <mutex>
#include <string>

class PiFinderBridgeClient : public INDI::BaseClient
{
    public:
        PiFinderBridgeClient();

        void setDevices(const std::string &piFinderName, const std::string &mountName);

        // Cold-start property-binding race (#159): watchDevice() in
        // setDevices() only ever sends the initial <getProperties> request
        // once - if indiserver or the watched driver itself hasn't finished
        // registering yet at that exact moment (common right after a full
        // Pi reboot, when every driver is starting up together), the
        // properties isReady() depends on may simply never arrive, with
        // nothing to notice or retry. Live-verified: a plain
        // Disconnect()/Connect() cycle does NOT recover this (it repeats
        // the same one-shot request), only a full process restart did.
        // Call once per TimerHit() tick while !isReady() - internally
        // no-ops until a short grace period has passed (give the original
        // subscription a first real chance), then re-requests whichever of
        // the three properties are still missing via watchProperty()
        // (which - unlike watchDevice() - actually resends
        // <getProperties> on every call), on a bounded backoff. Returns
        // true on ticks where a retry was actually (re-)issued, so the
        // driver can log it. See bindingGaveUp() for the final-failure case.
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

        // True while the mount is actively slewing (EQUATORIAL_EOD_COORD busy).
        bool isMountSlewing() const;

        // coordSetName is one of the mount's ON_COORD_SET switch names, e.g. "SYNC", "TRACK", "SLEW"
        bool sendMountCoords(double ra, double dec, const char *coordSetName);

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
        std::string m_piFinderName;
        std::string m_mountName;
        bool m_piFinderOnline = false;
        bool m_mountOnline = false;

        INDI::PropertyViewNumber *m_piFinderEqNP = nullptr;
        INDI::PropertyViewNumber *m_piFinderTargetNP = nullptr;
        INDI::PropertyViewNumber *m_mountEqNP = nullptr;
        INDI::PropertyViewSwitch *m_mountOnCoordSetSP = nullptr;
        INDI::PropertyViewSwitch *m_mountMountTypeSP = nullptr;
        INDI::PropertyViewSwitch *m_mountAbortSP = nullptr;
        INDI::PropertyViewSwitch *m_mountSlewRateSP = nullptr;

        // #159 cold-start property-binding retry - tick-counted (against
        // TimerHit()'s own ~2s period), same idiom as the driver's own
        // SETTLE_TICKS/MAX_FRESHNESS_WAIT_TICKS, not wall-clock timing.
        static constexpr int BINDING_RETRY_GRACE_TICKS = 2;    // ~4s: let the original subscription resolve on its own first
        static constexpr int BINDING_RETRY_INTERVAL_TICKS = 2; // ~4s between retry attempts
        static constexpr int BINDING_RETRY_MAX_ATTEMPTS = 3;   // "a handful", ~16s total budget incl. grace
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
        long m_lastMountCommandTime = 0;

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
