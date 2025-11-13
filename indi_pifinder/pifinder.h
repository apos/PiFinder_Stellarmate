#pragma once

#include "indibase.h"
#include "defaultdevice.h"
#include "indicom.h"
#include "indiproperty.h"
#include "indipropertynumber.h"
#include "indipropertyswitch.h"

#include <libnova/nova.h>

#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <unistd.h>

class PiFinder : public INDI::DefaultDevice
{
public:
    PiFinder();
    ~PiFinder() = default;

    const char *getDefaultName() override;

    bool initProperties() override;
    bool updateProperties() override;

    bool ISNewSwitch(const char *dev, const char *name, ISState *states, char *names[], int n) override;
    bool ISNewText(const char *dev, const char *name, char *texts[], char *names[], int n) override;
    bool ISNewNumber(const char *dev, const char *name, double *values, char *names[], int n) override;
    bool ISNewBLOB(const char *dev, const char *name, int sizes[], int blobsizes[], char *blobs[], char *formats[], char *names[], int n) override;

    void ISGetProperties(const char *dev) override;

protected:
    bool Handshake();
    bool ReadScopeStatus();

private:
    int pifinder_fd {-1};
    bool SendCommand(const char *cmd, char *response, int max_len);
    void Close();

    // Declare INDI properties
    INDI::NumberVectorProperty EquatorialEODNP;
    INDI::NumberProperty EquatorialEODN[2];
    INDI::SwitchVectorProperty ConnectionSP;
    INDI::SwitchProperty ConnectionS[2];
    INDI::NumberVectorProperty HorizontalCoordinatesNP;
    INDI::NumberProperty HorizontalCoordinatesN[2];
};