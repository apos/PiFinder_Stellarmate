#include "onstep_watcher.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>

#include <netdb.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <fcntl.h>
#include <unistd.h>

namespace
{
double monotonicSeconds()
{
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

double apartArcmin(double ra1, double dec1, double ra2, double dec2)
{
    const double toRad = M_PI / 180.0;
    double cosSep = std::sin(dec1 * toRad) * std::sin(dec2 * toRad) +
                    std::cos(dec1 * toRad) * std::cos(dec2 * toRad) * std::cos((ra1 - ra2) * 15.0 * toRad);
    cosSep = std::max(-1.0, std::min(1.0, cosSep));
    return std::acos(cosSep) / toRad * 60.0;
}

// "HH:MM:SS" or "HH:MM.T"
bool parseHours(const std::string &text, double &hours)
{
    int h = 0, m = 0, s = 0;
    double minutes = 0.0;
    if (std::sscanf(text.c_str(), "%d:%d:%d", &h, &m, &s) == 3)
        hours = h + m / 60.0 + s / 3600.0;
    else if (std::sscanf(text.c_str(), "%d:%lf", &h, &minutes) == 2)
        hours = h + minutes / 60.0;
    else
        return false;
    return hours >= 0.0 && hours < 24.0;
}

// "sDD*MM:SS" or "sDD*MM"; the sign is read from the text, "-00*30" is negative.
bool parseDegrees(const std::string &text, double &degrees)
{
    if (text.size() < 4 || (text[0] != '+' && text[0] != '-'))
        return false;
    int d = 0, m = 0, s = 0;
    char separator = 0;
    const int n = std::sscanf(text.c_str() + 1, "%d%c%d%*[:']%d", &d, &separator, &m, &s);
    if (n < 3)
        return false;
    degrees = (d + m / 60.0 + (n == 4 ? s : 0) / 3600.0) * (text[0] == '-' ? -1.0 : 1.0);
    return degrees >= -90.0 && degrees <= 90.0;
}

int connectTo(const std::string &host, int port)
{
    addrinfo hints = {}, *found = nullptr;
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &found) != 0)
        return -1;
    int fd = -1;
    for (addrinfo *a = found; a != nullptr && fd < 0; a = a->ai_next)
    {
        const int s = socket(a->ai_family, a->ai_socktype | SOCK_CLOEXEC, a->ai_protocol);
        if (s < 0)
            continue;
        const int flags = fcntl(s, F_GETFL, 0);
        fcntl(s, F_SETFL, flags | O_NONBLOCK);
        bool ok = connect(s, a->ai_addr, a->ai_addrlen) == 0;
        if (!ok)
        {
            pollfd p = { s, POLLOUT, 0 };
            int error = 0;
            socklen_t length = sizeof(error);
            ok = poll(&p, 1, 3000) == 1 && getsockopt(s, SOL_SOCKET, SO_ERROR, &error, &length) == 0 && error == 0;
        }
        if (ok)
            fd = s;
        else
            close(s);
    }
    freeaddrinfo(found);
    return fd;
}
}

bool OnStepGotoDetector::sample(const OnStepSample &s, double &ra, double &dec)
{
    if (!m_started)
    {
        // Whatever is there when the watching starts is no news, a slew that is already running included.
        m_started = true;
        m_wasSlewing = m_told = s.slewing;
        m_baseRA = s.targetRA;
        m_baseDec = s.targetDec;
        return false;
    }
    const bool newTarget = apartArcmin(s.targetRA, s.targetDec, m_baseRA, m_baseDec) > 0.5;
    bool tell = false;
    if (s.slewing)
    {
        if (!m_wasSlewing)
        {
            m_told = false;
            m_parkingRun = false;
        }
        m_parkingRun = m_parkingRun || s.parking;
        if (!m_told && !m_parkingRun && newTarget)
            tell = m_told = true;
        m_idleWithNewTarget = 0;
    }
    else if (m_wasSlewing)
    {
        if (!m_told && !m_parkingRun && apartArcmin(s.ra, s.dec, s.targetRA, s.targetDec) < ARRIVED_ARCMIN)
            tell = true;
        m_baseRA = s.targetRA;
        m_baseDec = s.targetDec;
        m_idleWithNewTarget = 0;
    }
    else if (newTarget && ++m_idleWithNewTarget >= UNUSED_TARGET_SAMPLES)
    {
        m_baseRA = s.targetRA;
        m_baseDec = s.targetDec;
        m_idleWithNewTarget = 0;
    }
    else if (!newTarget)
        m_idleWithNewTarget = 0;
    m_wasSlewing = s.slewing;
    if (tell)
    {
        ra = s.targetRA;
        dec = s.targetDec;
    }
    return tell;
}

void OnStepWatcher::follow(const std::string &host, const std::vector<int> &ports)
{
    if (m_thread.joinable() && host == m_host && ports == m_ports)
        return;
    stop();
    m_host = host;
    m_ports = ports;
    m_stop = false;
    m_thread = std::thread(&OnStepWatcher::run, this, host, ports);
}

