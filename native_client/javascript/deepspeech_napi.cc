#include "deepspeech_napi.h"

napi_value Init(napi_env env, napi_value exports) {
  return DeepSpeechNAPI::Init(env, exports);
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
