ROLE: Designer (org chart, step 2 of 3).
Turn the analysis into a flowchart for a whiteboard. Cards are "nodes" and connections are "edges" (from reports/hands work to to).
Output JSON: {"sectors": [{"key": str, "name": str, "color": "#rrggbb", "description": str}],
"nodes": [{"key": str, "kind": "role|sector|note|ai|person", "label": str, "text": str, "sector": sector key or "", "ref": role id or user id or ""}],
"edges": [{"from": node key, "to": node key, "kind": "reports|handoff|approval", "label": str}]}.
- Use kind "role" with "ref" = one of the role ids in the input (the permission level that position has); kind "person" only with a user id from "people"; kind "sector" with "sector" = a sector key.
- Every sector appears as one "sector" node; the chain of command goes top → sector heads → teams. Use "handoff" for work passing between sectors and "approval" for sign-offs.
- At most 60 nodes and 120 edges. Keys are unique.
