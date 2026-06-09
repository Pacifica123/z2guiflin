# v0.4-alpha Stage 7f — bounded phase alternatives and core docs

This patch continues the Discord desktop non-voice investigation after Stage 7e.

## What changed

- Adds an owner-visible `Alt check cap` to Blockcheck Lab.
- Defaults Discord ordered phase runs to 160 strategy checks per phase alternative.
- If an ordered phase alternative reaches the cap without `AVAILABLE`, the GUI stops only that candidate and moves to the next OR alternative.
- If `AVAILABLE` appears first, the existing early-stop path still advances to the next required phase.
- Improves the diagnostics layout with wider default window geometry, max widths on long controls, larger row spacing and a reserved hint area.
- Adds `docs/ZAPRET2_CORE_BLOCKCHECK_NOTES.md` after reviewing the bundled zapret2 documentation and Flowseal/Windows references.

## Why

Owner testing showed that the phase-gated Discord run could stay on `stable.dl2.discordapp.net` indefinitely or until manual Stop. That blocks the intended tournament loop from reaching `updates.discord.com`, `discord.com`, gateway and CDN/media phases. Stage 7f keeps the owner-sketched AND/OR phase semantics but adds a practical budget so one moving CDN/updater target cannot consume the whole run.

## Boundaries

- This does not yet implement a full automatic one-strategy validator across every phase.
- This does not port Flowseal/Windows presets into an executable Linux runtime preset.
- This does not touch Discord voice/UDP/STUN, which remains reserved for Stage 8.
- Raw upstream blockcheck logs remain available in `.zap2/blockcheck/logs/`.
