# What will be tested

- Best base prompt
- How do variants differ?
  - v1: reason before code
  - v2: structured field instead of blob
  - v3: prevent species bias
  - v4 return top 3 instead of just 1 (log uncertainty)
- Model comparison (`gpt-4o-mini`, `gpt-5.4-nano`, `gpt-5.4-mini` + small `gpt-5.4` sample)
- Final test on `heldout.csv`

# Potential Changes (future):
- Test using expert-labelled data -> necessary to actually calibrate results
- Triage based on outcome. Consider the following in final decision:
  - LLM output
  - LLM confidence distribution across top 3
  - GEE result
- If GEE impossible (use offline dataset)
- Potential water overcoding
- Extend output with following:
  - Has coords
  - GEE output
  - 

# Changes: 
- Classifier
- Model (include added metrics)
- Pipeline
- GEE option (what if no key?)
