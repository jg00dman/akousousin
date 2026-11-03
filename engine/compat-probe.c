/* SPDX-License-Identifier: LGPL-2.1-or-later */
#define COBJMACROS
#include <windows.h>
#include <initguid.h>
#include <sapi.h>
#include <stdio.h>
#include <string.h>
static const CLSID data_key_clsid={0xd9f6ee60,0x58c9,0x458b,{0x88,0xe1,0x2f,0x90,0x8f,0xd7,0xf8,0x7c}};
int main(int argc,char **argv)
{
    ISpRegDataKey *data=NULL;HKEY key;WCHAR path[128],*name=NULL;HRESULT hr;LONG error;
    if(argc==2 && !strcmp(argv[1],"--engine"))
    {
        const CLSID engine={0xea7a00ab,0x0fb7,0x4deb,{0x81,0xc5,0x55,0x0d,0x85,0x4f,0x39,0x0f}};
        IUnknown *object=NULL;
        CoInitializeEx(NULL,COINIT_MULTITHREADED);
        hr=CoCreateInstance(&engine,NULL,CLSCTX_INPROC_SERVER,&IID_IUnknown,(void**)&object);
        if(object)IUnknown_Release(object);
        CoUninitialize();
        printf("OpenSAPI engine activation: %#lx\n",hr);
        return SUCCEEDED(hr)?0:2;
    }
    swprintf(path,128,L"Software\\OpenSAPI\\Probe-%lu-%lu",GetCurrentProcessId(),GetTickCount());
    CoInitializeEx(NULL,COINIT_MULTITHREADED);
    error=RegCreateKeyExW(HKEY_CURRENT_USER,path,0,NULL,0,KEY_ALL_ACCESS,NULL,&key,NULL);
    if(error)return 2;
    RegSetValueExW(key,L"Test",0,REG_SZ,(BYTE*)L"value",sizeof(L"value"));
    hr=CoCreateInstance(&data_key_clsid,NULL,CLSCTX_INPROC_SERVER,&IID_ISpRegDataKey,(void**)&data);
    if(SUCCEEDED(hr))hr=ISpRegDataKey_SetKey(data,key,FALSE);
    if(SUCCEEDED(hr))hr=ISpRegDataKey_EnumValues(data,0,&name);
    if(name)CoTaskMemFree(name);
    if(data)ISpRegDataKey_Release(data);else RegCloseKey(key);
    RegDeleteTreeW(HKEY_CURRENT_USER,path);CoUninitialize();
    printf("SAPI EnumValues result: %#lx\n",hr);
    return hr==S_OK?0:hr==E_NOTIMPL?1:2;
}
