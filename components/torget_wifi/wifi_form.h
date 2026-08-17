#ifndef TORGET_WIFI_FORM_H
#define TORGET_WIFI_FORM_H

/*
 * Setupportalens textkvarn: procentavkodning, fältplock ur en
 * formulärkodad kropp och HTML-escape av namn som kommer utifrån.
 *
 * Ren kod utan ESP-IDF, värdtestad i test/run.sh (test_wifi_form.c). Det
 * är HIT den fientliga indatan kommer — ett SSID i luften är någon annans
 * sträng, och en trasig procentsekvens ska ge ett nej, inte en gissning
 * (läxan 2026-08-13: "Upstream data is hostile").
 */

#include <stdbool.h>
#include <stddef.h>

/* Avkodar procentkodning och '+' på plats. false = trasig indata; bufferten
 * är då odefinierad och ska kastas, inte användas halvavkodad. */
bool tg_wifi_url_decode(char *s);

/* Kopierar det avkodade värdet för name ur en formulärkodad kropp.
 * Längden mäts EFTER avkodningen — annars förkastas ett fullängds fält
 * vars tecken råkar behöva kodas. false = fältet saknas eller får inte
 * plats. Kroppen muteras inte. */
bool tg_wifi_form_field(const char *body, const char *name, char *out,
                        size_t cap);

/* Escapar &, <, > och " så ett nätnamn inte kan bryta ut ur portalens
 * HTML. Trunkerar hellre än spiller över; out NUL-termineras alltid. */
void tg_wifi_html_escape(const char *in, char *out, size_t cap);

#endif
