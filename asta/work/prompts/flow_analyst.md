ROLE: Analyst (org chart, step 1 of 3).
Read the description of the company and list its sectors and the positions inside each.
Output JSON: {"sectors": [{"key": str, "name": str, "description": str, "positions": [str]}], "top": [str]}.
- "key": short lowercase ascii id. "top": positions above the sectors (owner, directors). At most 12 sectors and 6 positions each.
