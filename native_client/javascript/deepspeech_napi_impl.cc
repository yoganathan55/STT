#include <assert.h>
#include <string.h>
#include <stdlib.h>

#include <iostream>

#include "deepspeech_napi.h"
#include "deepspeech.h"

napi_ref DeepSpeechNAPI::constructor;

DeepSpeechNAPI::DeepSpeechNAPI()
    : env_(nullptr), wrapper_(nullptr) {}

DeepSpeechNAPI::~DeepSpeechNAPI() {
  napi_delete_reference(env_, wrapper_);
}

void DeepSpeechNAPI::Destructor(napi_env env,
                          void* nativeObject,
                          void* /*finalize_hint*/) {
  reinterpret_cast<DeepSpeechNAPI*>(nativeObject)->~DeepSpeechNAPI();
}

#define DECLARE_NAPI_METHOD(name, func)                                        \
  { name, 0, func, 0, 0, 0, napi_default, 0 }

#define SIZEOF(a) ( sizeof a / sizeof a[0] )

napi_value DeepSpeechNAPI::Init(napi_env env, napi_value exports) {
  napi_status status;
  napi_property_descriptor properties[] = {
      DECLARE_NAPI_METHOD("CreateModel", CreateModel),
      DECLARE_NAPI_METHOD("GetModelSampleRate", GetModelSampleRate),
      DECLARE_NAPI_METHOD("SpeechToText", SpeechToText),
      DECLARE_NAPI_METHOD("FreeModel", FreeModel),
      DECLARE_NAPI_METHOD("Version", Version),
  };

  napi_value cons;
  status = napi_define_class(
      env, "DeepSpeechNAPI", NAPI_AUTO_LENGTH, New, nullptr, SIZEOF(properties), properties, &cons);
  assert(status == napi_ok);

  status = napi_create_reference(env, cons, 1, &constructor);
  assert(status == napi_ok);

  status = napi_set_named_property(env, exports, "DeepSpeechNAPI", cons);
  assert(status == napi_ok);
  return exports;
}

napi_value DeepSpeechNAPI::New(napi_env env, napi_callback_info info) {
  napi_status status;

  napi_value target;
  status = napi_get_new_target(env, info, &target);
  assert(status == napi_ok);
  bool is_constructor = target != nullptr;

  if (is_constructor) {
    // Invoked as constructor: `new DeepSpeechNAPI(...)`
    size_t argc = 1;
    napi_value args[1];
    napi_value jsthis;
    status = napi_get_cb_info(env, info, &argc, args, &jsthis, nullptr);
    assert(status == napi_ok);

    double value = 0;

    napi_valuetype valuetype;
    status = napi_typeof(env, args[0], &valuetype);
    assert(status == napi_ok);

    if (valuetype != napi_undefined) {
      status = napi_get_value_double(env, args[0], &value);
      assert(status == napi_ok);
    }

    DeepSpeechNAPI* obj = new DeepSpeechNAPI();

    obj->env_ = env;
    status = napi_wrap(env,
                       jsthis,
                       reinterpret_cast<void*>(obj),
                       DeepSpeechNAPI::Destructor,
                       nullptr,  // finalize_hint
                       &obj->wrapper_);
    assert(status == napi_ok);

    return jsthis;
  } else {
    // Invoked as plain function `DeepSpeechNAPI(...)`, turn into construct call.
    size_t argc_ = 1;
    napi_value args[1];
    status = napi_get_cb_info(env, info, &argc_, args, nullptr, nullptr);
    assert(status == napi_ok);

    const size_t argc = 1;
    napi_value argv[argc] = {args[0]};

    napi_value cons;
    status = napi_get_reference_value(env, constructor, &cons);
    assert(status == napi_ok);

    napi_value instance;
    status = napi_new_instance(env, cons, argc, argv, &instance);
    assert(status == napi_ok);

    return instance;
  }
}

