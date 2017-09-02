# bioreactor
Automated bioreactor for bacteria growth.

See https://blog.krastanov.org/2016/11/15/bioreactor/ for pictures and description.

## Design notes

- The code assumes the existence of a single reactor, hence numerous global
  variables (`reactor` of class `Reactor`, `db` as an `sqlite3 connection`
  object, `calibration` as a `json dict`, etc.) spread over submodules
  (`reactor`, `database`, `calibration`, etc.). The number of wells is hard
  coded (maybe it will move to `calibration` in the distant future).

- Three threads are created: the scheduler from submodule `scheduler`; the web
  interface from submodule `web`; the temperature control in `reactor`. The web
  interface talks to the scheduler from a single location. The scheduler does
  not talk to anybody.

- An `sqlite` on-disk database is used by most threads. Threads access the
  database for reading and writing, relying only on `sqlite`'s internal locks.
  No optimizations of disk access are done (might lead to wear of flash-based
  drives).

- The templating for the web UI is rudimentary, relying only on `str.format`.
  The navigation toolbar is hardcoded.

- Not much attention is paid to encoding url parameters. Non ASCII parameters
  are not guaranteed to work. Special symbols might explode. More testing
  necessary.

- Temperature control is done with a PID loop in a separate (third) thread.
  Some protection and resets through `usbdevicesfs` is enabled (requires the
  compilation of `usbreset.c`) in the case of a hangup. Additional watchdogs
  are possible in the Arduino, but are not currently enabled.

- Proper database normalization would be to have a single table with data
  measurements with a column dedicated to measurement type, but the more naive
  approach with multiple tables (one per measurement type) is good enough for
  this simple project.
