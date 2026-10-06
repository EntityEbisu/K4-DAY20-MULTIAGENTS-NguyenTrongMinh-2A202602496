Exploratory local-model pilots, preserved separately from the official results.

- `pilot-ternary/baseline/data-learn/`: `ternary-bonsai-4b` via the LM Studio shim, context 8192; score 0/8, 14 tool calls, 102756 tokens, 77.4 seconds.
- `pilot-nemotron/baseline/data-learn/`: `nvidia/nemotron-3-nano-4b` via LM Studio directly, context 8192; score 0/8, 4 tool calls, 27578 tokens, 62.7 seconds. The model attempted a Python script but generated a syntax error and did not write `answer.json`.

These are pilots only. Official comparisons should use one chosen model consistently across all conditions and tasks.