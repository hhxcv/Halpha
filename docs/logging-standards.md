# Logging Standards

Halpha writes local JSON-lines logs for operational diagnosis. Logs support
daily validation, bug reproduction, and local issue investigation. They do not
replace run manifests, command job records, monitor artifacts, product
validation, or source artifacts.

Default runtime logs are written to `logs/halpha.log` under the current working
directory. `logging.output_dir` may choose a different local log directory; a
relative value still resolves from the current working directory, not from the
config file location. Log rotation keeps bounded local files. Logs are local
artifacts and are not telemetry.

## Privacy Boundary

Logs must not include:

- credentials, tokens, cookies, proxy values, private endpoints, account
  identifiers, wallet addresses, private user-state values, raw local notes, or
  exact holdings;
- raw market streams, raw RSS bodies, raw on-chain payloads, full reusable
  histories, full SQLite contents, full Parquet contents, full Codex prompts,
  or full report text;
- absolute local paths, config file contents, machine hostnames, usernames, or
  ports.

Use stable references instead:

- `run_id`;
- `stage`;
- `job_id`;
- `cycle_id`;
- `loop_id`;
- `intent`;
- `status`;
- bounded artifact refs such as `analysis/risk_assessment.json`;
- bounded external placeholders such as `<external-artifact>` or
  `<external-config>` when a local path is outside the runtime root;
- counts, booleans, configured option names, and enum-like state values.

Logging configuration redacts configured private values and config-local paths.
Callers must still avoid putting unnecessary private values in log messages or
`extra` fields.

## Levels

Use `DEBUG` for high-volume lifecycle details that are useful during focused
debugging but too noisy for normal daily logs:

- individual pipeline stage start and success;
- compact branch decisions inside a single command when they do not indicate
  user-visible state changes;
- bounded diagnostic counters while investigating a specific path.

Use `INFO` for normal user-visible lifecycle events:

- CLI command start and success;
- pipeline run start and success;
- explicit single-stage pipeline start and success;
- command job queued, start, and success;
- monitor cycle or finite loop start and success;
- explicit skip or not-run summaries caused by user options such as
  `--no-codex` or `--until`;
- local service start and graceful stop.

Use `WARNING` for bounded recoverable or expected failure states:

- CLI command failure caused by config, validation, unsupported input, or
  completed command result with non-zero exit code;
- command job rejection, blocked state, cancellation, or process exit with a
  non-zero code;
- monitor cycle or loop failure where the product still wrote monitor
  artifacts;
- collector/source unavailability when the product records a partial artifact
  and can continue or report a bounded failure.

Use `ERROR` for unexpected or terminal failures that need investigation:

- pipeline stage failure;
- unhandled exception boundaries after redaction and bounded diagnostics;
- command job process start failure;
- local service startup/runtime failure.

Do not use `ERROR` for ordinary unavailable public data when the artifact
contract already records a warning, partial state, or bounded collection error.

## Event Shape

Log records use JSON objects. Every product log should include:

- `event`: stable dotted event name;
- `level`;
- `logger`;
- `message`;
- enough bounded context to correlate the event.

Common event names:

- `cli.command.start`;
- `cli.command.succeeded`;
- `cli.command.failed`;
- `pipeline.run.start`;
- `pipeline.run.succeeded`;
- `pipeline.stage.start`;
- `pipeline.stage.succeeded`;
- `pipeline.stage.skipped`;
- `pipeline.stage.failed`;
- `pipeline.stages.not_run`;
- `collector.<name>.start`;
- `collector.<name>.finished`;
- `collector.<name>.skipped`;
- `collector.<name>.failed`;
- `command_job.queued`;
- `command_job.start`;
- `command_job.finished`;
- `monitor.cycle.start`;
- `monitor.cycle.finished`;
- `monitor.loop.start`;
- `monitor.loop.finished`.

Common context fields:

- CLI: `command`, `stage`, `status`, `exit_code`, `reason`;
- pipeline: `run_id`, `stage`, `artifact_count`, `skip_codex`,
  `until_stage`;
- collectors: `stage`, `source`, `status`, `symbol_count`, `item_count`,
  `error_count`, `artifact`;
- command jobs: `job_id`, `intent`, `kind`, `status`, `exit_code`;
- monitor service: `service_id`, `status`, `heartbeat_at`,
  `consecutive_failures`, `stop_reason`;
- legacy monitor diagnostics: `cycle_id`, `loop_id`, `run_id`,
  `target_stage`, `no_codex`, `completed_cycles`, `stop_reason`;
- validation and inspection commands: `status`, `explicit_run`.

## Anti-Noise Rules

- Do not log per market record, per candle, per RSS item, per row, per alert
  archive line, or per reusable history record.
- Do not log raw request or response bodies.
- Do not log full artifact JSON or Markdown content.
- Prefer one lifecycle record per command/job/cycle and DEBUG records for
  repeated stage-level detail.
- Prefer counts and status summaries over lists. If a list is needed, keep it
  bounded and made of public artifact refs or stable IDs.
- Repeated finite loops should log loop start/finish and cycle finish, not every
  idle wait unless the wait itself is the issue being debugged.

## Compatibility

Logs are operational evidence only. They are not product state contracts and
must not become the source of truth for reports, dashboard state, monitor
health, validation, cleanup decisions, or strategy decisions.
