/*
 * Wine Piper TTS engine, using a separately installed loopback HTTP service.
 *
 * Copyright 2026 OpenSAPI contributors
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Lesser General Public License for more details.
 */

#include <stdlib.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>

#define COBJMACROS
#include <winsock2.h>
#include <windows.h>

#include <objbase.h>
#include <initguid.h>
#include <winhttp.h>
#include <sapi.h>
#include <sperror.h>
#include <sapiddk.h>
#include "engine.h"


#define WARN(...) ((void)0)

#define MAX_WAV_SIZE (64 * 1024 * 1024)
#define MAX_TEXT_LENGTH (1024 * 1024)

struct piper_engine
{
    ISpTTSEngine ISpTTSEngine_iface;
    ISpObjectWithToken ISpObjectWithToken_iface;
    LONG ref;
    ISpObjectToken *token;
    DWORD rate, port;
    WCHAR voice[128];
    DWORD language, route;
};

static struct piper_engine *impl_from_engine(ISpTTSEngine *iface)
{
    return CONTAINING_RECORD(iface, struct piper_engine, ISpTTSEngine_iface);
}

static struct piper_engine *impl_from_token(ISpObjectWithToken *iface)
{
    return CONTAINING_RECORD(iface, struct piper_engine, ISpObjectWithToken_iface);
}

static HRESULT WINAPI engine_QueryInterface(ISpTTSEngine *iface, REFIID iid, void **out)
{
    struct piper_engine *engine = impl_from_engine(iface);

    if (!out) return E_POINTER;
    *out = NULL;
    if (IsEqualIID(iid, &IID_IUnknown) || IsEqualIID(iid, &IID_ISpTTSEngine))
        *out = iface;
    else if (IsEqualIID(iid, &IID_ISpObjectWithToken))
        *out = &engine->ISpObjectWithToken_iface;
    else return E_NOINTERFACE;
    ISpTTSEngine_AddRef(iface);
    return S_OK;
}

static ULONG WINAPI engine_AddRef(ISpTTSEngine *iface)
{
    return InterlockedIncrement(&impl_from_engine(iface)->ref);
}

static ULONG WINAPI engine_Release(ISpTTSEngine *iface)
{
    struct piper_engine *engine = impl_from_engine(iface);
    ULONG ref = InterlockedDecrement(&engine->ref);

    if (!ref)
    {
        if (engine->token) ISpObjectToken_Release(engine->token);
        free(engine);
        InterlockedDecrement(&opensapi_objects);
    }
    return ref;
}

/* Convert a length-delimited UTF-16 fragment into a JSON string. */
static char *make_request(const SPVTEXTFRAG *frag, LONG rate, struct piper_engine *engine)
{
    static const char hex[] = "0123456789abcdef";
    char *utf8, *json, *p;
    unsigned int scale;
    int len, i;

    if (frag->ulTextLen > MAX_TEXT_LENGTH ||
        !(len = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, frag->pTextStart,
                                   frag->ulTextLen, NULL, 0, NULL, NULL))) return NULL;
    if (!(utf8 = malloc(len))) return NULL;
    if (!(json = malloc((size_t)len * 6 + 512)))
    {
        free(utf8);
        return NULL;
    }
    WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, frag->pTextStart,
                        frag->ulTextLen, utf8, len, NULL, NULL);
    p = json;
    p += sprintf(p, "{\"text\":\"");
    for (i = 0; i < len; i++)
    {
        unsigned char c = utf8[i];
        if (c < 32)
        {
            memcpy(p, "\\u00", 4);
            p[4] = hex[c >> 4];
            p[5] = hex[c & 15];
            p += 6;
        }
        else
        {
            if (c == '"' || c == '\\') *p++ = '\\';
            *p++ = c;
        }
    }
    rate = max(-10, min(10, (LONGLONG)rate + frag->State.RateAdj));
    /* Approximate SAPI's rate range with Piper length_scale in [0.5, 2]. */
    scale = rate >= 0 ? 100000 / (10 + rate) : 1000 * (10 - rate);
    sprintf(p, "\",\"length_scale\":%u.%04u}", scale / 10000, scale % 10000);
    if (engine->voice[0])
    {
        char voice[128];
        WideCharToMultiByte(CP_UTF8,0,engine->voice,-1,voice,sizeof(voice),NULL,NULL);
        p = json + strlen(json) - 1;
        p += sprintf(p, ",\"voice\":\"%s\",\"sample_rate\":%lu", voice, engine->rate);
        if (engine->route && frag->State.LangID && frag->State.LangID != engine->language)
            p += sprintf(p, ",\"language\":%u", frag->State.LangID);
        strcpy(p, "}");
    }
    free(utf8);
    return json;
}

