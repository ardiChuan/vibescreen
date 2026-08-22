# Wi-Fi setup cleanup design

## Goal

Make phone onboarding self-explanatory without removing the manual recovery
path.

## Panel

The primary 480 x 480 setup state contains only:

- `WIFI SETUP`;
- `SCAN WITH YOUR PHONE`;
- the 196 x 196 Wi-Fi QR code;
- one outlined `MANUAL SETUP` touch target;
- the remaining time and `KEY3 CLOSES` footer.

The temporary SSID, temporary password, and `192.168.4.1` move to the manual
details view. `MANUAL SETUP` opens that view and `BACK TO QR` returns to the
primary view. If QR generation fails, the manual view appears automatically.
Both touch targets are at least 90 px high. Hiding the overlay clears the
temporary password and returns the next opening to the QR view.

## Phone portal

Each scanned network carries its real open/secured classification into the
HTML option. For a secured selection the form says `Password for <SSID>`,
shows the field, and requires 8-63 printable ASCII bytes. For an open selection
the field is hidden and the page says `No password required`.

The firmware repeats the same validation on POST. JavaScript is presentation,
not authority: a missing password for a secured scanned network is rejected,
and a submitted password for an open scanned network is ignored.

## Verification

Regression tests pin both panel views, 480 x 480 layout, touch-target size,
portal copy and secure/open behavior. The shared LVGL captures, full host suite,
simulator build, and a fresh target build are required before requesting a
physical flash.
