# Legacy SWE-bench Experiments

This directory preserves BugPilot's earlier SWE-bench Lite experiments and
evaluation artifacts for reproducibility and historical reference.

These results were produced by an earlier evaluation pipeline. In particular,
some experiments used information from the SWE-bench gold patch to identify
the target source file before repair.

For that reason, these artifacts should not be interpreted as BugPilot's final
end-to-end SWE-bench performance.

The current evaluation pipeline will use repository-level investigation and
bug localization without gold-patch file information.

Contents:

- `scripts/` - original evaluation and retry scripts
- `inputs/` - benchmark instance inputs
- `predictions/` - generated BugPilot predictions
- `results/` - SWE-bench harness result artifacts
- `patches/` - individual experimental patches
