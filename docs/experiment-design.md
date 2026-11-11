# Experiment design

## Collaboration and computation

Independent and exchange modes differ only in peer-message delivery. Their worker counts, rounds, and final selector match.

Leader mode also changes roles, worker count, coordination calls, and final submission. It is a bundled architecture comparison.

Solo-budget supplies a longer single-agent baseline under the same resource ceilings. It does not force exact token matching.

Use observed quality-versus-token curves for comparisons. Equal ceilings do not establish an exact fixed-compute experiment.

Each call receives the public task and its own previous response. Older full histories are not retained.

Exchange also receives prior-round peer summaries. The leader receives current worker candidates and summaries.

Workers receive the leader's current schedule, summary, and their assigned instruction. Round barriers control visibility.

## Selection

Public-checker ranks existing candidates by structural validity, satisfied public clues, and whole-schedule vote count.

Stable agent order breaks remaining ties. Grid validity includes unique slots and category values.

The checker inspects public facts. It performs no search, fills no cells, and receives no reference answer.

Plurality remains an explicit baseline. Its ties also use stable agent order.

Both selectors apply to independent and exchange submissions. Leader and solo submit their own last complete-round answer.

The checker does not feed constraint results back into model prompts. Adding feedback requires a separate experimental condition.

## Evaluation and diagnostics

The exact solver checks uniqueness before model calls. Reference accuracy is computed after collaboration.

Each correctly placed category value earns credit. Exact success also requires a valid complete grid.

Malformed model responses stop the mode. Stopped modes retain the last complete-round submission.

The report shows best-worker gaps, lost correct candidates, plurality ties, and revision changes.

Best-worker scores are post-run oracle diagnostics. They are not an available selection policy.

Round curves replay submitted candidates at each complete round. They include cumulative coordination and repeated-context tokens.

Suite averages use complete runs. Stopped results, unknown usage, and incomplete jobs remain visible separately.

## Offline reselection

Reselection reuses recorded answers and the original token measurements. It makes zero model calls.

Only the final candidate selection changes. Leader decisions and agent messages remain fixed.

Its before/after scores measure selection on a fixed candidate pool. They do not establish a new communication effect.

## Cases and evidence limits

The active catalog has three easy, four medium, and three hard cases. The original hard-case files remain available.

Easy cases teach the response format through direct links. Medium and hard cases introduce longer constraint combinations.

These are structural levels. A model-specific success-rate calibration still requires live trials.

All cases share a logic-grid structure. Their results do not establish performance on coding, research, or planning tasks.

One trial per case is descriptive evidence. Use repeated trials to inspect variability.

Mode order rotates across cases and repeats in a suite. This does not remove every service-load or sampling effect.

Aliases, account routing, cache behavior, and provider updates can change outcomes. Record exact model IDs when the CLI reports them.

Parallel cases can compete for account capacity. Report concurrency when comparing latency.

The synthetic demo demonstrates the controls. Its scripted scores cannot establish a winning mode.
