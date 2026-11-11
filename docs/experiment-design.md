# Experiment design

## What changes

The independent and exchange modes differ only in message delivery. Their worker counts, task prompts, rounds, and final selection rule match.

Leader mode also changes roles, worker count, coordination calls, and final selection. It is a bundled architecture comparison, not a communication-only intervention.

The lab reconstructs context explicitly for every call. Agents receive the public task and their own previous response.

Older full histories are not retained. Exchange agents also receive peer messages from the previous round.

The leader receives complete current worker candidates. Workers receive the leader's current schedule, message, and their assigned instruction.

Agents never see evaluation scores during a run. Peer messages are claims to inspect, not trusted ground truth.

## Budgets

Equal ceilings define an allowed resource envelope. They do not force all modes to spend the same amount.

The default round count gives solo fewer calls. A twelve-round solo run provides an additional computation baseline.

Compare quality at similar observed resource use. Do not describe unequal actual usage as an exact fixed-compute experiment.

No retry, fifth-agent judge, reference-guided answer selection, or hidden model upgrade enters the protocol.

Coordination tokens, repeated task context, response tokens, and cache reads count toward recorded totals.

## Selection and scoring

Independent and exchange modes use plurality over complete schedule candidates. Row order does not affect equality.

The lowest agent ID wins a tie. A wrong majority remains wrong. The answer key never determines the winner.

The leader submits its own synthesis. Solo submits its last response.

The score is the fraction of correctly placed category values. A value must occur once in a uniquely specified time row.

Exact success also requires a complete valid schedule. Missing answers score zero. Stopped runs retain the last complete-round submission.

Evaluation happens after collaboration. Per-call scores describe trajectories but never feed back into a model prompt.

A message can cite a valid clue ID while misinterpreting that clue. The lab does not claim automatic proof verification.

## Evidence limits

One case and one trial cannot establish a general winner. Use different cases and repeated trials.

Generated cases share a task structure. Results do not automatically transfer to coding, web research, or planning tasks.

The exact solver verifies uniqueness. It does not establish human difficulty or model difficulty.

Alias versions, provider updates, subscription routing, cache behavior, and service load can change results.

The controller uses round barriers. These protocols do not model unrestricted asynchronous teams or continuous shared memory.

Explicit summaries can lose useful details. Compare different message lengths as a separate experiment.

The demo uses the same scripted correction pattern across modes. It demonstrates controls and report fields only.

## Suggested investigations

- Does sharing help more on cases with many cross-category clues?
- Does a wrong early message spread to other workers?
- Does a leader identify disagreements or repeat the most confident claim?
- Does a longer message improve quality enough to justify repeated input tokens?
- Does twelve-round solo match four three-round workers?
- Does a larger budget improve scores or only increase repeated explanations?
