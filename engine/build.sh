#!/bin/sh
set -eu
mkdir -p build/standalone-engine
cc=${CC_PE:-x86_64-w64-mingw32-gcc}
"$cc" -std=c11 -Wall -Wextra -Wno-unused-parameter -shared -Iengine/include -Iengine \
    engine/piper.c engine/com.c -o build/standalone-engine/opensapi-piper.dll \
    -lole32 -ladvapi32 -lws2_32 -luuid -lsapi -Wl,--no-insert-timestamp
"$cc" -std=c11 -Wall -Wextra -municode examples/sapi-probe.c \
    -o build/standalone-engine/sapi-probe.exe -lole32 -loleaut32 -lsapi -luuid
"$cc" -std=c11 -Wall -Wextra -Wno-unused-parameter -municode -Iengine/include \
    tests/engine-probe.c -o build/standalone-engine/engine-probe.exe -lole32 -lsapi -luuid
