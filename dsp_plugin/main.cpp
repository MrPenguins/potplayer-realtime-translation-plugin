// winsock2.h must be included BEFORE windows.h to prevent
// windows.h from pulling in the old winsock.h (they conflict)
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include "dsp.h"

#pragma comment(lib, "ws2_32.lib")

// Global socket variables
SOCKET udpSocket = INVALID_SOCKET;
struct sockaddr_in serverAddr;
bool winsockInitialized = false;

// Initialize Winsock and setup UDP socket
void InitNetwork() {
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) == 0) {
        winsockInitialized = true;
        udpSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (udpSocket != INVALID_SOCKET) {
            serverAddr.sin_family = AF_INET;
            serverAddr.sin_port = htons(12345); // Target Python server port
            inet_pton(AF_INET, "127.0.0.1", &serverAddr.sin_addr);
        }
    }
}

void CloseNetwork() {
    if (udpSocket != INVALID_SOCKET) {
        closesocket(udpSocket);
        udpSocket = INVALID_SOCKET;
    }
    if (winsockInitialized) {
        WSACleanup();
        winsockInitialized = false;
    }
}

// Struct for audio packet header (must be declared before use)
#pragma pack(push, 1)
struct AudioHeader {
    int32_t srate;
    int32_t nch;
    int32_t bps;
};
#pragma pack(pop)

// Send a control frame to signal playback state changes (pause/stop/seek).
// The Python server recognizes nch=-1 as a "reset" signal and clears all buffers.
void SendControlFrame() {
    if (udpSocket != INVALID_SOCKET) {
        AudioHeader ctrl_header;
        ctrl_header.srate = 0;
        ctrl_header.nch = -1;      // -1 = control: reset
        ctrl_header.bps = 0;
        sendto(udpSocket, (char*)&ctrl_header, sizeof(AudioHeader), 0,
               (struct sockaddr*)&serverAddr, sizeof(serverAddr));
    }
}

// Module functions
void config(struct winampDSPModule *this_mod) {
    MessageBox(this_mod->hwndParent, "PotPlayer Real-time Translation DSP Plugin\nSends audio via UDP to 127.0.0.1:12345", "Config", MB_OK);
}

int init(struct winampDSPModule *this_mod) {
    InitNetwork();
    // Signal the Python server to reset its buffers on playback start
    SendControlFrame();
    return 0; // return 0 on success
}

void quit(struct winampDSPModule *this_mod) {
    // Signal reset before closing (playback stopped / player closing)
    SendControlFrame();
    CloseNetwork();
}

int modify_samples(struct winampDSPModule *this_mod, short int *samples, int numsamples, int bps, int nch, int srate) {
    if (udpSocket != INVALID_SOCKET && numsamples > 0) {
        // Send a packet: Header + PCM Data
        int bytes_per_sample = bps / 8;
        int data_size = numsamples * nch * bytes_per_sample;
        
        // Ensure we don't exceed typical UDP MTU sizes (e.g. 64KB)
        // Usually PotPlayer sends chunks of 576 or 1152 samples.
        int total_size = sizeof(AudioHeader) + data_size;
        
        // We will just allocate a temporary buffer and send
        // In a highly optimized plugin, we'd pre-allocate or manage chunks
        char* buffer = (char*)malloc(total_size);
        if (buffer) {
            AudioHeader* header = (AudioHeader*)buffer;
            header->srate = srate;
            header->nch = nch;
            header->bps = bps;
            
            memcpy(buffer + sizeof(AudioHeader), samples, data_size);
            
            sendto(udpSocket, buffer, total_size, 0, (struct sockaddr*)&serverAddr, sizeof(serverAddr));
            
            free(buffer);
        }
    }
    
    // Return numsamples to let audio play normally
    return numsamples;
}

// Define the module
winampDSPModule module = {
    "PotPlayer Whisper Interceptor",
    NULL,
    NULL,
    config,
    init,
    modify_samples,
    quit,
    NULL
};

// Retrieve the module
winampDSPModule* getModule(int which) {
    if (which == 0) return &module;
    return NULL;
}

// Define the header
winampDSPHeader header = {
    DSP_HDRVER,
    "Whisper Interceptor Plugin",
    getModule
};

// Exported function that Winamp/PotPlayer looks for
extern "C" __declspec(dllexport) winampDSPHeader* winampDSPGetHeader2() {
    return &header;
}

// DllMain
BOOL APIENTRY DllMain(HMODULE hModule, DWORD  ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH:
    case DLL_THREAD_ATTACH:
    case DLL_THREAD_DETACH:
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}
