# Discord observation matrix auto row runner

`v0.4-alpha Stage 7o2d` adds a more automated row-runner mode for collecting matrix rows without juggling build/start plan ids manually.

Use:

```bash
PYTHONPATH=gui python -m zap2_gui.app --discord-observation-matrix-run-row multisplit --matrix-row-auto
```

For strategy rows the owner phase will select the strategy, build `nfqws2` if it is missing, prepare and confirm the start workflow plan, then print a single sudo command for the privileged phase.

The sudo phase will start Default workflow if needed and then enter the guided probe. Discord is still never launched by Zap2. Open Discord only when the probe prints `MANUAL ACTION`.

This keeps the safety model intact:

- local build runs as the project owner, not root;
- firewall/NFQUEUE changes happen only in the explicit sudo phase;
- Discord is a manual action;
- generated reports remain the comparison source for strategy promotion.