/* Nonblocking loopback HTTP/1.0 with Content-Length framing. Keeping the socket
 * on the SAPI calling thread makes abort and deadlines independent of Wine's
 * WinHTTP worker queues (closing those handles does not interrupt blocked I/O). */
static HRESULT socket_ready(SOCKET socket, BOOL write, ISpTTSEngineSite *site, ULONGLONG deadline)
{
    fd_set ready, errors;
    struct timeval interval;
    int result, error, size;
    for (;;)
    {
        if (ISpTTSEngineSite_GetActions(site) & SPVES_ABORT) return S_FALSE;
        if (GetTickCount64() >= deadline) return HRESULT_FROM_WIN32(ERROR_WINHTTP_TIMEOUT);
        FD_ZERO(&ready);
        FD_ZERO(&errors);
        FD_SET(socket, &ready);
        FD_SET(socket, &errors);
        interval.tv_sec = 0;
        interval.tv_usec = 50000;
        result = select(0, write ? NULL : &ready, write ? &ready : NULL, &errors, &interval);
        if (result == SOCKET_ERROR) return HRESULT_FROM_WIN32(ERROR_WINHTTP_CONNECTION_ERROR);
        if (!result) continue;
        size = sizeof(error);
        if (getsockopt(socket, SOL_SOCKET, SO_ERROR, (char *)&error, &size) == SOCKET_ERROR || error)
            return HRESULT_FROM_WIN32(ERROR_WINHTTP_CANNOT_CONNECT);
        return S_OK;
    }
}

