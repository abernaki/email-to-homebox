# Testing Guide

## Safe first-stage pipeline

Run the synthetic extraction-to-mapping test:

```bash
python -m unittest tests.test_safe_pipeline tests.test_model_evaluation -v
```

The test supplies synthetic email data, stubs extraction, and uses a fake Homebox client. It does not load a model, access IMAP, write to Homebox, or persist a receipt.

Run the mocked Homebox v0.26.2 entities API contract tests with only Python's standard test runner:

```bash
python -m unittest tests.test_homebox_entities -v
```

These tests mock every Homebox HTTP call and cover entity create/update, paginated location and item reads, tag compatibility, and multipart attachment uploads. They do not require credentials or a live service.

The daemon and one-shot mailbox processor refuse to start unless `--live` is supplied. The flag enables IMAP reads, mailbox moves, and Homebox writes. `run_dry_run.py` remains isolated from both integrations.

To evaluate the configured pipeline with an existing Ollama model against the synthetic receipt:

```bash
python run_dry_run.py \
  --input tests/fixtures/synthetic_receipt.json \
  --ollama-url http://localhost:11434 \
  --model qwen2.5:14b
```

This command reads only the supplied JSON and YAML config. It contacts the explicitly supplied Ollama endpoint for `/api/tags` and `/api/chat`, then prints extraction results and mapped payloads. It never initializes the email fetcher or Homebox client. The default `DRY_RUN_LOCATION_ID` is only a payload placeholder; pass `--location-id` to preview a different value. Use synthetic or sanitized content because the receipt text is sent to the selected Ollama server.

For a serial comparison of selected installed model tags on the same checked-in synthetic receipt:

```bash
python run_model_evaluation.py \
  --ollama-url http://localhost:11434 \
  --models qwen2.5:14b qwen3:14b phi4:14b gemma4:12b
```

This reports correctness for the known store, order ID/date, receipt total, and line item, plus client wall time and Ollama load/prompt/generation durations and token counts when returned. Client wall time is seconds; Ollama durations are nanoseconds. Each tag is evaluated in order; the script does not access IMAP or Homebox and does not change Ollama's `keep_alive` behavior. Ollama may keep earlier models loaded according to its normal policy, so choose a small model list and run only when the shared host has capacity. No benchmarks are run automatically.

To request CPU-only execution for every request, add `--num-gpu 0`. Omitting the option leaves placement to the Ollama server (which may use its configured GPU, but does not guarantee P100 use); the comparison does not itself identify which physical device handled inference. Ollama documents per-request `options` on `/api/chat`; its current source maps `num_gpu: 0` to CPU-only execution ([API](https://docs.ollama.com/api/chat), [types.go](https://github.com/ollama/ollama/blob/main/api/types.go), [llama_server.go](https://github.com/ollama/ollama/blob/main/llm/llama_server.go), [sched.go](https://github.com/ollama/ollama/blob/main/server/sched.go)). Confirm the installed server version accepts this option before a user-initiated evaluation.

Possible statuses are `ready_for_review`, `low_confidence`, `manual_review`, `no_items`, and `extraction_failed`. A non-ready result does not include mapped items.

## Running other tests

The repository also contains legacy tests and utilities that are not safe substitutes for the isolated test above:

- Tests marked `slow` instantiate `ReceiptExtractor` and contact the configured Ollama server.
- Email and Homebox scripts/tests may connect to live services. Do not run them unless live integration testing is explicitly intended and the target accounts/instances are disposable or otherwise approved.
- `./run_tests.sh` may include those tests; inspect its selected markers before running it.

## Current implementation and later integration

Despite the legacy `src/receipt_extractor_mlx.py` filename and older MLX references in the repository, the checked-in extractor uses Ollama's HTTP API. `OLLAMA_HOST` and `AI_MODEL` select its endpoint and model. Ollama was selected here because it is the existing implementation and the user's homelab already runs it, not because MLX is categorically unsupported on x86. Current MLX docs include Linux CPU and CUDA backends; Tesla P100 compatibility and performance have not been validated for this project.

The client supports `HOMEBOX_API_KEY` as a bearer credential and prefers it over the username/password fallback. Homebox v0.26.2 API keys inherit the owning user's full access; they are not endpoint-scoped. Prefer a dedicated service account with only the access the app needs, and create/manage the key manually in Homebox. Never mint keys from this app or put credentials in source, container images, logs, or plaintext manifests.

If an entity is created but its required purchase-details update fails, the Homebox client raises a partial-write error. The receipt processor stops processing that receipt, reports `partial_write` (not success), and moves the source message to the configured manual-review folder so a later mailbox scan cannot create a duplicate automatically. The created entity ID is returned in the processing result for reconciliation.

Homebox v0.26.2 removed the item and location routes in favor of the unified entities API. The client now uses `/api/v1/entities` (`isLocation=true` for location search), `parentId` for an item's parent, `/api/v1/entities/{id}/attachments`, and `/api/v1/tags` for the former label behavior. Its full entity updates are based on the fetched/created entity so unrelated purchase, warranty, tag, and entity fields are retained. Reference: [Homebox Entity Merge API Migration Guide](https://github.com/sysadminsmedia/homebox/blob/v0.26.2/docs/src/content/docs/en/advanced/entity-merge-upgrade.mdx).

## Deployment contract and remaining work

The Docker image is configured to start the live daemon (`python src/app.py --live`). The one-shot command is `python run_once.py --live`; both are intentionally explicit opt-ins because they read/move mailbox messages and may write Homebox items. The isolated synthetic tests and `run_dry_run.py` do not enable live processing. Docker image publication and any fork/registry setup remain external deployment steps.

For a future Kubernetes integration, keep credentials in an External Secrets Operator (ESO)-backed Secret and inject these exact application environment keys: `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, and `HOMEBOX_API_KEY`. `EMAIL_PASSWORD` is the IMAP app password; `HOMEBOX_API_KEY` should be a dedicated service-account key. Do not create or rotate keys automatically from this repository. Non-secret settings include `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `HOMEBOX_URL`, `OLLAMA_HOST`, `AI_MODEL`, `CHECK_INTERVAL`, and `MIN_CONFIDENCE`; mount `config/config.yml` read-only and persist only the intended `data/` directories.

Keep any scheduled job suspended until image publication, secret injection, endpoint egress, and a human-reviewed test plan are ready. A scheduled one-shot job should run `python run_once.py --live`, not the daemon. `OLLAMA_HOST` must be an address routable and allowed from inside the pod/container; `localhost` refers to that same pod/container, not the Ollama host. Confirm access to Ollama, Homebox, and the IMAP host/port in the deployment network policy. The CPU-only evaluation option is `--num-gpu 0`; otherwise Ollama uses its normal placement policy, which may use the shared P100.

If a later deployment is integrated through a separate `lab-manifests` repository, keep the contract to configuration and secret references:

- Inject `OLLAMA_HOST` as an address reachable from the application container and `AI_MODEL` as an already-installed Ollama model tag.
- Inject `HOMEBOX_URL`; provide `HOMEBOX_API_KEY` through a secret reference (or use username/password only as a legacy fallback).
- Provide IMAP address, port, username, and app password through secret-backed environment variables; do not enable mailbox polling in the local dry-run.
- Mount `config/config.yml` read-only and persist only the intended `data/` directories.

No `lab-manifests` changes are part of this local test stage.
