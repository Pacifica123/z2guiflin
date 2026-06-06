# Legacy project digest

The previous Linux project is now a draft source, not the active implementation baseline. The useful concepts to carry forward are:

- a strict privilege boundary between GUI planning and system mutation;
- guided lifecycle flows instead of unexplained buttons;
- “optimal next action” as a dashboard concept;
- source alignment reports for patches that claim to follow upstream/reference behavior;
- transactional thinking around apply/rollback/logging;
- localization as a product requirement, not a late afterthought;
- bytecode-safe and cache-safe checks in devctl.

The main lesson is also negative: many guarded installer patches can still fail to reach product essence if the architecture is centered on remote installation. `v0.3-alpha` changes the center to a vendored native core source tree.