static HRESULT fetch_wav(struct piper_engine *engine, const char *json,
                         ISpTTSEngineSite *site, BYTE **data, DWORD *size)
{
    SOCKET socket = INVALID_SOCKET;
    WSADATA winsock;
    struct sockaddr_in address = {0};
    ULONGLONG deadline = GetTickCount64() + 65000, send_deadline;
    char headers[16385], request[256], *line, *end, *value;
    DWORD length = 0, used = 0, header_size = 0;
    BOOL have_length = FALSE;
    BYTE *buffer = NULL;
    int count, offset, total;
    HRESULT hr = HRESULT_FROM_WIN32(ERROR_WINHTTP_CONNECTION_ERROR);

    *data = NULL;
    *size = 0;
    if (WSAStartup(MAKEWORD(2, 2), &winsock)) return hr;
    if ((socket = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0, 0)) == INVALID_SOCKET) goto done;
    {
        u_long nonblocking = 1;
        if (ioctlsocket(socket, FIONBIO, &nonblocking)) goto done;
    }
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(engine->port);
    if (connect(socket, (struct sockaddr *)&address, sizeof(address)) == SOCKET_ERROR &&
        WSAGetLastError() != WSAEWOULDBLOCK)
    {
        hr = HRESULT_FROM_WIN32(ERROR_WINHTTP_CANNOT_CONNECT);
        goto done;
    }
    if ((hr = socket_ready(socket, TRUE, site, GetTickCount64() + 3000)) != S_OK) goto done;
    total = sprintf(request, "POST /synthesize HTTP/1.0\r\nHost: 127.0.0.1:%lu\r\n"
                    "Content-Type: application/json\r\nContent-Length: %u\r\nConnection: close\r\n\r\n",
                    engine->port, (unsigned int)strlen(json));
    send_deadline = GetTickCount64() + 5000;
    for (offset = 0; offset < total; offset += count)
    {
        if ((hr = socket_ready(socket, TRUE, site, send_deadline)) != S_OK) goto done;
        count = send(socket, request + offset, total - offset, 0);
        if (count <= 0) { hr = HRESULT_FROM_WIN32(ERROR_WINHTTP_CONNECTION_ERROR); goto done; }
    }
    total = strlen(json);
    for (offset = 0; offset < total; offset += count)
    {
        if ((hr = socket_ready(socket, TRUE, site, send_deadline)) != S_OK) goto done;
        count = send(socket, json + offset, total - offset, 0);
        if (count <= 0) { hr = HRESULT_FROM_WIN32(ERROR_WINHTTP_CONNECTION_ERROR); goto done; }
    }
    /* Read only the bounded header here, leaving all audio bytes in the socket. */
    while (header_size < sizeof(headers) - 1)
    {
        if ((hr = socket_ready(socket, FALSE, site, deadline)) != S_OK) goto done;
        count = recv(socket, headers + header_size, 1, 0);
        if (count != 1) { hr = HRESULT_FROM_WIN32(ERROR_BAD_NET_RESP); goto done; }
        header_size++;
        if (header_size >= 4 && !memcmp(headers + header_size - 4, "\r\n\r\n", 4)) break;
    }
    hr = HRESULT_FROM_WIN32(ERROR_BAD_NET_RESP);
    headers[header_size] = 0;
    if (header_size < 4 || memcmp(headers + header_size - 4, "\r\n\r\n", 4)) goto done;
    if ((strncmp(headers, "HTTP/1.0 200 ", 13) && strncmp(headers, "HTTP/1.1 200 ", 13)) ||
        !(line = strstr(headers, "\r\n"))) goto done;
    line += 2;
    while ((end = strstr(line, "\r\n")) && end != line)
    {
        *end = 0;
        if (!_strnicmp(line, "Transfer-Encoding:", 18)) goto done;
        if (!_strnicmp(line, "Content-Length:", 15))
        {
            if (have_length) goto done;
            value = line + 15;
            while (*value == ' ' || *value == '\t') value++;
            if (*value < '0' || *value > '9') goto done;
            for (; *value >= '0' && *value <= '9'; value++)
            {
                if (length > (MAX_WAV_SIZE - (*value - '0')) / 10) goto done;
                length = length * 10 + *value - '0';
            }
            while (*value == ' ' || *value == '\t') value++;
            if (*value) goto done;
            have_length = TRUE;
        }
        line = end + 2;
    }
    if (!have_length || !length) goto done;
    if (!(buffer = malloc(length))) { hr = E_OUTOFMEMORY; goto done; }
    while (used < length)
    {
        if ((hr = socket_ready(socket, FALSE, site, deadline)) != S_OK) goto done;
        count = recv(socket, (char *)buffer + used, min(length - used, 65536), 0);
        if (count <= 0) { hr = HRESULT_FROM_WIN32(ERROR_BAD_NET_RESP); goto done; }
        used += count;
    }
    *data = buffer;
    *size = length;
    buffer = NULL;
    hr = S_OK;
done:
    if (socket != INVALID_SOCKET) closesocket(socket);
    WSACleanup();
    free(buffer);
    return hr;
}

static unsigned int read_u16(const BYTE *p) { return p[0] | p[1] << 8; }
static DWORD read_u32(const BYTE *p) { return p[0] | p[1] << 8 | p[2] << 16 | (DWORD)p[3] << 24; }

