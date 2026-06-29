# Patch summary

## Title

Add Overview launch error banner and classifier

## What changed

- added `launch_error_classifier.py` with stable launch issue codes;
- added a yellow dismissable issue banner to Overview;
- added icon-only copy buttons for short and full issue text;
- added close button for the banner;
- wired Overview actions to classify both exceptions and partial combined starts;
- documented the error code classifier in `docs/LAUNCH_ERROR_CLASSIFIER.md`;
- added regression tests for classifier behavior and banner UI contract.

## Why

After the unified launch toggle, the GUI made it visible that Zapret and VLESS did not always start together, but the reason was still buried in long logs. The Overview now surfaces the failure reason directly while preserving full copyable diagnostics for analysis.
