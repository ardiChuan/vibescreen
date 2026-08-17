# Glance-mönstrets HTTP-klient: en begränsad GET, hela kroppen eller
# ingenting — nu med reläet som reservväg när LAN:et inte går att nå.
# net_source_policy är den rena kärnan och värdtestas i test/run.sh.
idf_component_register(
  SRCS "torget_http.c" "net_source_policy.c"
  INCLUDE_DIRS "."
  PRIV_REQUIRES esp_http_client esp-tls esp_timer)
