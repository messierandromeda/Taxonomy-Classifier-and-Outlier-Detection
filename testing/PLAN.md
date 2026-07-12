# What will be tested

- Best base prompt
- How do variants differ?
  - v1: reason before code
  - v2: structured field instead of blob
  - v3: prevent species bias
  - v4 return top 3 instead of just 1 (log uncertainty)
- Model comparison (`gpt-4o-mini`, `gpt-5.4-nano`, `gpt-5.4-mini` + small `gpt-5.4` sample)
- Final test on `heldout.csv`