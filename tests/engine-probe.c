/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Direct engine host for error, partial-write and cancellation regression tests.
 */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <sapi.h>
#include <sapiddk.h>
#include <stdio.h>
#include <stdlib.h>

static const GUID piper_clsid = {0x7c8b3f91, 0x6f72, 0x4c5b, {0xa6, 0x0f, 0x2e, 0x89, 0x5a, 0xb1, 0x43, 0xd2}};
static HANDLE output;
static ULONG total;
static LONG rate;
static USHORT volume;
static BOOL partial, abort_output, fail_write, no_count, zero_write;
static BOOL abort_network;
static ULONGLONG started;

static HRESULT WINAPI site_qi(ISpTTSEngineSite *iface, REFIID iid, void **out)
{
    *out = NULL;
    if (!IsEqualIID(iid, &IID_IUnknown) && !IsEqualIID(iid, &IID_ISpTTSEngineSite)) return E_NOINTERFACE;
    *out = iface;
    return S_OK;
}
static ULONG WINAPI site_addref(ISpTTSEngineSite *iface) { return 2; }
static ULONG WINAPI site_release(ISpTTSEngineSite *iface) { return 1; }
static HRESULT WINAPI site_events(ISpTTSEngineSite *iface, const SPEVENT *events, ULONG count) { return S_OK; }
static HRESULT WINAPI site_interest(ISpTTSEngineSite *iface, ULONGLONG *interest) { *interest = 0; return S_OK; }
static DWORD WINAPI site_actions(ISpTTSEngineSite *iface) { return (abort_output && total) || (abort_network && GetTickCount64() - started >= 300) ? SPVES_ABORT : 0; }
static HRESULT WINAPI site_write(ISpTTSEngineSite *iface, const void *data, ULONG size, ULONG *written)
{
    DWORD count = partial ? min(size, 14) : size;
    if (fail_write) return STG_E_WRITEFAULT;
    if (zero_write) { *written = 0; return S_OK; }
    if (!WriteFile(output, data, count, &count, NULL)) return E_FAIL;
    /* Match System.Speech's EngineSiteSapi.Write, which accepts data without
     * storing the count through pcbWritten. */
    if (!no_count) *written = count;
    total += count;
    return S_OK;
}
static HRESULT WINAPI site_rate(ISpTTSEngineSite *iface, LONG *out) { *out = rate; return S_OK; }
static HRESULT WINAPI site_volume(ISpTTSEngineSite *iface, USHORT *out) { *out = volume; return S_OK; }
static HRESULT WINAPI site_skip(ISpTTSEngineSite *iface, SPVSKIPTYPE *type, LONG *count) { return E_NOTIMPL; }
static HRESULT WINAPI site_complete(ISpTTSEngineSite *iface, LONG count) { return E_NOTIMPL; }
static const ISpTTSEngineSiteVtbl site_vtbl =
{
    site_qi, site_addref, site_release, site_events, site_interest, site_actions,
    site_write, site_rate, site_volume, site_skip, site_complete
};

int wmain(int argc, WCHAR **argv)
{
    ISpTTSEngineSite site = {&site_vtbl};
    ISpTTSEngine *engine;
    ISpObjectWithToken *with_token;
    ISpObjectToken *token;
    SPVTEXTFRAG fragment = {0};
    SPVTEXTFRAG silence = {0}, tail;
    WAVEFORMATEX *format;
    GUID id;
    HRESULT hr;
    if (argc != 6) return 2;
    rate = wcstol(argv[2], NULL, 10);
    volume = wcstoul(argv[3], NULL, 10);
    partial = !wcscmp(argv[5], L"partial");
    abort_output = !wcscmp(argv[5], L"abort");
    fail_write = !wcscmp(argv[5], L"fail-write");
    no_count = !wcscmp(argv[5], L"no-count");
    abort_network = !wcscmp(argv[5], L"abort-network") || !wcscmp(argv[5], L"recover-cancel");
    zero_write = !wcscmp(argv[5], L"zero-write");
    output = CreateFileW(argv[1], GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, 0, NULL);
    if (output == INVALID_HANDLE_VALUE) return 2;
    CoInitializeEx(NULL, COINIT_MULTITHREADED);
    hr = CoCreateInstance(&piper_clsid, NULL, CLSCTX_INPROC_SERVER, &IID_ISpTTSEngine, (void **)&engine);
    if (FAILED(hr)) { fprintf(stderr, "engine creation failed: %#lx\n", hr); return 2; }
    if (wcscmp(argv[5], L"uninitialized"))
    {
        hr = CoCreateInstance(&CLSID_SpObjectToken, NULL, CLSCTX_INPROC_SERVER, &IID_ISpObjectToken, (void **)&token);
        if (FAILED(hr)) return 2;
        hr = ISpObjectToken_SetId(token, NULL, L"HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\OpenSAPI-Piper", FALSE);
        if (FAILED(hr)) return 2;
        hr = ISpTTSEngine_QueryInterface(engine, &IID_ISpObjectWithToken, (void **)&with_token);
        if (FAILED(hr)) return 2;
        hr = ISpObjectWithToken_SetObjectToken(with_token, token);
        ISpObjectWithToken_Release(with_token);
        ISpObjectToken_Release(token);
        if (FAILED(hr)) return 2;
    }
    hr = ISpTTSEngine_GetOutputFormat(engine, NULL, NULL, &id, &format);
    if (FAILED(hr)) return 2;
    fragment.State.eAction = SPVA_Speak;
    fragment.State.Volume = 100;
    fragment.pTextStart = argv[4];
    fragment.ulTextLen = wcslen(argv[4]);
    if (!wcscmp(argv[5], L"silence"))
    {
        tail = fragment;
        fragment.pNext = &silence;
        silence.State.eAction = SPVA_Silence;
        silence.State.SilenceMSecs = 100;
        silence.pNext = &tail;
    }
    started = GetTickCount64();
    hr = ISpTTSEngine_Speak(engine, 0, &id, format, &fragment, &site);
    printf("result: %#lx, bytes: %lu\n", hr, total);
    if (!wcscmp(argv[5], L"recover-cancel"))
    {
        if (FAILED(hr) || total) return 2;
        abort_network = FALSE;
        hr = ISpTTSEngine_Speak(engine, 0, &id, format, &fragment, &site);
        printf("cancel recovery: %#lx, bytes: %lu\n", hr, total);
    }
    if (!wcscmp(argv[5], L"recover"))
    {
        if (SUCCEEDED(hr) || total) return 2;
        hr = ISpTTSEngine_Speak(engine, 0, &id, format, &fragment, &site);
        printf("recovery: %#lx, bytes: %lu\n", hr, total);
    }
    CoTaskMemFree(format);
    ISpTTSEngine_Release(engine);
    CoUninitialize();
    CloseHandle(output);
    return FAILED(hr) ? 1 : 0;
}
