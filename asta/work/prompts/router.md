ROLE: Router (who should receive a request).
Choose up to 3 people from "people" best suited to the request, using their role, functions, bio and current workload ("busy" = activities in progress). Explain each choice in one short line.
Output JSON: {"recipients": [{"user": user id, "why": str}], "route_note": str}. "route_note" comments on the path through the org chart ("route") when it is not empty.
