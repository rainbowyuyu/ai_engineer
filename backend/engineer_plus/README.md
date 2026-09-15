# AI Engineer Plus

Review evidence: the five-dimensional numerical scores are deterministic rules.
An optional Qwen call explains failed/warning rules; it is not an independent
engineering assessment and does not change the score. `rationale_review.json`
and `validation_score.json` retain per-rule model/template sources, attempted
and successful calls, model identifiers and prompt/text hashes. Provider errors,
empty/truncated responses and missing credentials remain explicit template
fallbacks. `mixed` means some findings received a model response and others did
not. Markdown/Word reports label each explanation's source. These provenance
checks do not demonstrate live model quality or physical solver completion.

`ClosedLoopEngine` is the common protocol shared by all construction families.
The Phase-I parser supplies a `DesignRequest`; a registered construction builder
creates a design-domain artifact, a registered BESO runner creates a topology
artifact, and the existing validation pipeline supplies the review score. The
engine then applies the existing halt gate and selects the highest-scoring
candidate that actually passed it.

The model can propose a structured request and a tool call. It cannot provide a
review score, mark a preview as live, or select a candidate that failed the gate.
Each transition emits an event with a candidate id, and a registry callback can
persist the complete candidate record.

Each `ConstructionAdapter` declares its capabilities, accepted input formats,
required physical inputs, produced artifacts and known limitations. The
`GET /constructions` response exposes these fields together with
`registration_errors`, so an unavailable or failed adapter registration is
observable instead of silently omitted. Natural-language routing is conservative;
an unsupported construction must be supplied through an explicitly registered
adapter and cannot be mapped to a physics workflow by language-model guesswork.

The direct `POST /review-select` path has the same hard selection boundary as a
live run: a candidate must pass the deterministic physical gate, complete a
candidate-level review from a real LLM response, and receive an `accept`
recommendation before its score can be compared with other candidates. Template
explanations, missing credentials and invalid model output are retained as
non-completed review states and cannot authorize selection.

The rule-explanation channel and the candidate-decision channel have distinct
roles. `no_findings` means there are no failed/warning rules to explain and is
allowed only alongside a completed candidate-level LLM response. It never
substitutes for that response. The same check is used by both execution paths.
In direct batch review, an exception in a candidate's reviewer is recorded by
exception class and excludes that candidate while its peers continue. Exclusion
events distinguish incomplete rule explanations from an incomplete candidate
decision and retain returned candidate evidence for diagnosis.

The module is deliberately construction-neutral: OC4, prism, shell, frame and
future builders can implement the same two artifact callbacks. Existing
construction-specific code remains available in `backend/pipeline` and is not
silently replaced by a fixture or canned result.

The built-in `prism` adapter is registered against the repository's real
FreeCAD/Gmsh and CalculiX/BESO functions. It waits for the asynchronous BESO
job to finish and then runs sizing before review. A missing solver, timeout or
failed job is returned as a failed candidate.

The built-in `oc4` adapter reuses the existing OC4 session builder, including
CAD design-domain construction, mesh generation and load partitioning, before
entering the same BESO and review path.

The built-in `cad` adapter accepts a workspace-local IGES/STEP solid and uses
the repository's FreeCAD+Gmsh converter to create the FEM input before BESO.
It requires a real solid and rejects missing, out-of-workspace or undersized
conversion outputs.

The API is mounted under `/api/plus`: `GET /constructions` reports registered
adapters, `POST /run` executes a registered live loop, and
`POST /review-select` reviews already-produced geometry JSON files. The run
endpoint can therefore be used by a UI without bypassing the same gate.

Candidate review now receives measured metrics, per-rule findings, assumptions
and surrogate provenance, and persists the provider response separately as
`candidate_review.json`. Truncated provider responses cannot authorize selection.

The engine connects a completed `revise` decision to an adapter-owned revision
contract, a real model proposal and a new build/solve/review attempt. It rejects
invalid or repeated specifications and retains prior candidates and their
hashed artifacts. Events are checkpointed between stages; errors are recorded
by class. Each execution uses unique attempt and event paths. Exception
recovery can only patch the explicitly permitted numerical settings.

Prism dimensions are locked by default and by the production service, following
the author's instruction. The reusable contract supports explicitly bounded
geometry experiments in controlled tests, but the production prism route
overrides any such search bounds with an empty set. No numeric geometry change
is currently authorized. A failed candidate requiring a geometry change remains
unselected. Fixed-domain topology continuation now validates the original
full-precision mesh hash, exported node coordinates, element connectivity,
complete domain state coverage and protected elements before installing an
element-state checkpoint into an independent run. The only production patch is
`topology_continuation: continue`. Geometry, loads, materials, target fraction
and scoring thresholds remain fixed. The BESO iteration allowance is `auto`;
the model cannot choose it. Sensitivity/history are reset, so this is a warm
start, not exact optimizer replay. A live continuation is in progress; this
contract must not be described as demonstrated convergence or certification.

The legacy CAD route still feeds floating-wind reconstruction, sizing and
validation. Accepting an arbitrary STEP file therefore does not establish a
validated general-purpose structural solver. Dedicated physical evaluators are
required before claiming coverage of other structural families.