void OnStepWatcher::stop()
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_stop = true;
    }
    m_wake.notify_all();
    if (m_thread.joinable())
        m_thread.join();
    std::lock_guard<std::mutex> lock(m_mutex);
    m_haveGoto = m_unreachable = false;
    m_port = m_star = m_stars = 0;
}

bool OnStepWatcher::takeGoto(double minAgeSec, double &ra, double &dec)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    if (!m_haveGoto || monotonicSeconds() - m_gotoTime < minAgeSec)
        return false;
    m_haveGoto = false;
    ra = m_gotoRA;
    dec = m_gotoDec;
    return true;
}

bool OnStepWatcher::aligning(int &star, int &stars) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    star = m_star;
    stars = m_stars;
    return m_star > 0 && m_stars > 0 && m_star <= m_stars;
}

int OnStepWatcher::port() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_port;
}

bool OnStepWatcher::unreachable() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_unreachable;
}

bool OnStepWatcher::pause(double seconds)
{
    std::unique_lock<std::mutex> lock(m_mutex);
    m_wake.wait_for(lock, std::chrono::duration<double>(seconds), [this] { return m_stop.load(); });
    return !m_stop;
}

bool OnStepWatcher::ask(int fd, const char *command, std::string &reply) const
{
    // Drop anything left over from an answer that came too late, it must not be read as the next one's.
    char buffer[64];
    while (recv(fd, buffer, sizeof(buffer), MSG_DONTWAIT) > 0)
    {
    }
    const size_t length = std::strlen(command);
    if (send(fd, command, length, MSG_NOSIGNAL) != static_cast<ssize_t>(length))
        return false;
    reply.clear();
    const double deadline = monotonicSeconds() + 2.0;
    while (!m_stop && monotonicSeconds() < deadline && reply.size() < 64)
    {
        pollfd p = { fd, POLLIN, 0 };
        if (poll(&p, 1, 200) <= 0)
            continue;
        const ssize_t n = recv(fd, buffer, sizeof(buffer), 0);
        if (n <= 0)
            return false;
        reply.append(buffer, static_cast<size_t>(n));
        const auto end = reply.find('#');
        if (end != std::string::npos)
        {
            reply.erase(end);
            return true;
        }
    }
    return false;
}

bool OnStepWatcher::read(int fd, OnStepSample &s, int &star, int &stars) const
{
    std::string status, targetRA, targetDec, ra, dec, align;
    // The status first: a GoTo that starts between two answers then shows its new target with the next sample at the latest.
    if (!ask(fd, ":GU#", status) || !ask(fd, ":Gr#", targetRA) || !ask(fd, ":Gd#", targetDec) || !ask(fd, ":GR#", ra) ||
        !ask(fd, ":GD#", dec) || !ask(fd, ":A?#", align))
        return false;
    // A status is a row of flags. Anything shorter is a stray answer (a lone "0" was seen on the real controller as the first
    // reply of a connection): read as a status it would look like a slew.
    if (status.size() < 3)
        return false;
    s.slewing = status.find('N') == std::string::npos;
    s.parking = status.find_first_of("Ih") != std::string::npos;
    if (!parseHours(targetRA, s.targetRA) || !parseDegrees(targetDec, s.targetDec) || !parseHours(ra, s.ra) ||
        !parseDegrees(dec, s.dec))
        return false;
    // :A?# is "mno": most stars possible, the current one, the last one; 0 0 when none is running.
    star = align.size() == 3 ? align[1] - '0' : 0;
    stars = align.size() == 3 ? align[2] - '0' : 0;
    return true;
}

void OnStepWatcher::run(std::string host, std::vector<int> ports)
{
    while (!m_stop)
    {
        bool answered = false;
        for (size_t i = 0; i < ports.size() && !m_stop && !answered; ++i)
        {
            const int fd = connectTo(host, ports[i]);
            if (fd < 0)
                continue;
            OnStepGotoDetector detector;
            OnStepSample s;
            int star = 0, stars = 0, failures = 0;
            // A port somebody else holds accepts the connection but never answers: the first reading decides.
            while (!m_stop && failures < 3)
            {
                if (!read(fd, s, star, stars))
                {
                    if (!answered)
                        break;
                    ++failures;
                    continue;
                }
                failures = 0;
                answered = true;
                double ra = 0.0, dec = 0.0;
                const bool isGoto = detector.sample(s, ra, dec);
                {
                    std::lock_guard<std::mutex> lock(m_mutex);
                    m_port = ports[i];
                    m_unreachable = false;
                    m_star = star;
                    m_stars = stars;
                    if (isGoto)
                    {
                        m_haveGoto = true;
                        m_gotoRA = ra;
                        m_gotoDec = dec;
                        m_gotoTime = monotonicSeconds();
                    }
                }
                if (!pause(POLL_SEC))
                    break;
            }
            close(fd);
            std::lock_guard<std::mutex> lock(m_mutex);
            m_port = m_star = m_stars = 0;
        }
        if (!answered)
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_unreachable = true;
        }
        if (!pause(RETRY_SEC))
            break;
    }
}
