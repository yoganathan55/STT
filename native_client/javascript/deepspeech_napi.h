#ifndef DEEPSPEECH_NAPI_H
#define DEEPSPEECH_NAPI_H

#include <node_api.h>

class DeepSpeechNAPI {
 public:
  static napi_value Init(napi_env env, napi_value exports);
  static void Destructor(napi_env env, void* nativeObject, void* finalize_hint);

 private:
  explicit DeepSpeechNAPI();
  ~DeepSpeechNAPI();

  static napi_value New(napi_env env, napi_callback_info info);
  static napi_value CreateModel(napi_env env, napi_callback_info info);
  static napi_value GetModelSampleRate(napi_env env, napi_callback_info info);
  static napi_value SpeechToText(napi_env env, napi_callback_info info);
  static napi_value FreeModel(napi_env env, napi_callback_info info);
  static napi_value Version(napi_env env, napi_callback_info info);
  static napi_ref constructor;
  napi_env env_;
  napi_ref wrapper_;
};

#endif  // DEEPSPEECH_NAPI_H