/* Validate every chunk before passing samples to the SAPI audio sink. */
static HRESULT parse_wav(BYTE *data, DWORD size, DWORD rate, BYTE **pcm, DWORD *pcm_size)
{
    DWORD pos, len, end;
    BOOL format = FALSE;

    *pcm = NULL;
    *pcm_size = 0;
    if (size < 12 || memcmp(data, "RIFF", 4) || memcmp(data + 8, "WAVE", 4) ||
        read_u32(data + 4) != size - 8) return SPERR_UNSUPPORTED_FORMAT;
    end = size;
    for (pos = 12; pos < end;)
    {
        if (end - pos < 8) return SPERR_UNSUPPORTED_FORMAT;
        len = read_u32(data + pos + 4);
        if (len > end - pos - 8) return SPERR_UNSUPPORTED_FORMAT;
        if (!memcmp(data + pos, "fmt ", 4))
        {
            const BYTE *fmt = data + pos + 8;
            if (format || len < 16 || read_u16(fmt) != WAVE_FORMAT_PCM || read_u16(fmt + 2) != 1 ||
                read_u32(fmt + 4) != rate || read_u32(fmt + 8) != rate * 2 ||
                read_u16(fmt + 12) != 2 || read_u16(fmt + 14) != 16) return SPERR_UNSUPPORTED_FORMAT;
            format = TRUE;
        }
        else if (!memcmp(data + pos, "data", 4))
        {
            if (*pcm || len & 1) return SPERR_UNSUPPORTED_FORMAT;
            *pcm = data + pos + 8;
            *pcm_size = len;
        }
        pos += 8 + len;
        if (len & 1)
        {
            if (pos == end) return SPERR_UNSUPPORTED_FORMAT;
            pos++;
        }
    }
    return format && *pcm && *pcm_size ? S_OK : SPERR_UNSUPPORTED_FORMAT;
}

static HRESULT write_pcm(ISpTTSEngineSite *site, const BYTE *pcm, DWORD size, ULONG fragment_volume)
{
    SHORT samples[2048];
    DWORD count, i, written, offset;
    USHORT volume;
    HRESULT hr;

    while (size)
    {
        if (ISpTTSEngineSite_GetActions(site) & SPVES_ABORT) return S_FALSE;
        if (FAILED(hr = ISpTTSEngineSite_GetVolume(site, &volume))) return hr;
        count = min(size, sizeof(samples));
        for (i = 0; i < count / 2; i++)
            samples[i] = (SHORT)read_u16(pcm + i * 2) * (int)min(volume, 100) *
                         (int)min(fragment_volume, 100) / 10000;
        for (offset = 0; offset < count; offset += written)
        {
            if (ISpTTSEngineSite_GetActions(site) & SPVES_ABORT) return S_FALSE;
            /* System.Speech accepts the buffer but leaves pcbWritten untouched.
             * Default to full acceptance; compliant hosts can still report partial
             * writes or zero progress, which are handled below. */
            written = count - offset;
            if (FAILED(hr = ISpTTSEngineSite_Write(site, (BYTE *)samples + offset, count - offset, &written)))
                return hr;
            if (!written || written > count - offset || (written & 1)) return STG_E_WRITEFAULT;
        }
        pcm += count;
        size -= count;
    }
    return S_OK;
}

