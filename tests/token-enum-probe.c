/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Exercise ISpDataKey::EnumValues, including System.Speech's attribute loop.
 */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <sapi.h>
#include <sapiddk.h>
#include <sperror.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

#define REQUIRE(condition, message) do { if (!(condition)) { fprintf(stderr, "%s (line %d)\n", message, __LINE__); exit(1); } } while (0)

static void check_voice_attributes(void)
{
    ISpObjectToken *token;
    ISpDataKey *attributes;
    WCHAR *name, *value;
    HRESULT hr;
    ULONG index;
    unsigned found = 0;

    hr = CoCreateInstance(&CLSID_SpObjectToken, NULL, CLSCTX_INPROC_SERVER,
                          &IID_ISpObjectToken, (void **)&token);
    REQUIRE(hr == S_OK, "create voice token failed");
    hr = ISpObjectToken_SetId(token, NULL,
        L"HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\Akousousin-Piper", FALSE);
    REQUIRE(hr == S_OK, "open Piper token failed");
    hr = ISpObjectToken_OpenKey(token, L"Attributes", &attributes);
    REQUIRE(hr == S_OK, "open Piper attributes failed");
    /* Same S_OK loop and string retrieval as System.Speech RegistryDataKey. */
    for (index = 0; index < 32; index++)
    {
        hr = ISpDataKey_EnumValues(attributes, index, &name);
        if (hr == SPERR_NO_MORE_ITEMS) break;
        REQUIRE(hr == S_OK, "Piper attribute enumeration failed");
        hr = ISpDataKey_GetStringValue(attributes, name, &value);
        REQUIRE(hr == S_OK, "Piper attribute string retrieval failed");
        if (!wcscmp(name, L"Name"))
        {
            REQUIRE(!wcscmp(value, L"Piper (Akousousin)"), "incorrect voice Name");
            found |= 1;
        }
        else if (!wcscmp(name, L"Vendor"))
        {
            REQUIRE(!wcscmp(value, L"Akousousin"), "incorrect voice Vendor");
            found |= 2;
        }
        else if (!wcscmp(name, L"Language"))
        {
            REQUIRE(!wcscmp(value, L"409"), "incorrect test voice Language");
            found |= 4;
        }
        CoTaskMemFree(value);
        CoTaskMemFree(name);
    }
    REQUIRE(index < 32 && found == 7, ".NET-style voice discovery omitted required attributes");
    ISpDataKey_Release(attributes);
    ISpObjectToken_Release(token);
}

int wmain(void)
{
    ISpRegDataKey *data;
    WCHAR path[128], long_name[2049], *name;
    const WCHAR *names[] = {L"", L"Text", L"Number", L"Binary", L"\x8a9e\x2603", long_name};
    const BYTE bytes[] = {1, 2, 3};
    DWORD number = 42, disposition;
    HKEY key;
    HRESULT hr;
    ULONG index;
    unsigned found = 0, bit;
    size_t i;

    REQUIRE(SUCCEEDED(CoInitializeEx(NULL, COINIT_MULTITHREADED)), "COM initialization failed");
    check_voice_attributes();
    hr = CoCreateInstance(&CLSID_SpDataKey, NULL, CLSCTX_INPROC_SERVER,
                          &IID_ISpRegDataKey, (void **)&data);
    REQUIRE(hr == S_OK, "create data key failed");
    name = (WCHAR *)1;
    hr = ISpRegDataKey_EnumValues(data, 0, &name);
    REQUIRE(hr == E_HANDLE && !name, "uninitialized key handling failed");
    REQUIRE(ISpRegDataKey_EnumValues(data, 0, NULL) == E_POINTER, "null output handling failed");
    _snwprintf(path, sizeof(path) / sizeof(path[0]), L"Software\\Akousousin\\EnumValues-%lu", GetCurrentProcessId());
    REQUIRE(RegCreateKeyExW(HKEY_CURRENT_USER, path, 0, NULL, 0, KEY_ALL_ACCESS,
                            NULL, &key, &disposition) == ERROR_SUCCESS, "create test key failed");
    REQUIRE(disposition == REG_CREATED_NEW_KEY, "refusing to reuse an existing registry key");
    REQUIRE(ISpRegDataKey_SetKey(data, key, FALSE) == S_OK, "attach registry key failed");
    name = (WCHAR *)1;
    REQUIRE(ISpRegDataKey_EnumValues(data, 0, &name) == SPERR_NO_MORE_ITEMS && !name, "empty key handling failed");
    wmemset(long_name, L'x', 2048);
    long_name[2048] = 0;
    for (i = 0; i < sizeof(names) / sizeof(names[0]); i++)
    {
        DWORD type = i == 2 ? REG_DWORD : i == 3 ? REG_BINARY : REG_SZ;
        const BYTE *content = i == 2 ? (const BYTE *)&number : i == 3 ? bytes : (const BYTE *)L"value";
        DWORD size = i == 2 ? sizeof(number) : i == 3 ? sizeof(bytes) : sizeof(L"value");
        REQUIRE(RegSetValueExW(key, names[i], 0, type, content, size) == ERROR_SUCCESS, "write test value failed");
    }
    for (index = 0; index < 16; index++)
    {
        hr = ISpRegDataKey_EnumValues(data, index, &name);
        if (hr == SPERR_NO_MORE_ITEMS) break;
        REQUIRE(hr == S_OK && name, "value enumeration failed");
        bit = 0;
        for (i = 0; i < sizeof(names) / sizeof(names[0]); i++)
            if (!wcscmp(name, names[i])) bit = 1u << i;
        REQUIRE(bit && !(found & bit), "unknown or duplicate enumerated value name");
        found |= bit;
        CoTaskMemFree(name);
    }
    REQUIRE(index == 6 && found == 63, "enumeration dropped a value or failed to terminate");
    name = (WCHAR *)1;
    REQUIRE(ISpRegDataKey_EnumValues(data, 999, &name) == SPERR_NO_MORE_ITEMS && !name, "past-end handling failed");
    ISpRegDataKey_Release(data);
    REQUIRE(RegDeleteTreeW(HKEY_CURRENT_USER, path) == ERROR_SUCCESS, "test registry cleanup failed");
    CoUninitialize();
    puts("EnumValues regression passed: .NET-style Piper attributes, empty/unnamed/Unicode/long names, mixed value types, boundaries and cleanup.");
    return 0;
}
