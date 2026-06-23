cmake_minimum_required(VERSION 3.10)
project(PotPlayerWhisperDSP)

# PotPlayer is usually 64-bit on modern systems, but could be 32-bit. 
# Make sure to compile to match the PotPlayer installation (usually 64-bit).

# Create a shared library (.dll)
add_library(dsp_whisper SHARED main.cpp)

# Link against Winsock
target_link_libraries(dsp_whisper ws2_32)

# Set the output extension to .dll
set_target_properties(dsp_whisper PROPERTIES SUFFIX ".dll")
