/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * SPDX-FileCopyrightText: 2026 John Goodman
 */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <objbase.h>
#include <stdio.h>
#include <wchar.h>

/* Public SAPI identities. No imported implementation or engine modification. */
static const CLSID reg_data_key = {0xd9f6ee60,0x58c9,0x458b,{0x88,0xe1,0x2f,0xd7,0xf8,0x8f,0x8f,0x7c}};
static const CLSID voice = {0x96749377,0x3391,0x11d2,{0x9e,0xe3,0x00,0xc0,0x4f,0x79,0x73,0x96}};

int wmain(int argc, wchar_t **argv)
{
    HMODULE module = NULL;
    wchar_t path[32768], search[32768];
    HRESULT hr = S_OK;
    IUnknown *object = NULL;
    MEMORY_BASIC_INFORMATION memory;
    if (argc != 2 && argc != 3) return 2;
    if (GetEnvironmentVariableW(L"PATH", search, 32768)) wprintf(L"PATH=%ls\n", search);
    if (!wcscmp(argv[1], L"load"))
    {
        module = LoadLibraryW(argc == 3 ? argv[2] : L"sapi.dll");
        if (!module) { wprintf(L"ERROR=%lu\n", GetLastError()); return 3; }
    }
    else
    {
        CoInitializeEx(NULL, COINIT_MULTITHREADED);
        hr = CoCreateInstance(!wcscmp(argv[1], L"voice") ? &voice : &reg_data_key,
                             NULL, CLSCTX_INPROC_SERVER, &IID_IUnknown, (void **)&object);
        wprintf(L"HRESULT=%08lx\n", (unsigned long)hr);
        if (object && VirtualQuery(object->lpVtbl, &memory, sizeof(memory)))
            module = (HMODULE)memory.AllocationBase;
        if (!module) module = GetModuleHandleW(L"sapi.dll");
    }
    if (module && GetModuleFileNameW(module, path, 32768)) wprintf(L"MODULE=%ls\n", path);
    else wprintf(L"MODULE=unknown\n");
    if (object) IUnknown_Release(object);
    if (wcscmp(argv[1], L"load")) CoUninitialize();
    else FreeLibrary(module);
    return FAILED(hr) ? 4 : 0;
}
