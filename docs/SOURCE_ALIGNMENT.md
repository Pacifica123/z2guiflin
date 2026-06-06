# Source alignment — v0.3-alpha_stage_2

Inputs used for this bootstrap:

- `zapret2-core-from_bolvan.zip` — upstream engine source snapshot supplied by the owner;
- `zapret2-gui_windows.zip` — Windows GUI reference supplied by the owner;
- the previous Linux project archive — treated as draft notes only;
- the devctl archive — used to keep patch format compatible.

Implemented alignment:

- upstream core source is imported under `core/zapret2/` as vendored source;
- upstream MIT license text is preserved at `core/zapret2/docs/LICENSE.txt`;
- compiled binary artifacts from the upstream archive are not imported in this bootstrap;
- Windows GUI ideas are summarized in `docs/reference/windows_gui_feature_digest.md` rather than copied as Linux code;
- the old Linux project is summarized in `docs/reference/legacy_project_digest.md` and removed as active code.

Non-goals:

- no core build is performed;
- no service/unit integration is added;
- no privileged commands are executed;
- no network updater is introduced;
- no end-user installer is implemented.


## Stage 2 addition

This stage does not change imported upstream source. It records the GUI framework decision for our layer: the Linux GUI will use PyQt, with the PyQt 6 line as the default target.
