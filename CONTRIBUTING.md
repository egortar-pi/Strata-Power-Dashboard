# Contributing

Issues and pull requests are welcome. Please include your Ubuntu version, Python version, `nvidia-smi` output with sensitive details removed, and a redacted sample of the Strata `/metrics` schema when reporting an integration problem.

Run tests with `python3 -m unittest discover -s tests -v` and check syntax with `python3 -m py_compile app.py`.

Avoid committing credentials, SQLite databases, identifiable hostnames, local monitoring data, or tokens. Keep dependencies minimal and document changes to the SQLite schema.
