/*
    PiFinder Mount Bridge - read-only watcher of an OnStep controller

    A GoTo started on the OnStep hand controller, the OnStep app or SkySafari goes straight to the controller: INDI only
    ever shows that the mount moves, not where it was sent (#658). The controller itself knows, so this asks it over its
    network command channel. Only get commands are sent (:GU# :Gr# :Gd# :GR# :GD# :A?#) - nothing here moves, syncs or
    configures anything.

    A controller's network port serves one client at a time and the INDI OnStep driver occupies one, so another one of the
    command ports is used.
*/

#pragma once

#include <atomic>
#include <condition_variable>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

// One reading of the controller. Angles: RA in hours, Dec in degrees, both of date (as INDI's EQUATORIAL_EOD_COORD).
struct OnStepSample
{
    bool slewing = false;   // a GoTo is in progress (:GU# lacks 'N')
    bool parking = false;   // ... to the park or home position
    double targetRA = 0.0, targetDec = 0.0;
    double ra = 0.0, dec = 0.0;
};

// Tells a GoTo from everything else that changes the controller's target (a Sync, a target that is set and never used).
class OnStepGotoDetector
{
    public:
        // True: this sample shows a GoTo to (ra, dec) that has not been told yet.
        bool sample(const OnStepSample &s, double &ra, double &dec);
        void reset() { *this = OnStepGotoDetector(); }

    private:
        // A target that stays changed this many samples without a slew was a Sync (or never used).
        static constexpr int UNUSED_TARGET_SAMPLES = 4;
        // A slew to an unchanged target counts when it ends this close to it ("GoTo the same object again").
        static constexpr double ARRIVED_ARCMIN = 10.0;
        bool m_started = false, m_wasSlewing = false, m_told = false, m_parkingRun = false;
        double m_baseRA = 0.0, m_baseDec = 0.0;
        int m_idleWithNewTarget = 0;
};

class OnStepWatcher
{
    public:
        ~OnStepWatcher() { stop(); }

        // Watch the controller at `host`, trying `ports` in this order. Calling it again with the same values does nothing.
        void follow(const std::string &host, const std::vector<int> &ports);
        void stop();

        // The newest GoTo seen, once, as soon as it is at least `minAgeSec` old (so that whoever else reports the same GoTo
        // had the time to do so).
        bool takeGoto(double minAgeSec, double &ra, double &dec);
        // An alignment is running on the controller: star `star` of `stars`. False when none, or nothing is known.
        bool aligning(int &star, int &stars) const;
        // The controller's alignment as last read: the most stars it takes, the star it waits for and how many the alignment
        // has (star = stars + 1: finished; 0 0: none). `reading` counts the readings, so a caller can wait for a newer one.
        // False while not connected.
        bool progress(int &maxStars, int &star, int &stars, unsigned &reading) const;
        // The port in use, 0 while not connected.
        int port() const;
        bool following() const { return m_thread.joinable(); }
        std::string host() const { return m_host; }
        // True once a whole round over all ports found no controller that answers.
        bool unreachable() const;

    private:
        void run(std::string host, std::vector<int> ports);
        bool ask(int fd, const char *command, std::string &reply) const;
        bool read(int fd, OnStepSample &s, int &maxStars, int &star, int &stars) const;
        bool pause(double seconds); // false: stop was asked for

        static constexpr double POLL_SEC = 1.0;   // the controller drops a client that is silent for 10 s
        static constexpr double RETRY_SEC = 15.0;

        std::thread m_thread;
        std::string m_host;
        std::vector<int> m_ports;
        mutable std::mutex m_mutex;
        std::condition_variable m_wake;
        std::atomic<bool> m_stop { false };
        bool m_haveGoto = false, m_unreachable = false;
        double m_gotoRA = 0.0, m_gotoDec = 0.0, m_gotoTime = 0.0;
        int m_port = 0, m_star = 0, m_stars = 0, m_maxStars = 0;
        unsigned m_readings = 0;
};
