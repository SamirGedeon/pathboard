# Architecture decisions

## Separate the graph from persistence

`backend/pathboard/planning.py` contains the request models and deterministic planner. `store.py` handles authentication and SQLite persistence. `main.py` wires FastAPI routes, response models, cookie authentication and request boundaries. The Vue application presents saved calculations rather than duplicating scheduling rules in JavaScript.

A task has a stable ID, a title, an integer estimate and prerequisite IDs. A complete project graph is validated before it can be persisted. Unknown dependencies, repeated prerequisites, duplicate IDs, self-links and cycles are invalid. The 60-task limit bounds request size and planner work.

## Critical-path method

Kahn's topological algorithm uses a heap of ready IDs to provide deterministic ordering, even if an equivalent request presents its tasks in another order. The forward pass calculates:

- earliest start = maximum finish of prerequisite tasks, or zero;
- earliest finish = earliest start + estimated hours.

The project duration is the maximum earliest finish. The backward pass starts from that finish and calculates each task's latest start from its successors. Slack is latest start minus earliest start. All zero-slack tasks are critical, including equal-length parallel branches.

Disconnected tasks share the project finish as their latest finish. This produces meaningful slack for work outside the longest branch. Empty projects have zero duration, effort and critical tasks.

This is an unlimited-resource, finish-to-start model with no calendar. The planner does not claim to solve staffing, working-time allocation or uncertain delivery forecasts.

## Saved state and simulations

A project is saved as one validated snapshot with an integer version. An update starts `BEGIN IMMEDIATE` and performs a conditional update scoped to project ID, owner ID and submitted version. Exactly one competing writer can advance a version. The saved row is read inside the transaction, so the response represents that mutation's snapshot.

Validation failure performs no writes. A stale update returns 409; another account's project returns 404. The browser offers “Reload latest” to resolve a stale local copy. Because updates are version guarded rather than idempotency keyed, a retry after an ambiguous successful response can return 409; read the latest saved project before retrying.

Simulations load the current owned snapshot, check its version, change one estimate in memory and recalculate. They do not update the database, version or timestamps. Saving a task change clears any previous simulation so it cannot appear to describe the new saved graph.

## SQLite and connections

Every operation opens and closes its own SQLite connection. Foreign keys are enabled, WAL is configured on initialization and connections use a five-second busy timeout. Short explicit transactions serialize writes. Parameterized SQL is used for values.

This is a single-instance design. SQLite files must live on persistent local storage. The project has an idempotent schema initializer but no migration framework or snapshot-history system.

## Authentication and HTTP boundary

Passwords use `hashlib.scrypt` with per-account random salts. Login uses constant-time hash comparison; missing-account attempts also perform a hash calculation. Session tokens contain 256 random bits; only token digests are stored. Expiration is checked on every authenticated request; logout removes the session row.

Pydantic validates both requests and project/simulation responses. The generated OpenAPI schema includes these models and cookie authentication. JSON mutation bodies are read with a 64 KiB cap, extra fields are rejected, and validation output excludes submitted inputs. Origin checks and SameSite cookies protect browser mutations. Non-browser clients may omit Origin but still need a valid session.

Authentication throttling is process-local and uses the direct client address. The provided uvicorn commands disable forwarded proxy headers so an untrusted client cannot choose a limiter identity through a header. Set a deliberate trust policy and shared rate limit before scaling behind proxies.

## Frontend

Vue refs hold form and workspace state; computed values derive project counts and search results. The server is authoritative for graph validity, schedule values and version checks. Task text is rendered using escaped Vue interpolation.

The timeline uses CSS bars with textual labels and accessible descriptions. Forms use visible labels, native number constraints, fieldsets and checkboxes. Status and error messages use live regions. Playwright checks narrow-layout overflow and real keyboard-compatible native form interactions. No formal accessibility audit has been performed.
