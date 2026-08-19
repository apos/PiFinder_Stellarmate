/*
    PiFinder Mount Bridge

    Generic, mount-agnostic coupling between PiFinder's plate-solved position
    and whichever real INDI mount driver is active. Never speaks a
    mount-specific wire protocol - only the standard EQUATORIAL_EOD_COORD /
    ON_COORD_SET properties every INDI telescope driver already exposes, via
    an internal INDI client (same pattern as the stock indi_skysafari
    driver).

    See basic-memory pifinder-stellarmate/00009_indi-mount-bridge-concept for
    the design rationale (the "coupling degree" dial below).
*/

#pragma once

#include "defaultdevice.h"

#include <cmath>
#include <memory>
#include <string>
#include <utility>
#include <vector>

class PiFinderBridgeClient;

class PiFinderMountBridge : public INDI::DefaultDevice
{
    public:
        PiFinderMountBridge();

        virtual void ISGetProperties(const char *dev) override;
        virtual bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;
        virtual bool ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n) override;
        virtual bool ISNewNumber(const char *dev, const char *name, double values[], char *names[], int n) override;

    protected:
        virtual bool initProperties() override;
        virtual bool updateProperties() override;
        virtual bool Connect() override;
        virtual bool Disconnect() override;
        virtual const char *getDefaultName() override;
        virtual void TimerHit() override;
        virtual bool saveConfigItems(FILE *fp) override;

    private:
        void applyMode();
        double angularSeparationArcmin(double ra1, double dec1, double ra2, double dec2) const;

        // Pushes the active mount's TELESCOPE_MOUNT_TYPE (Alt/Az vs EQ) to
        // PiFinder's own Mount Type setting via HTTP, independent of
        // BridgeModeSP - this should stay in sync regardless of which
        // coupling mode (or Off) is selected. No-op if unchanged since the
        // last successful push, or if the mount hasn't reported it yet.
        void syncMountTypeToPiFinder();
        std::string m_lastSyncedMountType;

        // Tells PiFinder to stay awake (see PiFinder's /api/keep_awake) -
        // called every tick from handleGotoForward() itself, so it's
        // automatically scoped to exactly when Goto-Forward is active, never
        // running (and never needlessly draining PiFinder's battery) in any
        // other coupling mode. See #227 follow-up (2026-08-19).
        void keepPiFinderAwake();

        std::unique_ptr<PiFinderBridgeClient> m_client;

        // ISGetProperties() fires once per client connection (every
        // indi_getprop call, every INDI Control Panel refresh) - guard so
        // loadConfig() only actually replays the saved config once, or a
        // later client re-querying properties would silently revert
        // whatever mode the user just chose back to the last-saved one.
        bool m_configLoaded = false;

        // Same idea, for the properties that only exist once connected
        // (BRIDGE_MODE, CORRECTION_ACTION, DRIFT_THRESHOLD,
        // SOLVE_FRESHNESS) - ISGetProperties() runs before the device is
        // connected, so its loadConfig() call above has nothing to apply
        // BRIDGE_MODE's saved value to yet (the property doesn't exist as a
        // target). Found live (2026-08-05): Coupling mode never survived a
        // reconnect/profile restart, always came back up as whatever
        // in-memory default the switch was initialized with, regardless of
        // what was actually saved on disk.
        bool m_connectedConfigLoaded = false;

        // Last-applied ACTIVE_DEVICES values, used by ISNewText() to detect
        // a genuine change worth reconnecting for. Deliberately NOT read
        // from ActiveDeviceT[...].text before IUUpdateText() runs - that
        // crashed (2026-08-05) when ISNewText() fires from loadConfig()'s
        // config replay inside ISGetProperties(). Populated from the
        // same defaults as ActiveDeviceT in initProperties(), then kept in
        // sync after every applied update.
        std::string m_lastActivePiFinder;
        std::string m_lastActiveMount;

        // Settings: how to reach the local indiserver
        ITextVectorProperty SettingsTP;
        IText SettingsT[2] {};
        enum { INDISERVER_HOST, INDISERVER_PORT };

        // Which devices to bridge
        ITextVectorProperty ActiveDeviceTP;
        IText ActiveDeviceT[2] {};
        enum { ACTIVE_PIFINDER, ACTIVE_MOUNT };

        // Shadow Sync (#181): a purely additive, optional mirror of
        // PiFinder's verified solved position onto a second, independent
        // device (typically "PiFinder Simulator", #164/#176) via Sync -
        // for visualization/testing only. Deliberately decoupled from
        // ACTIVE_DEVICES/BridgeModeSP/CorrectionActionSP entirely: found
        // live (2026-08-07) that with the real mount as ACTIVE_MOUNT,
        // nothing ever targets the Simulator device, so it silently sits
        // at its RA=0/DEC=0 init default indefinitely. This must never be
        // able to influence the real mount or Coupling correction logic -
        // it only ever reads PiFinder's position and Syncs a second
        // device, nothing else.
        //
        // Kept the manual switch (2026-08-08, User decision after
        // weighing removing it): rather than removing the toggle to avoid
        // "forgot to re-enable it", auto-arm it instead - see
        // autoArmShadowSyncIfDevicePresent(), called whenever the shadow
        // device is (re)detected, so it's on by default whenever the
        // Simulator exists without the user needing to remember, while
        // still leaving a real, discoverable way to turn it off if
        // explicitly wanted (not just an obscure blank-the-name trick).
        // Also gated by isShadowDeviceSafe() regardless of the switch -
        // MUST never fire if the shadow name happens to equal the real
        // ACTIVE_MOUNT/ACTIVE_PIFINDER (typo, profile mixup, future
        // reconfiguration).
        ITextVectorProperty ShadowDeviceTP;
        IText ShadowDeviceT[1] {};
        enum { SHADOW_DEVICE };

        ISwitchVectorProperty ShadowSyncSP;
        ISwitch ShadowSyncS[2];
        enum { SHADOW_SYNC_ENABLE, SHADOW_SYNC_DISABLE };

        bool isShadowDeviceSafe() const;
        bool m_shadowAutoArmed = false; // guards auto-arm to once per device (re)appearance, not every tick
        void autoArmShadowSyncIfDevicePresent();

        // #159: guards the "binding never resolved" ERROR log to once per
        // give-up, not every tick thereafter - reset whenever isReady()
        // comes true again (a later disconnect/reconnect deserves a fresh
        // warning if it happens again). See PiFinderBridgeClient::
        // retryMissingPropertiesIfNeeded()/bindingGaveUp().
        bool m_bindingGiveUpLogged = false;

        // #227 follow-up (2026-08-19, user-requested): whatever position the
        // mount reports right after Connect() (its own idea of "where it is"
        // from before this session, or a hardware default) is exactly as
        // untrustworthy as the pre-Goto case syncMountToPiFinderPosition()
        // already fixes - found live: right after a driver reconnect, drift
        // was already >120' (over MaxSyncDriftNP), which would otherwise
        // just sit unfixed in HOLDING forever, same deadlock as before but
        // at connect-time instead of Goto-time. Reset to false in Connect();
        // TimerHit() performs exactly one unconditional Sync from PiFinder's
        // position as soon as isReady() and a fresh solve are both true, for
        // BridgeModeS that are allowed to actively command the mount
        // (Auto-correct, Goto-Forward) - never for Verify-Alert/Off, which
        // must never move/Sync the mount at all.
        bool m_didInitialSync = false;

        // Mode-Readiness-Check (2026-08-08, User request): runs whenever a
        // Coupling mode other than Off is (re-)selected. Verifies known
        // easy-to-forget preconditions instead of silently assuming them -
        // reports what it can't fix itself, auto-corrects what it safely
        // can (currently: MaxSyncDriftNP being smaller than
        // DriftThresholdNP, which would silently block every correction
        // in that gap forever). Deliberately does NOT touch
        // TELESCOPE_TRACK_STATE or anything else the user might have
        // intentionally configured - see 00090's Regel 2 in basic-memory.
        void runModeReadinessCheck();

        void handleShadowSync();

        // Coupling degree - see 00009 for the rationale of each stage.
        ISwitchVectorProperty BridgeModeSP;
        ISwitch BridgeModeS[4];
        enum { MODE_OFF, MODE_VERIFY_ALERT, MODE_AUTO_CORRECT, MODE_GOTO_FORWARD };

        // AUTO_CORRECT sends Sync or Goto/Track - separate from the above so
        // the one-shot manual actions below can also pick either.
        ISwitchVectorProperty CorrectionActionSP;
        ISwitch CorrectionActionS[2];
        enum { ACTION_SYNC, ACTION_GOTO };

        // Manual, immediate one-shot trigger (works regardless of BridgeModeSP)
        ISwitchVectorProperty ManualTriggerSP;
        ISwitch ManualTriggerS[2];
        enum { TRIGGER_SYNC_NOW, TRIGGER_GOTO_NOW };

        // Emergency stop - sends TELESCOPE_ABORT_MOTION to the active mount
        // immediately, independent of Coupling mode or any in-progress
        // settle-retry cycle. Separate property from ManualTriggerSP
        // (rather than a third option there) so it's never gated behind
        // the same handler path as Sync/Goto - a panic button should stay
        // as simple and direct as possible. See #179 (found live
        // 2026-08-07: Mount Bridge had no way at all to stop the mount if
        // a settle-retry cycle went wrong, e.g. #177's missing
        // dead-reckoning made it sync onto a stale position and re-slew
        // repeatedly).
        ISwitchVectorProperty AbortMountSP;
        ISwitch AbortMountS[1];

        // #191 - automatic multi-point alignment, see
        // docs/concepts/mount_bridge_multistar_alignment.md. §4.3's core
        // sequence and §5's Sync-only ADR (already confirmed sufficient for
        // OnStep - repeated Syncs build a real multi-point model there) are
        // implemented. §4.2's candidate selection is real: points come from
        // PiFinder's own /api/nearby_bright_stars (its "Str" bright-named-
        // star catalog, altitude-filtered server-side using PiFinder's own
        // GPS location/time via skyfield) - not a fixed hardcoded set.
        // Still out of scope: §4.3's median-of-N-solves (one fresh solve
        // per point, same as everywhere else in this file), §4.5's KStars-
        // model feed (explicitly flagged there as separate/research-first).
        //
        // Slew-path/cable-wrap risk between two altitude-safe points is a
        // known gap (#218) but deliberately out of scope, not an oversight:
        // a real mount normally already protects itself (OnStep's own Slew
        // elevation Limit, most GEM/Alt-Az controllers' own axis/meridian-
        // flip limits) - the below-horizon-mid-slew symptom seen live was
        // specific to the Telescope Simulator, which has none of that.
        // Modeling per-mount slew-path geometry here would duplicate the
        // mount's own firmware and cuts against this file's generic-
        // protocol-only philosophy (see the concept doc's own ADR).
        ISwitchVectorProperty MultiPointAlignSP;
        ISwitch MultiPointAlignS[2];
        enum { ALIGN_START, ALIGN_STOP };

        // §3's configuration parameters - only the three that gate
        // candidate selection (§4.2). Median-solve-count and the KStars-
        // feed checkbox aren't implemented yet, so aren't exposed here.
        INumberVectorProperty AlignConfigNP;
        INumber AlignConfigN[3];
        enum { ALIGN_RADIUS, ALIGN_COUNT, ALIGN_MIN_ALTITUDE };

        // Preferred-direction hard filter (direct feedback, 2026-08-10,
        // found live under real sky: "vom Zenith aus wandert der PiFinder
        // sonst gerne mal in eine Region, die z.B. nicht geeignet ist" - a
        // real obstruction in one azimuth quadrant, not modeled by
        // min_altitude alone). ANY (default) keeps the previous,
        // direction-agnostic behavior. A HARD filter, not a preference -
        // matches PiFinder's own /api/nearby_bright_stars contract: too few
        // candidates in the chosen quadrant is a failure
        // (fetchAlignmentCandidates() below), not a silent fallback to
        // other directions.
        ISwitchVectorProperty AlignDirectionSP;
        ISwitch AlignDirectionS[5];
        enum { ALIGN_DIR_ANY, ALIGN_DIR_N, ALIGN_DIR_E, ALIGN_DIR_S, ALIGN_DIR_W };

        // Poll-friendly progress readout for the Control Center GUI - a
        // one-shot getProperties can't observe LOGF_INFO/LOGF_WARN messages
        // (those are ephemeral <message> elements, not a queryable
        // property), so a client that only polls properties (no persistent
        // listening connection) would otherwise see no per-point progress
        // at all, just the coarse MULTI_POINT_ALIGN Idle/Busy/Ok/Alert
        // state. POINT_INDEX is 1-based (0 = no sequence has run yet this
        // session), frozen at its last value once the sequence stops/
        // completes/errors - not reset on Stop, so "stopped at 2/4" stays
        // readable until the next Start.
        INumberVectorProperty AlignProgressNP;
        INumber AlignProgressN[3];
        enum { ALIGN_POINT_INDEX, ALIGN_POINT_COUNT, ALIGN_POINT_SYNCED };

        enum class AlignState { IDLE, SLEWING, SETTLING, DONE };
        AlignState m_alignState = AlignState::IDLE;
        // RA (hours) / Dec (degrees) - populated fresh by
        // fetchAlignmentCandidates() every time Start is clicked, not
        // hardcoded. Empty until a sequence has actually been started.
        std::vector<std::pair<double, double>> m_alignPoints;
        size_t m_alignPointIndex = 0;
        // How many of m_alignPoints actually got a verified Sync (not just
        // attempted/skipped) - drives both AlignProgressN[ALIGN_POINT_SYNCED]
        // and advanceAlignPoint()'s final IPS_OK vs IPS_ALERT choice: a
        // sequence that skipped every single point (e.g. no fresh PiFinder
        // solve ever arrived) previously still reported IPS_OK ("sequence
        // complete"), indistinguishable from a real success - found during
        // #217's GUI-facing follow-up, where that ambiguity would otherwise
        // show up as a false "green" result.
        size_t m_alignSyncedCount = 0;
        int m_alignSettleTicksRemaining = 0;
        int m_alignFreshnessWaitTicksRemaining = 0;

        // Calls PiFinder's own /api/nearby_bright_stars (no ra/dec params -
        // it centers on PiFinder's own current solved position itself, per
        // §4.2's own decision) with AlignConfigN's radius/count/
        // min_altitude, and populates m_alignPoints from the response.
        // Returns false (having already logged why) on any request/parse
        // failure or a zero-candidate response - callers must not start a
        // sequence with stale/empty m_alignPoints left over from a
        // previous attempt.
        bool fetchAlignmentCandidates();

        void handleMultiPointAlignment();
        void startMultiPointAlignment();
        void stopMultiPointAlignment(const char *reason);
        bool gotoAlignPoint(size_t index);
        void advanceAlignPoint();

        INumberVectorProperty DriftThresholdNP;
        INumber DriftThresholdN[1];

        // Sanity cap on the SYNC step of every automatic correction (Auto-
        // correct's plain Sync path, and the Sync+re-Goto refine pattern
        // SETTLING/HOLDING/CorrectState::SETTLING all share). Separate from
        // DriftThresholdNP, which only decides *whether* to correct at all -
        // this decides whether an automatic Sync is even plausible as a
        // small model refinement versus almost certainly a bad/outlier
        // solve. Found live (2026-08-08): a several-degree drift reading
        // (way beyond anything a real alignment-model residual would be)
        // still passed the ordinary freshness gate (#79) and got Synced to
        // the mount unconditionally, risking corrupting its model with a
        // spurious solve instead of refining it - same failure class #79
        // guards against for staleness, just for implausible magnitude
        // instead. Deliberately NOT applied to ManualTriggerSP - those are
        // one-shot, user-initiated actions where the user already has eyes
        // on the situation before clicking.
        INumberVectorProperty MaxSyncDriftNP;
        INumber MaxSyncDriftN[1];

        // Graduated slew rate for correction Gotos (2026-08-08, regraded
        // 2026-08-19): sending every correction at whatever rate happens to
        // be currently selected on the mount (found live: "Half-Max") risks
        // overshoot - real handsets have long used slower "Guide/Center"
        // rates specifically for fine centering, only using fast rates for
        // big slews (see basic-memory pifinder-stellarmate for the
        // KStars/Ekos Align research this mirrors). Picks by INDEX POSITION
        // in whatever TELESCOPE_SLEW_RATE list the mount reports (same
        // mount-agnostic philosophy as getMountType() - never assumes a
        // specific driver's item names/count).
        //
        // Originally a fixed 3-bucket (slow/medium/fast) scheme - found live
        // (2026-08-19, first real Goto-Forward test against a correctly-
        // detected Alt/Az OnStep mount, see #227) that 3 buckets waste most
        // of a mount's actual rate ladder (OnStep exposes 10 steps) and,
        // combined with the old "no pre-Goto Sync" bug below, contributed to
        // large, uncorrected residuals. Now interpolates LOGARITHMICALLY
        // across the mount's *entire* available rate count between these two
        // endpoints - drift can plausibly range from sub-arcminute (fine
        // HOLDING correction) to several hundred degrees (an unaligned
        // mount's very first Goto), and a log scale gives sensible
        // resolution across that whole range instead of only at the low end.
        static constexpr double SLEW_RATE_LOG_MIN_ARCMIN = 0.5;
        static constexpr double SLEW_RATE_LOG_MAX_ARCMIN = 21600.0; // 360 deg
        void applySlewRateForDrift(double driftArcmin);

        // Root-cause fix for #227's real-sky Goto-Forward failure
        // (2026-08-19): every path that forwards a *new* target Goto to the
        // mount used to send it unconditionally, trusting whatever internal
        // model the mount already had - fine for an already-aligned mount,
        // but the very first real Goto against a freshly-correctly-detected
        // Alt/Az OnStep mount (no prior alignment reference at all) landed
        // many degrees off, and MaxSyncDriftNP's outlier-solve heuristic
        // then refused to correct it, since a residual that large looked
        // indistinguishable from a bad solve. Fix: ALWAYS Sync the mount to
        // PiFinder's current (not target) position immediately before
        // computing/sending a new Goto - this corrects the mount's model
        // from ground truth right before it computes the slew vector, so
        // the arrival residual reflects the mount's real pointing accuracy
        // instead of compounding an unknown, possibly huge, pre-existing
        // model error. Returns false (and forwards nothing) if PiFinder has
        // no fresh solve to sync from yet - never skip the sync silently.
        bool syncMountToPiFinderPosition();

        // Auto-correct only fires off a position PiFinder itself reports as
        // a real, recent camera solve (via /api/status - see #79/#107 in
        // basic-memory pifinder-stellarmate: LX200 has no room to carry this,
        // so it's fetched separately over HTTP). This is the max age of that
        // solve for a correction to still be considered trustworthy.
        INumberVectorProperty SolveFreshnessMaxAgeNP;
        INumber SolveFreshnessMaxAgeN[1];

        // Read-only: last computed drift between PiFinder and the mount, for
        // the VERIFY_ALERT mode and general visibility.
        INumberVectorProperty DriftStatusNP;
        INumber DriftStatusN[1];

        // MODE_GOTO_FORWARD state machine: forwards a *new* push-to target
        // to the mount immediately (event-driven, unlike the drift-polling
        // modes above), then waits for the mount to finish slewing and for
        // PiFinder to produce a fresh plate-solve of the arrival position
        // before auto-correcting any residual error. See 00009/00012 in
        // basic-memory pifinder-stellarmate for the design rationale.
        //
        // HOLDING (added for #171's follow-up): after a successful (or
        // exhausted) SETTLING, don't just go quiet - the whole point of a
        // push-to is that the mount then *holds* that target, same as any
        // other coupling mode. HOLDING watches for either a new push-to
        // target (same as IDLE) or the held target drifting past Threshold
        // (same Sync+re-Goto correction as SETTLING, just re-triggered on
        // an ongoing basis instead of only right after arrival) - found
        // live (2026-08-07): without this, normal mount tracking drift went
        // completely uncorrected once Goto-Forward settled once.
        enum class ForwardState { IDLE, SLEWING, SETTLING, HOLDING };
        ForwardState m_forwardState = ForwardState::IDLE;
        double m_lastForwardedRA = std::nan("");
        double m_lastForwardedDec = std::nan("");

        // A genuinely new target event (consumePiFinderTargetPending()) was
        // seen, but syncMountToPiFinderPosition() couldn't run yet (no fresh
        // PiFinder solve at that exact tick) - remember the intent and keep
        // retrying the sync every tick, using whatever target is *currently*
        // selected (getPiFinderTargetRADE() is non-consuming), instead of
        // silently dropping the user's target selection because one tick
        // was unlucky. Cleared once the sync succeeds and the Goto fires.
        bool m_forwardAwaitingSync = false;
        int m_settleTicksRemaining = 0;
        static constexpr int SETTLE_TICKS = 3; // poll cycles to wait before even checking for a fresh solve

        // SETTLE_TICKS alone doesn't guarantee PiFinder has actually produced
        // a new camera solve by then - it may still be reporting an
        // IMU-interpolated position left over from before/during the slew.
        // Trusting that as arrival truth would Sync the mount to a guessed
        // position instead of a verified one, corrupting its model instead
        // of correcting it. Found live (2026-08-07): this caused PiFinder's
        // own reported position to overshoot the target and the mount to
        // never converge across retries - same failure class #79 already
        // guards against for Auto-Correct, just missing here. Bounded so a
        // stuck/slow solver can't stall a settle attempt forever.
        int m_freshnessWaitTicksRemaining = 0;
        static constexpr int MAX_FRESHNESS_WAIT_TICKS = 10;

        // A residual after arrival usually means the mount's own model was
        // slightly off at this sky position - Sync corrects that model with
        // PiFinder's solve, then re-issuing the Goto (now benefiting from
        // the corrected model) should land closer. Bounded so a genuinely
        // noisy solve can't loop forever chasing it.
        int m_settleRetriesRemaining = 0;
        static constexpr int MAX_SETTLE_RETRIES = 3;

        void handleGotoForward();

        // MODE_AUTO_CORRECT with CorrectionActionS[ACTION_GOTO]: mirrors
        // handleGotoForward()'s arrival-verify-and-refine pattern (#170 -
        // blindly re-issuing a Goto to wherever PiFinder currently reports,
        // every single tick drift exceeds threshold, never corrects the
        // mount's own alignment-model error, so each Goto lands off by
        // roughly that same fixed error and drift climbs straight back up
        // right after - never actually converges on the target). Kept as a
        // separate state machine rather than reusing ForwardState/
        // handleGotoForward(): that one is driven by a discrete *new*
        // PiFinder push-to target event; this one is driven by continuous
        // drift-exceeds-threshold and needs to hand control back to normal
        // per-tick monitoring once a correction settles, not wait for a
        // "new target" event that may never come.
        enum class CorrectState { IDLE, SLEWING, SETTLING };
        CorrectState m_correctState = CorrectState::IDLE;
        double m_correctTargetRA = std::nan("");
        double m_correctTargetDec = std::nan("");
        int m_correctSettleTicksRemaining = 0;
        int m_correctFreshnessWaitTicksRemaining = 0;
        int m_correctSettleRetriesRemaining = 0;

        void handleAutoCorrectGoto(bool exceeded, double piRA, double piDec, double drift, double threshold);

        // Reposition Detection (#178, 2026-08-08) - see
        // docs/concepts/mount_bridge_reposition_detection.md for the full
        // design (decision matrix, sequence diagrams, ADR). Runs as a
        // shared pre-check in TimerHit(), before handleGotoForward()/
        // handleAutoCorrectGoto() - classifies every PiFinder-vs-mount
        // disagreement instead of blindly treating all of them as
        // "ordinary drift to correct":
        //   - Mount busy/moved, but NEITHER of our own state machines just
        //     commanded it (SLEWING) -> an external client did (hand-paddle
        //     over its own direct TCP/WiFi link to the mount controller,
        //     SkySafari, the OnStep app, KStars-GoTo-on-the-mount - all
        //     indistinguishable from each other and not distinguished on
        //     purpose, see the concept doc's Architecture section). Wait
        //     for it to finish + a fresh PiFinder solve, then adopt the new
        //     position as the held target - no Sync/Goto needed, the
        //     mount's own model is already correct since real motor motion
        //     was involved.
        //   - No command signal at all, but PiFinder-vs-mount disagree by
        //     more than the sky's own physical speed limit could produce
        //     since the last confirmed-good position -> the mount's
        //     internal model itself is stale (classic case: clutch open,
        //     OTA moved by hand without the motor/encoders registering it -
        //     live-verified 2026-08-08, see basic-memory 00093). Genuinely
        //     ambiguous whether this was deliberate (User: normal practice
        //     on friction-clutch mounts, incl. occasionally this EQ-6) or
        //     accidental - ask via ShadowSync-style low-friction
        //     confirmation rather than guessing either way.
        // Returns true if this tick was fully handled here (external slew
        // in progress or just adopted, or a Fall-4 confirmation is pending/
        // just resolved) - callers must skip their own normal handling for
        // this tick in that case, so the old per-mode Sync+re-Goto logic
        // never fires on the same drift a pending confirmation is already
        // watching.
        bool handleRepositionDetection(bool havePositions, double piRA, double piDec, double mountRA,
                                        double mountDec, double drift);

        // True while we're watching a mount slew we did NOT ourselves just
        // command (i.e. neither ForwardState::SLEWING nor
        // CorrectState::SLEWING) - sudden onset is what proves "someone
        // else is driving this mount right now" (see 3.1/3.2 in the concept
        // doc: the INDI driver reflects the mount controller's real state
        // regardless of which external client caused it, so Mount Bridge
        // never needs to know *which* one - only that it wasn't itself).
        bool m_externalSlewInProgress = false;

        // Fall-2 onset detection (2026-08-08 revision) - compares the
        // mount's own EQUATORIAL_EOD_COORD tick-to-tick instead of watching
        // for an IPS_BUSY state. Found live: a real, small/fast external
        // Sync+Goto (~20', the exact "hand-paddle nudge" scenario #178 is
        // meant to support) never produced an observable Busy state at all -
        // verified via a raw INDI wire capture on port 7624, state stayed
        // "Idle" throughout. isMountSlewing() is reliable for OUR OWN larger
        // Goto-Forward/Auto-correct moves elsewhere in this file (unchanged,
        // still fine there) but cannot be trusted as the *detection* signal
        // for Fall 2, at any poll rate - the edge it would need to be caught
        // on may simply never exist on the wire. A tick-to-tick position
        // delta needs no such edge - any real movement shows up, however
        // fast. Distinguished from passive drift (no tracking - see
        // MAX_SIDEREAL_DRIFT_ARCMIN_PER_SEC's own comment: deliberate
        // routine practice on this friction-clutch mount) using the exact
        // same physical plausibility bound Fall 3/4 already uses, applied
        // here to the mount's own movement rather than the PiFinder-vs-
        // mount difference.
        double m_lastPolledMountRA = std::nan("");
        double m_lastPolledMountDec = std::nan("");
        long m_lastPolledMountTime = 0;

        // Once a genuine external move is detected, give the mount a few
        // ticks to physically finish settling before trusting its position -
        // same reasoning/constant as SETTLE_TICKS for our own moves, since
        // isMountSlewing() can't reliably tell us "still moving" here either.
        int m_externalSettleTicksRemaining = 0;

        // Timestamp of the last position Mount Bridge is confident is
        // correct (either a just-adopted reposition, or the last
        // successful HOLDING/SETTLING correction) - the reference point the
        // physical drift-rate classification measures elapsed time from.
        // Deliberately time_t via std::time(), matching isPiFinderSolveFresh()'s
        // own existing timestamp convention elsewhere in this file.
        long m_lastConfirmedGoodTime = 0;
        static constexpr double MAX_SIDEREAL_DRIFT_ARCMIN_PER_SEC = 0.35; // measured live 2026-08-08 (~0.25-0.3'/s), generous margin

        // Found live (2026-08-08): right after a restart/mode-switch,
        // m_lastConfirmedGoodTime gets baselined on the very first tick
        // regardless of how much drift already exists (e.g. accumulated
        // during the restart itself, or left over from before) - the very
        // NEXT tick then judges that pre-existing drift against only ~1
        // poll interval of elapsed time, almost always exceeding the
        // physical plausibility bound and misfiring Fall 4 before the
        // existing, proven HOLDING/Auto-correct mechanism ever got a
        // chance to just fix it normally. Fix: the rate-based Fall-3/4
        // judgment only activates once a genuine confirmed-good moment
        // (drift already within Threshold) has actually been observed
        // since the last reset - until then, defer entirely to the
        // existing correction logic (still backstopped by MaxSyncDriftNP).
        bool m_repositionBaselineTrusted = false;

        // Fall 4 (clutch/disturbance) pending-confirmation state - a
        // ShadowSync-style low-friction Yes/No, not a full manual-Sync
        // workflow. Times out to an automatic "No" (revert) rather than
        // sitting on a stale position indefinitely if nobody answers.
        bool m_repositionConfirmPending = false;
        long m_repositionConfirmDeadline = 0;
        static constexpr int REPOSITION_CONFIRM_TIMEOUT_SEC = 45;
        ISwitchVectorProperty RepositionConfirmSP;
        ISwitch RepositionConfirmS[2];
        enum { REPOSITION_CONFIRM_YES, REPOSITION_CONFIRM_NO };

        // Read-only "who does the currently held target come from" badge
        // (#178 GUI unification, 2026-08-08): with Reposition Detection
        // active, MODE_GOTO_FORWARD alone already reacts symmetrically to
        // both a PiFinder push-to (Fall 1) and an external mount-side
        // command (Fall 2) - the separate "Follow mount's goto" preset
        // (MODE_AUTO_CORRECT+ACTION_GOTO) is now redundant for this use
        // case. The GUI replaces both with a single "GoTo" button (always
        // sets MODE_GOTO_FORWARD) and shows this badge instead of making
        // the user pre-select a source. Set whenever a target is adopted -
        // Fall 1 -> PIFINDER, Fall 2/Fall-4-confirmed-yes -> MOUNT (the
        // mount's own position was what got trusted); ordinary Fall-3
        // corrections and Fall-4 reverts don't change the source, they're
        // just re-affirming the existing held target.
        ISwitchVectorProperty TargetSourceSP;
        ISwitch TargetSourceS[2];
        enum { TARGET_SOURCE_PIFINDER, TARGET_SOURCE_MOUNT };
        void setTargetSource(int index);

        // Read-only, GUI-visible warning distinct from DriftStatusNP - see
        // the initProperties() comment. Empty message + IPS_OK/IDLE while
        // clear, driver's own refusal text + IPS_ALERT while active.
        ITextVectorProperty MountRejectTP;
        IText MountRejectT[1];
        void setMountRejectWarning(bool active, const std::string &message);

        // PiFinder's own IMU-dead-reckoning-relevant settings (Settings ->
        // Mount Type, Settings -> Advanced -> PiFinder Type/screen_direction)
        // - read-only status, distinct from syncMountTypeToPiFinder() below
        // which *pushes* Mount Type one-way. This just *shows* both current
        // values plus whether Mount Type actually matches the INDI mount's
        // own TELESCOPE_MOUNT_TYPE right now - IPS_ALERT on a mismatch (the
        // auto-sync failing, e.g. PiFinder unreachable), IPS_OK once they
        // agree. PiFinder Type has no INDI-side equivalent to compare
        // against at all (pure physical-mounting fact, see
        // docs/concepts/simulation_fidelity_and_pifinder_orientation.md §6) -
        // shown for the user to judge against their actual rig, never itself
        // marked right/wrong, but bundled into the same property/state as
        // Mount Type per direct feedback (2026-08-09): a Mount Type mismatch
        // should flag the whole "orientation config" badge, not just half of
        // it.
        ITextVectorProperty PiFinderOrientationTP;
        IText PiFinderOrientationT[2];
        enum { ORIENTATION_MOUNT_TYPE, ORIENTATION_SCREEN_DIRECTION };
        void syncOrientationStatus();
        std::string m_lastOrientationStatusKey;
};
