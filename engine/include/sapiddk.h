/* LGPL-2.1-or-later. C interface declarations derived from Wine's sapiddk.idl,
 * Copyright (C) 2017 Huw Davies. Standard SAPI DDK binary interfaces only. */
#ifndef OPENSAPI_SAPIDDK_H
#define OPENSAPI_SAPIDDK_H
#include <sapi.h>
typedef enum { SPVST_SENTENCE = 1 } SPVSKIPTYPE;
typedef enum { SPVES_CONTINUE=0, SPVES_ABORT=1, SPVES_SKIP=2, SPVES_RATE=4, SPVES_VOLUME=8 } SPVESACTIONS;
typedef struct ISpTTSEngineSite ISpTTSEngineSite;
typedef struct ISpTTSEngine ISpTTSEngine;
typedef struct SPVTEXTFRAG {
    struct SPVTEXTFRAG *pNext; SPVSTATE State; LPCWSTR pTextStart; ULONG ulTextLen, ulTextSrcOffset;
} SPVTEXTFRAG;
DEFINE_GUID(IID_ISpTTSEngineSite,0x9880499b,0xcce9,0x11d2,0xb5,0x03,0x00,0xc0,0x4f,0x79,0x73,0x96);
DEFINE_GUID(IID_ISpTTSEngine,0xa74d7c8e,0x4cc5,0x4f2f,0xa6,0xeb,0x80,0x4d,0xee,0x18,0x50,0x0e);
typedef struct ISpTTSEngineSiteVtbl {
 HRESULT (STDMETHODCALLTYPE *QueryInterface)(ISpTTSEngineSite*,REFIID,void**);
 ULONG (STDMETHODCALLTYPE *AddRef)(ISpTTSEngineSite*);
 ULONG (STDMETHODCALLTYPE *Release)(ISpTTSEngineSite*);
 HRESULT (STDMETHODCALLTYPE *AddEvents)(ISpTTSEngineSite*,const SPEVENT*,ULONG);
 HRESULT (STDMETHODCALLTYPE *GetEventInterest)(ISpTTSEngineSite*,ULONGLONG*);
 DWORD (STDMETHODCALLTYPE *GetActions)(ISpTTSEngineSite*);
 HRESULT (STDMETHODCALLTYPE *Write)(ISpTTSEngineSite*,const void*,ULONG,ULONG*);
 HRESULT (STDMETHODCALLTYPE *GetRate)(ISpTTSEngineSite*,long*);
 HRESULT (STDMETHODCALLTYPE *GetVolume)(ISpTTSEngineSite*,USHORT*);
 HRESULT (STDMETHODCALLTYPE *GetSkipInfo)(ISpTTSEngineSite*,SPVSKIPTYPE*,long*);
 HRESULT (STDMETHODCALLTYPE *CompleteSkip)(ISpTTSEngineSite*,long);
} ISpTTSEngineSiteVtbl;
struct ISpTTSEngineSite { const ISpTTSEngineSiteVtbl *lpVtbl; };
typedef struct ISpTTSEngineVtbl {
 HRESULT (STDMETHODCALLTYPE *QueryInterface)(ISpTTSEngine*,REFIID,void**);
 ULONG (STDMETHODCALLTYPE *AddRef)(ISpTTSEngine*);
 ULONG (STDMETHODCALLTYPE *Release)(ISpTTSEngine*);
 HRESULT (STDMETHODCALLTYPE *Speak)(ISpTTSEngine*,DWORD,REFGUID,const WAVEFORMATEX*,const SPVTEXTFRAG*,ISpTTSEngineSite*);
 HRESULT (STDMETHODCALLTYPE *GetOutputFormat)(ISpTTSEngine*,const GUID*,const WAVEFORMATEX*,GUID*,WAVEFORMATEX**);
} ISpTTSEngineVtbl;
struct ISpTTSEngine { const ISpTTSEngineVtbl *lpVtbl; };
#define ISpTTSEngine_QueryInterface(p,a,b) ((p)->lpVtbl->QueryInterface(p,a,b))
#define ISpTTSEngine_AddRef(p) ((p)->lpVtbl->AddRef(p))
#define ISpTTSEngine_Release(p) ((p)->lpVtbl->Release(p))
#define ISpTTSEngine_Speak(p,a,b,c,d,e) ((p)->lpVtbl->Speak(p,a,b,c,d,e))
#define ISpTTSEngine_GetOutputFormat(p,a,b,c,d) ((p)->lpVtbl->GetOutputFormat(p,a,b,c,d))
#define ISpTTSEngineSite_GetActions(p) ((p)->lpVtbl->GetActions(p))
#define ISpTTSEngineSite_GetRate(p,a) ((p)->lpVtbl->GetRate(p,a))
#define ISpTTSEngineSite_GetVolume(p,a) ((p)->lpVtbl->GetVolume(p,a))
#define ISpTTSEngineSite_Write(p,a,b,c) ((p)->lpVtbl->Write(p,a,b,c))
#endif
