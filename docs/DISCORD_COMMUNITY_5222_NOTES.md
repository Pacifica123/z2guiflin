# Discord community 5222 notes (v0.4-alpha Stage 7m)

Stage 7m imports the owner-provided Discord-only Windows GUI community preset as a Linux diagnostic seed. The new selectable strategy is:

```text
community-discord-hostfakesplit-5222-minimal
```

It is intentionally narrower than `community-discord-youtube-edge-flow` and `community-discord-syndata-edge-flow-v2`:

- no YouTube fallback;
- no automatic selection;
- no voice/STUN runtime block in the v0.4 non-voice path; Stage 8 remains reserved for voice/UDP;
- explicit TCP `5222` coverage alongside the Discord HTTPS-like port set.

## Why 5222 is being tried

The source Windows preset declares this capture envelope:

```text
--wf-tcp-out=80,443,1080,2053,2083,2087,2096,5222,8443
```

The actual hostfakesplit blocks in that preset do not repeat `5222` in their `--filter-tcp` values. On Linux, WinDivert `--wf-*` switches are not executed, so Stage 7m makes the hint explicit in the owner-confirmed nft/NFQUEUE scope:

```text
--filter-tcp=80,443,1080,2053,2083,2087,2096,5222,8443
```

This is a diagnostic bridge, not a claim that TCP 5222 fixes the current Discord updater. The owner evidence still points at `updates.discord.com`/`discord.com` Cloudflare edges stuck in `SYN-SENT` on TCP/443. The 5222 seed is useful because it tests whether the successful Windows community preset depended on a wider Discord capture envelope than our earlier Linux ports.

## Owner experiment

```bash
PYTHONPATH=gui python -m zap2_gui.app --select-strategy community-discord-hostfakesplit-5222-minimal
PYTHONPATH=gui python -m zap2_gui.app --default-start-plan
```

Then continue through the normal owner-confirmed Default workflow. If Discord still stays at `Checking for updates`, run endpoint discovery again and check whether TCP/5222 appears at all. If only TCP/443 `SYN-SENT` remains, this seed did not address the updater blocker.
