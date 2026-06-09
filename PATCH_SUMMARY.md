# v0.4-alpha Stage 7m — Discord community 5222 seed

This patch imports the additional owner-provided Discord-only Windows GUI community preset as a Linux diagnostic strategy.

Added:

- `strategies/community-discord-hostfakesplit-5222-minimal.json`
- `strategies/imported/community-discord-hostfakesplit-5222.txt`
- `strategies/imported/community-discord-hostfakesplit-5222.json`
- `docs/DISCORD_COMMUNITY_5222_NOTES.md`
- `tests/test_stage7m_discord_5222_seed.py`

The new strategy makes TCP `5222` explicit in the Linux `--filter-tcp`/nft queue scope because the Windows source preset lists it in `--wf-tcp-out`. It is not selected automatically, does not include the voice/STUN branch, and does not claim to fix the current Discord updater SYN-SENT blocker by itself.