static HRESULT WINAPI engine_Speak(ISpTTSEngine *iface, DWORD flags, REFGUID fmtid,
                                  const WAVEFORMATEX *wfx, const SPVTEXTFRAG *frag,
                                  ISpTTSEngineSite *site)
{
    struct piper_engine *engine = impl_from_engine(iface);
    BYTE *wav, *pcm;
    DWORD size, pcm_size;
    char *json;
    LONG rate;
    HRESULT hr;

    if (!fmtid || !wfx || !site) return E_POINTER;
    if (!engine->token) return SPERR_UNINITIALIZED;
    if (!IsEqualGUID(fmtid, &SPDFID_WaveFormatEx) || wfx->wFormatTag != WAVE_FORMAT_PCM ||
        wfx->nChannels != 1 || wfx->wBitsPerSample != 16 || wfx->nSamplesPerSec != engine->rate ||
        wfx->nBlockAlign != 2 || wfx->nAvgBytesPerSec != engine->rate * 2 || wfx->cbSize)
        return SPERR_UNSUPPORTED_FORMAT;
    for (; frag; frag = frag->pNext)
    {
        if (ISpTTSEngineSite_GetActions(site) & SPVES_ABORT) return S_OK;
        if (frag->State.eAction == SPVA_Silence)
        {
            BYTE silence[4096] = {0};
            ULONGLONG left = (ULONGLONG)engine->rate * frag->State.SilenceMSecs / 1000 * 2;
            while (left)
            {
                DWORD chunk = min(left, sizeof(silence));
                if ((hr = write_pcm(site, silence, chunk, 100)) != S_OK) return hr == S_FALSE ? S_OK : hr;
                left -= chunk;
            }
            continue;
        }
        if (frag->State.eAction != SPVA_Speak) return E_NOTIMPL;
        if (!frag->ulTextLen) continue;
        if (!frag->pTextStart) return E_POINTER;
        if (frag->ulTextLen > MAX_TEXT_LENGTH) return E_INVALIDARG;
        if (FAILED(hr = ISpTTSEngineSite_GetRate(site, &rate))) return hr;
        if (!(json = make_request(frag, rate, engine))) return E_INVALIDARG;
        hr = fetch_wav(engine, json, site, &wav, &size);
        free(json);
        if (hr != S_OK) return hr == S_FALSE ? S_OK : hr;
        hr = parse_wav(wav, size, engine->rate, &pcm, &pcm_size);
        if (SUCCEEDED(hr)) hr = write_pcm(site, pcm, pcm_size, frag->State.Volume);
        free(wav);
        if (hr != S_OK) return hr == S_FALSE ? S_OK : hr;
    }
    return S_OK;
}

static HRESULT WINAPI engine_GetOutputFormat(ISpTTSEngine *iface, const GUID *target_id,
                                             const WAVEFORMATEX *target, GUID *id, WAVEFORMATEX **out)
{
    WAVEFORMATEX *wfx;
    if (!id || !out) return E_POINTER;
    *out = NULL;
    if (!(wfx = CoTaskMemAlloc(sizeof(*wfx)))) return E_OUTOFMEMORY;
    wfx->wFormatTag = WAVE_FORMAT_PCM;
    wfx->nChannels = 1;
    wfx->nSamplesPerSec = impl_from_engine(iface)->rate;
    wfx->wBitsPerSample = 16;
    wfx->nBlockAlign = 2;
    wfx->nAvgBytesPerSec = wfx->nSamplesPerSec * 2;
    wfx->cbSize = 0;
    *id = SPDFID_WaveFormatEx;
    *out = wfx;
    return S_OK;
}

static const ISpTTSEngineVtbl engine_vtbl =
{
    engine_QueryInterface, engine_AddRef, engine_Release, engine_Speak, engine_GetOutputFormat
};

