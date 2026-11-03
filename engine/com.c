/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define COBJMACROS
#include <windows.h>
#include <objbase.h>
#include <sapi.h>
#include "engine.h"
static const CLSID piper_clsid = {0x7c8b3f91,0x6f72,0x4c5b,{0xa6,0x0f,0x2e,0x89,0x5a,0xb1,0x43,0xd2}};
const GUID SPDFID_WaveFormatEx = {0xc31adbae, 0x527f, 0x4ff5, {0xa2, 0x30, 0xf6, 0x2b, 0xb6, 0x1f, 0xf7, 0x0c}};
LONG opensapi_objects;
static LONG locks;
static HMODULE module;
static HRESULT WINAPI factory_qi(IClassFactory *self, REFIID iid, void **out)
{
    if (!out) return E_POINTER;
    *out = NULL;
    if (!IsEqualIID(iid,&IID_IUnknown) && !IsEqualIID(iid,&IID_IClassFactory)) return E_NOINTERFACE;
    *out=self; IClassFactory_AddRef(self); return S_OK;
}
static ULONG WINAPI factory_add(IClassFactory *self) { return InterlockedIncrement(&opensapi_objects); }
static ULONG WINAPI factory_release(IClassFactory *self) { return InterlockedDecrement(&opensapi_objects); }
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
{ return opensapi_objects || locks ? S_FALSE : S_OK; }
__declspec(dllexport) HRESULT WINAPI DllRegisterServer(void)
{
    WCHAR path[32768]; HKEY key; LONG ret;
    if (!GetModuleFileNameW(module,path,32768)) return HRESULT_FROM_WIN32(GetLastError());
    ret=RegCreateKeyExW(HKEY_CURRENT_USER,L"Software\\Classes\\CLSID\\{7C8B3F91-6F72-4C5B-A60F-2E895AB143D2}\\InprocServer32",0,NULL,0,KEY_WRITE|KEY_WOW64_64KEY,NULL,&key,NULL);
    if(ret) return HRESULT_FROM_WIN32(ret);
    ret=RegSetValueExW(key,NULL,0,REG_SZ,(BYTE*)path,(lstrlenW(path)+1)*sizeof(WCHAR));
    if(!ret) ret=RegSetValueExW(key,L"ThreadingModel",0,REG_SZ,(BYTE*)L"Both",sizeof(L"Both"));
    RegCloseKey(key);return HRESULT_FROM_WIN32(ret);
}
__declspec(dllexport) HRESULT WINAPI DllUnregisterServer(void)
{
    WCHAR path[32768],installed[32768];DWORD size=sizeof(installed);LONG ret;
    const WCHAR *key=L"Software\\Classes\\CLSID\\{7C8B3F91-6F72-4C5B-A60F-2E895AB143D2}";
    if(!GetModuleFileNameW(module,path,32768)) return E_FAIL;
    ret=RegGetValueW(HKEY_CURRENT_USER,L"Software\\Classes\\CLSID\\{7C8B3F91-6F72-4C5B-A60F-2E895AB143D2}\\InprocServer32",NULL,RRF_RT_REG_SZ,NULL,installed,&size);
    if(ret==ERROR_FILE_NOT_FOUND) return S_OK;
    if(ret || lstrcmpiW(path,installed)) return S_FALSE;
    return HRESULT_FROM_WIN32(RegDeleteTreeW(HKEY_CURRENT_USER,key));
}
