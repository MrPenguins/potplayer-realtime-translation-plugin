#ifndef WINAMP_DSP_H
#define WINAMP_DSP_H

#include <windows.h>

typedef struct winampDSPModule {
    char *description;       // description of the module
    HWND hwndParent;         // parent window (filled in by calling app)
    HINSTANCE hDllInstance;  // instance handle to this DLL (filled in by calling app)

    void (*Config)(struct winampDSPModule *this_mod);  // configuration dialog
    int (*Init)(struct winampDSPModule *this_mod);     // 0 on success, creates window, etc
    
    // modify waveform samples: returns number of samples to actually write
    // numsamples is the number of SAMPLES (not bytes)
    // bps is bits per sample (e.g. 16)
    // nch is number of channels (e.g. 2 for stereo)
    // srate is sample rate (e.g. 44100)
    int (*ModifySamples)(struct winampDSPModule *this_mod, short int *samples, int numsamples, int bps, int nch, int srate);
    
    void (*Quit)(struct winampDSPModule *this_mod);    // called when module is unloaded

    void *userData; // user data
} winampDSPModule;

typedef struct {
    int version;       // DSP_HDRVER
    char *description; // description of library
    winampDSPModule* (*getModule)(int); // module retrieval function
} winampDSPHeader;

#define DSP_HDRVER 0x20

#endif // WINAMP_DSP_H