static HRESULT WINAPI token_QueryInterface(ISpObjectWithToken *iface, REFIID iid, void **out)
{
    return engine_QueryInterface(&impl_from_token(iface)->ISpTTSEngine_iface, iid, out);
}
static ULONG WINAPI token_AddRef(ISpObjectWithToken *iface)
{
    return engine_AddRef(&impl_from_token(iface)->ISpTTSEngine_iface);
}
static ULONG WINAPI token_Release(ISpObjectWithToken *iface)
{
    return engine_Release(&impl_from_token(iface)->ISpTTSEngine_iface);
}
static HRESULT WINAPI token_SetObjectToken(ISpObjectWithToken *iface, ISpObjectToken *token)
{
    struct piper_engine *engine = impl_from_token(iface);
    DWORD rate = 22050, port = 5000, size;
    WCHAR *id = NULL;
    HKEY key;
    LONG result;
    HRESULT hr;
    if (!token) return E_INVALIDARG;
    if (engine->token) return SPERR_ALREADY_INITIALIZED;
    hr = ISpObjectToken_GetId(token, &id);
    if (FAILED(hr)) return hr;
    if (wcsncmp(id, L"HKEY_LOCAL_MACHINE\\", 19)) { CoTaskMemFree(id); return E_INVALIDARG; }
    result = RegOpenKeyExW(HKEY_LOCAL_MACHINE, id + 19, 0, KEY_READ | KEY_WOW64_64KEY, &key);
    CoTaskMemFree(id);
    if (result) return HRESULT_FROM_WIN32(result);
    size = sizeof(rate);
    result = RegGetValueW(key, NULL, L"SampleRate", RRF_RT_REG_DWORD, NULL, &rate, &size);
    if (!result) { size = sizeof(port); result = RegGetValueW(key, NULL, L"Port", RRF_RT_REG_DWORD, NULL, &port, &size); }
    if (!result)
    {
        DWORD i;
        size = sizeof(engine->voice);
        RegGetValueW(key,NULL,L"VoiceID",RRF_RT_REG_SZ,NULL,engine->voice,&size);
        for (i = 0; engine->voice[i]; i++)
            if (!(engine->voice[i] >= 'a' && engine->voice[i] <= 'z') &&
                !(engine->voice[i] >= 'A' && engine->voice[i] <= 'Z') &&
                !(engine->voice[i] >= '0' && engine->voice[i] <= '9') &&
                engine->voice[i] != '_' && engine->voice[i] != '-')
            { RegCloseKey(key); return E_INVALIDARG; }
        size = sizeof(engine->language);
        RegGetValueW(key,NULL,L"LanguageID",RRF_RT_REG_DWORD,NULL,&engine->language,&size);
        size = sizeof(engine->route);
        RegGetValueW(key,NULL,L"RouteLanguages",RRF_RT_REG_DWORD,NULL,&engine->route,&size);
    }
    RegCloseKey(key);
    if (result) return HRESULT_FROM_WIN32(result);
    if (rate < 8000 || rate > 192000 || !port || port > 65535) return E_INVALIDARG;
    engine->rate = rate;
    engine->port = port;
    engine->token = token;
    ISpObjectToken_AddRef(token);
    return S_OK;
}
static HRESULT WINAPI token_GetObjectToken(ISpObjectWithToken *iface, ISpObjectToken **token)
{
    struct piper_engine *engine = impl_from_token(iface);
    if (!token) return E_POINTER;
    *token = engine->token;
    if (!*token) return SPERR_UNINITIALIZED;
    ISpObjectToken_AddRef(*token);
    return S_OK;
}
static const ISpObjectWithTokenVtbl token_vtbl =
{
    token_QueryInterface, token_AddRef, token_Release, token_SetObjectToken, token_GetObjectToken
};

HRESULT piper_engine_create(IUnknown *outer, REFIID iid, void **out)
{
    struct piper_engine *engine;
    HRESULT hr;
    if (outer) return CLASS_E_NOAGGREGATION;
    if (!(engine = calloc(1, sizeof(*engine)))) return E_OUTOFMEMORY;
    InterlockedIncrement(&opensapi_objects);
    engine->ISpTTSEngine_iface.lpVtbl = &engine_vtbl;
    engine->ISpObjectWithToken_iface.lpVtbl = &token_vtbl;
    engine->ref = 1;
    engine->rate = 22050;
    engine->port = 5000;
    hr = engine_QueryInterface(&engine->ISpTTSEngine_iface, iid, out);
    engine_Release(&engine->ISpTTSEngine_iface);
    return hr;
}
