[app]
title = Synthex
package.name = synthex
package.domain = com.yohn18.synthex

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 1.0.0

requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.ndk_path =
android.sdk_path =
android.accept_sdk_license = True
android.arch = arm64-v8a

android.presplash_color = #0a0a0f
android.icon.filename = %(source.dir)s/icon.png

log_level = 2
warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
