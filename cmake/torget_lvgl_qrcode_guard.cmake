function(torget_require_lvgl_qrcode enabled)
  if(NOT "${enabled}" STREQUAL "y")
    message(FATAL_ERROR
      "LVGL QR support is disabled. The generated sdkconfig is stale: set "
      "CONFIG_LV_USE_QRCODE=y (matching sdkconfig.defaults), then run: "
      "idf.py reconfigure && idf.py build")
  endif()
endfunction()
