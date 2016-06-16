# bioreactor
Automated bioreactor for bacteria growth.

## Design notes

- The code assumes the existence of a single reactor, hence numerous global
  variables (`reactor` of class `Reactor`, `db` as an `sqlite3 connection`
  object, `calibration` as a `json dict`, etc.) spread over submodules
  (`reactor`, `database`, `calibration`, etc.). The number of wells is hard
  coded (maybe it will move to `calibration` in the distant future).

- Three threads are created: the scheduler from submodule `scheduler`; the web
  interface from submodule `web`; the temperature control. The web interface
  talks to the scheduler from a single location. The scheduler does not talk to
  anybody.

- An `sqlite` on-disk database is used by most threads. Both threads access the
  database for reading and writing, relying only on `sqlite`'s internal locks.
  No optimizations of disk access are done (might lead to wear of flash-based
  drives).

- The templating for the web UI is rudimentary, relying only on `str.format`.
  The navigation toolbar is hardcoded.

- Not much attention is paid to encoding url parameters. Non ASCII parameters
  are not guaranteed to work.

- Temperature control is done with a PID loop in a separate (third) thread. It
  relies on `nanpy` for properly locking the serial connection resource to the
  Arduino controller.
