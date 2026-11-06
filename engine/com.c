/*
 * SPDX-License-Identifier: LGPL-2.1-or-later
 * SPDX-FileCopyrightText: 2026 John Goodman
 */
#define COBJMACROS
#include <windows.h>
#include <objbase.h>
#include <sapi.h>
#include "engine.h"
static const CLSID piper_clsid = {0xea7a00ab,0x0fb7,0x4deb,{0x81,0xc5,0x55,0x0d,0x85,0x4f,0x39,0x0f}};
const GUID SPDFID_WaveFormatEx = {0xc31adbae, 0x527f, 0x4ff5, {0xa2, 0x30, 0xf6, 0x2b, 0xb6, 0x1f, 0xf7, 0x0c}};
LONG akousousin_objects;
static LONG locks;
static HMODULE module;
static HRESULT WINAPI factory_qi(IClassFactory *self, REFIID iid, void **out)
{
    if (!out) return E_POINTER;
    *out = NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IClassFactory)) return E_NOINTERFACE;
    *out=self; IClassFactory_AddRef(self); return S_OK;
}
static ULONG WINAPI factory_add(IClassFactory *self) { return InterlockedIncrement(&akousousin_objects); }
static ULONG WINAPI factory_release(IClassFactory *self) { return InterlockedDecrement(&akousousin_objects); }
static HRESULT WINAPI factory_create(IClassFactory *self,IUnknown *outer,REFIID iid,void **out)
{ return piper_engine_create(outer,iid,out); }
static HRESULT WINAPI factory_lock(IClassFactory *self,BOOL lock)
{ if (lock) InterlockedIncrement(&locks); else InterlockedDecrement(&locks); return S_OK; }
static const IClassFactoryVtbl factory_vtbl={factory_qi,factory_add,factory_release,factory_create,factory_lock};
static IClassFactory factory={&factory_vtbl};
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,void *reserved)
{ if (reason==DLL_PROCESS_ATTACH) { module=instance; DisableThreadLibraryCalls(instance); } return TRUE; }
__declspec(dllexport) HRESULT WINAPI DllGetClassObject(REFCLSID clsid,REFIID iid,void **out)
{ if (!IsEqualCLSID(clsid,&piper_clsid)) { if(out)*out=NULL; return CLASS_E_CLASSNOTAVAILABLE; }
  return IClassFactory_QueryInterface(&factory,iid,out); }
__declspec(dllexport) HRESULT WINAPI DllCanUnloadNow(void)
{ return akousousin_objects || locks ? S_FALSE : S_OK; }
__declspec(dllexport) HRESULT WINAPI DllRegisterServer(void)
{
    WCHAR path[32768]; HKEY key; LONG ret;
    if (!GetModuleFileNameW(module,path,32768)) return HRESULT_FROM_WIN32(GetLastError());
    ret=RegCreateKeyExW(HKEY_CURRENT_USER,L"Software\\Classes\\CLSID\\{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}\\InprocServer32",0,NULL,0,KEY_WRITE|KEY_WOW64_64KEY,NULL,&key,NULL);
    if(ret) return HRESULT_FROM_WIN32(ret);
    ret=RegSetValueExW(key,NULL,0,REG_SZ,(BYTE*)path,(lstrlenW(path)+1)*sizeof(WCHAR));
    if(!ret) ret=RegSetValueExW(key,L"ThreadingModel",0,REG_SZ,(BYTE*)L"Both",sizeof(L"Both"));
    RegCloseKey(key);return HRESULT_FROM_WIN32(ret);
}
__declspec(dllexport) HRESULT WINAPI DllUnregisterServer(void)
{
    WCHAR path[32768],installed[32768];DWORD size=sizeof(installed);LONG ret;
    const WCHAR *key=L"Software\\Classes\\CLSID\\{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}";
    if(!GetModuleFileNameW(module,path,32768)) return E_FAIL;
    ret=RegGetValueW(HKEY_CURRENT_USER,L"Software\\Classes\\CLSID\\{EA7A00AB-0FB7-4DEB-81C5-550D854F390F}\\InprocServer32",NULL,RRF_RT_REG_SZ,NULL,installed,&size);
    if(ret==ERROR_FILE_NOT_FOUND) return S_OK;
    if(ret || lstrcmpiW(path,installed)) return S_FALSE;
    return HRESULT_FROM_WIN32(RegDeleteTreeW(HKEY_CURRENT_USER,key));
}
