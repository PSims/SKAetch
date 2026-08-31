# SKAetch: An interactive SKA-Low radio interferometry outreach simulator

Explore interferometric imaging with staged SKA-Low configurations, including
interactive radio portraits.

SKAetch includes frozen station geometries for five staged SKA-Low
configurations: AA0.5, AA1, AA2, AA* and AA4.  See
[`docs/array_geometry.md`](docs/array_geometry.md) for their source, validation
and reproduction workflow.

## Run the live exhibit

```bash
uv run skaetch
```

The application runs only on the local computer and opens a browser interface.
Camera captures are processed in memory and are not saved by SKAetch.  A bundled
Einstein portrait provides a non-camera route through the activity.

The default visitor progression is:

```text
AA1 snapshot → AA1 6 h → AA2 6 h → AA* 6 h → AA4 6 h
```

See [`docs/live_exhibit.md`](docs/live_exhibit.md) for runtime details and
[`docs/facilitator_runbook.md`](docs/facilitator_runbook.md) for the suggested
event flow.
