/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 John Goodman
 */
/*
 * Minimal native SAPI client; no dependency on Piper or private Wine APIs.
 * Usage: sapi-probe.exe output.wav rate volume text [async|xml|default|play|automation]
 */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <sapi.h>
#include <sperror.h>
#include <stdio.h>
#include <stdlib.h>

const GUID SPDFID_WaveFormatEx = {0xc31adbae, 0x527f, 0x4ff5, {0xa2, 0x30, 0xf6, 0x2b, 0xb6, 0x1f, 0xf7, 0x0c}};

static void check(HRESULT hr, const char *operation)
{
    if (FAILED(hr))
    {
        fprintf(stderr, "%s failed: %#lx\n", operation, (unsigned long)hr);
        exit(1);
    }
}

static void save_wav(const WCHAR *filename, IStream *base, const WAVEFORMATEX *format)
{
    BYTE header[44] = "RIFF\0\0\0\0WAVEfmt \x10\0\0\0\x01\0\x01\0";
    STATSTG stat;
    HGLOBAL memory;
    HANDLE file;
    DWORD size, riff_size, written;
    void *data;
    check(IStream_Stat(base, &stat, STATFLAG_NONAME), "output size");
    if (stat.cbSize.QuadPart > MAXDWORD - 36) exit(1);
    size = stat.cbSize.LowPart;
    riff_size = size + 36;
    memcpy(header + 4, &riff_size, 4);
    memcpy(header + 24, &format->nSamplesPerSec, 4);
    memcpy(header + 28, &format->nAvgBytesPerSec, 4);
    memcpy(header + 32, &format->nBlockAlign, 2);
    memcpy(header + 34, &format->wBitsPerSample, 2);
    memcpy(header + 36, "data", 4);
    memcpy(header + 40, &size, 4);
    check(GetHGlobalFromStream(base, &memory), "output memory");
    data = GlobalLock(memory);
    file = CreateFileW(filename, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    if (file == INVALID_HANDLE_VALUE ||
        !WriteFile(file, header, sizeof(header), &written, NULL) || written != sizeof(header) ||
        !WriteFile(file, data, size, &written, NULL) || written != size)
    {
        fprintf(stderr, "could not save WAV: %lu\n", GetLastError());
        exit(1);
    }
    CloseHandle(file);
    GlobalUnlock(memory);
}

int wmain(int argc, wchar_t **argv)
{
    ISpVoice *voice;
    ISpObjectTokenCategory *category;
    IEnumSpObjectTokens *tokens;
    ISpObjectToken *token, *selected = NULL;
    ISpStream *stream = NULL;
    IStream *base = NULL;
    WCHAR *id;
    ULONG fetched, count;
    WAVEFORMATEX format = {WAVE_FORMAT_PCM, 1, 22050, 44100, 2, 16, 0};
    DWORD sample_rate;
    ULONG flags = SPF_IS_NOT_XML;
    BOOL async = argc > 5 && !wcscmp(argv[5], L"async");
    BOOL use_default = argc > 5 && !wcscmp(argv[5], L"default");
    BOOL play = argc > 5 && !wcscmp(argv[5], L"play");
    BOOL missing_token = argc > 5 && !wcscmp(argv[5], L"missing-token");
    BOOL missing = missing_token || (argc > 5 && !wcscmp(argv[5], L"missing"));
    BOOL automation = argc > 5 && !wcscmp(argv[5], L"automation");

    if (argc < 5)
    {
        fprintf(stderr, "usage: sapi-probe.exe output.wav rate volume text [async|xml|default|play|automation]\n");
        return 2;
    }
    check(CoInitializeEx(NULL, COINIT_MULTITHREADED), "CoInitializeEx");
    check(CoCreateInstance(&CLSID_SpObjectTokenCategory, NULL, CLSCTX_INPROC_SERVER,
                          &IID_ISpObjectTokenCategory, (void **)&category), "create category");
    check(ISpObjectTokenCategory_SetId(category, SPCAT_VOICES, FALSE), "open voices");
    check(ISpObjectTokenCategory_EnumTokens(category, missing ? L"Vendor=Akousousin" : NULL, NULL, &tokens), "enumerate voices");
    check(IEnumSpObjectTokens_GetCount(tokens, &count), "voice count");
    printf("voices: %lu\n", count);
    while (IEnumSpObjectTokens_Next(tokens, 1, &token, &fetched) == S_OK)
    {
        check(ISpObjectToken_GetId(token, &id), "token id");
        wprintf(L"voice: %ls\n", id);
        if (wcsstr(id, L"Akousousin-Piper"))
        {
            if (selected) ISpObjectToken_Release(selected);
            selected = token;
            ISpObjectToken_AddRef(selected);
        }
        CoTaskMemFree(id);
        ISpObjectToken_Release(token);
    }
    IEnumSpObjectTokens_Release(tokens);
    ISpObjectTokenCategory_Release(category);
    if (missing)
    {
        HRESULT hr;
        if (selected || count) return 2;
        if (missing_token)
        {
            WCHAR token_id[1024];
            if (!GetEnvironmentVariableW(L"AKOUSOUSIN_TOKEN", token_id, 1024)) return 2;
            check(CoCreateInstance(&CLSID_SpObjectToken, NULL, CLSCTX_INPROC_SERVER,
                                  &IID_ISpObjectToken, (void **)&token), "create absent token test");
            hr = ISpObjectToken_SetId(token, NULL, token_id, FALSE);
            ISpObjectToken_Release(token);
            CoUninitialize();
            return hr == SPERR_NOT_FOUND ? 0 : 2;
        }
        check(CoCreateInstance(&CLSID_SpVoice, NULL, CLSCTX_INPROC_SERVER,
                              &IID_ISpVoice, (void **)&voice), "create voice without token");
        hr = ISpVoice_Speak(voice, argv[4], SPF_IS_NOT_XML, NULL);
        ISpVoice_Release(voice);
        CoUninitialize();
        printf("missing voice result: %#lx\n", hr);
        return hr == SPERR_NOT_FOUND ? 0 : 2;
    }
    if (!selected) { fprintf(stderr, "No Akousousin-Piper voice registered\n"); return 1; }
    check(ISpObjectToken_GetDWORD(selected, L"SampleRate", &sample_rate), "sample rate");
    format.nSamplesPerSec = sample_rate;
    format.nAvgBytesPerSec = sample_rate * 2;
    check(CoCreateInstance(&CLSID_SpVoice, NULL, CLSCTX_INPROC_SERVER,
                          &IID_ISpVoice, (void **)&voice), "create voice");
    if (!use_default) check(ISpVoice_SetVoice(voice, selected), "select Piper");
    ISpObjectToken_Release(selected);
    if (!play)
    {
        check(CoCreateInstance(&CLSID_SpStream, NULL, CLSCTX_INPROC_SERVER,
                              &IID_ISpStream, (void **)&stream), "create output stream");
        check(CreateStreamOnHGlobal(NULL, TRUE, &base), "create PCM stream");
        check(ISpStream_SetBaseStream(stream, base, &SPDFID_WaveFormatEx, &format), "set PCM stream");
        check(ISpVoice_SetOutput(voice, (IUnknown *)stream, FALSE), "set output");
    }
    check(ISpVoice_SetRate(voice, wcstol(argv[2], NULL, 10)), "set rate");
    check(ISpVoice_SetVolume(voice, wcstoul(argv[3], NULL, 10)), "set volume");
    if (async) flags |= SPF_ASYNC;
    if (argc > 5 && !wcscmp(argv[5], L"xml")) flags = SPF_IS_XML;
    if (automation)
    {
        ISpeechVoice *speech;
        ISpeechObjectTokens *voices;
        LONG voice_count, stream_number;
        BSTR text = SysAllocString(argv[4]);
        if (!text) return 1;
        check(ISpVoice_QueryInterface(voice, &IID_ISpeechVoice, (void **)&speech), "automation voice");
        check(ISpeechVoice_GetVoices(speech, NULL, NULL, &voices), "automation voices");
        check(ISpeechObjectTokens_get_Count(voices, &voice_count), "automation count");
        if (!voice_count) return 1;
        ISpeechObjectTokens_Release(voices);
        check(ISpeechVoice_Speak(speech, text, SVSFIsNotXML, &stream_number), "automation speak");
        ISpeechVoice_Release(speech);
        SysFreeString(text);
    }
    else check(ISpVoice_Speak(voice, argv[4], flags, NULL), "speak");
    if (async)
    {
        SPVOICESTATUS status;
        HRESULT hr = ISpVoice_WaitUntilDone(voice, 60000);
        if (hr != S_OK) { fprintf(stderr, "speech did not finish: %#lx\n", hr); return 1; }
        check(ISpVoice_GetStatus(voice, &status, NULL), "speech status");
        check(status.hrLastResult, "asynchronous synthesis");
    }
    ISpVoice_Release(voice);
    if (stream)
    {
        /* BindToFile is a stub in this Wine revision. Use the standard
         * SetBaseStream API, then wrap the resulting PCM in a WAV container. */
        save_wav(argv[1], base, &format);
        check(ISpStream_Close(stream), "close WAV output");
        ISpStream_Release(stream);
        IStream_Release(base);
    }
    CoUninitialize();
    puts("speech completed");
    return 0;
}