napi_value DeepSpeechNAPI::CreateModel(napi_env env, napi_callback_info info) {
  napi_status status;

  size_t argc = 1;
  napi_value args[1];
  napi_value jsthis;
  status = napi_get_cb_info(env, info, &argc, args, &jsthis, nullptr);
  assert(status == napi_ok);

  napi_valuetype valuetype;
  status = napi_typeof(env, args[0], &valuetype);
  assert(status == napi_ok);

  size_t num;
  char* modelPath = (char*)malloc(sizeof(char)*1024);
  status = napi_get_value_string_utf8(env, args[0], modelPath, 1024, &num);
  assert(status == napi_ok);

  napi_value array_rc, modelState, modelRv;

  status = napi_create_array(env, &array_rc);
  assert(status == napi_ok);

  ModelState *aCtx;
  int rv = DS_CreateModel(modelPath, &aCtx);

  status = napi_create_int32(env, rv, &modelRv);
  assert(status == napi_ok);
  
  int64_t ptr = reinterpret_cast<int64_t>(aCtx);
  status = napi_create_int64(env, ptr, &modelState);
  assert(status == napi_ok);
  std::cerr << __PRETTY_FUNCTION__ << " ModelSate: " << aCtx << std::endl;
  std::cerr << __PRETTY_FUNCTION__ << " ModelSate(int64_t): " << ptr << std::endl;

  status = napi_set_element(env, array_rc, 0, modelRv);
  assert(status == napi_ok);

  status = napi_set_element(env, array_rc, 1, modelState);
  assert(status == napi_ok);

  free(modelPath);

  return array_rc;
}

napi_value DeepSpeechNAPI::SpeechToText(napi_env env, napi_callback_info info) {
  napi_status status;

  size_t argc = 2;
  napi_value args[2];
  napi_value jsthis;
  status = napi_get_cb_info(env, info, &argc, args, &jsthis, nullptr);
  assert(status == napi_ok);

  napi_valuetype ptr_impl_type;
  status = napi_typeof(env, args[0], &ptr_impl_type);
  assert(status == napi_ok);

  napi_valuetype buffer_type;
  status = napi_typeof(env, args[1], &buffer_type);
  assert(status == napi_ok);

  int64_t ptr;
  status = napi_get_value_int64(env, args[0], &ptr);
  assert(status == napi_ok);
  ModelState *aCtx = reinterpret_cast<ModelState*>(ptr);
  std::cerr << __PRETTY_FUNCTION__ << " ModelSate(int64_t): " << ptr << std::endl;
  std::cerr << __PRETTY_FUNCTION__ << " ModelSate: " << aCtx << std::endl;

  const short* aBuffer;
  size_t aBufferSize;
  status = napi_get_buffer_info(env, args[1], (void**)&aBuffer, &aBufferSize);
  assert(status == napi_ok);

  napi_value js_str_ver;
  const char* inference = DS_SpeechToText(aCtx, aBuffer, aBufferSize / 2);
  status = napi_create_string_utf8(env, inference, strlen(inference), &js_str_ver);
  assert(status == napi_ok);

  return js_str_ver;
}

napi_value DeepSpeechNAPI::GetModelSampleRate(napi_env env, napi_callback_info info) {
  napi_status status;

  napi_value jsthis;
  status = napi_get_cb_info(env, info, nullptr, nullptr, &jsthis, nullptr);
  assert(status == napi_ok);

  napi_value sample_rate;
  status = napi_create_int32(env, 16000, &sample_rate);
  assert(status == napi_ok);

  return sample_rate;
}

napi_value DeepSpeechNAPI::Version(napi_env env, napi_callback_info info) {
  napi_status status;

  napi_value jsthis;
  status = napi_get_cb_info(env, info, nullptr, nullptr, &jsthis, nullptr);
  assert(status == napi_ok);

  napi_value js_str_ver;
  const char* ds_ver = DS_Version();
  status = napi_create_string_utf8(env, ds_ver, strlen(ds_ver), &js_str_ver);
  assert(status == napi_ok);

  return js_str_ver;
}

napi_value DeepSpeechNAPI::FreeModel(napi_env env, napi_callback_info info) {
  napi_status status;

  napi_value jsthis;
  status = napi_get_cb_info(env, info, nullptr, nullptr, &jsthis, nullptr);
  assert(status == napi_ok);

  napi_value free_model;
  status = napi_create_int32(env, 0, &free_model);
  assert(status == napi_ok);

  return free_model;
}
