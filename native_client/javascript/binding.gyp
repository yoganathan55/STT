{
  "targets": [
    {
      "target_name": "deepspeech",
      "cflags!": [ "-fno-exceptions" ],
      "cflags_cc!": [ "-fno-exceptions" ],
      "xcode_settings": { "GCC_ENABLE_CPP_EXCEPTIONS": "YES",
        "CLANG_CXX_LIBRARY": "libc++",
        "MACOSX_DEPLOYMENT_TARGET": "10.7",
      },
      "msvs_settings": {
        "VCCLCompilerTool": { "ExceptionHandling": 1 },
      },
      "sources": [ "deepspeech_napi.cc", "deepspeech_napi_impl.cc" ],
      "libraries": [
        "$(LIBS)"
      ],
      "include_dirs": [
        "<!@(node -p \"require('node-addon-api').include\")",
        "../"
      ],
      "conditions": [
        [ "OS=='mac'", {
            "xcode_settings": {
              "OTHER_CXXFLAGS": [
                "-stdlib=libc++",
                "-mmacosx-version-min=10.10"
              ],
              "OTHER_LDFLAGS": [
                "-stdlib=libc++",
                "-mmacosx-version-min=10.10"
              ]
            }
          }
        ]
      ]
    },
    {
      "target_name": "action_after_build",
      "cflags!": [ "-fno-exceptions" ],
      "cflags_cc!": [ "-fno-exceptions" ],
      "xcode_settings": { "GCC_ENABLE_CPP_EXCEPTIONS": "YES",
        "CLANG_CXX_LIBRARY": "libc++",
        "MACOSX_DEPLOYMENT_TARGET": "10.7",
      },
      "msvs_settings": {
        "VCCLCompilerTool": { "ExceptionHandling": 1 },
      },
      "type": "none",
      "dependencies": [ "<(module_name)" ],
      "copies": [
        {
          "files": [ "<(PRODUCT_DIR)/<(module_name).node" ],
          "destination": "<(module_path)"
        }
      ]
    }
  ],
  "variables": {
    "build_v8_with_gn": 1,
    "v8_enable_pointer_compression": 0,
    "v8_enable_31bit_smis_on_64bit_arch": 0,
    "enable_lto": 0
  },
}
