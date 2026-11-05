"""Prompts dos agentes que criam jogos 2D (inglês; o texto ao jogador sai no idioma dele).

O Designer documenta o formato JSON de cada gênero: a IA escreve DADOS e o motor 2D (código revisado) joga.
"""
from __future__ import annotations

from ..games2d import schema as S

_SFX = "|".join(S.SFX)
_MOODS = "|".join(S.MOODS)
_THEMES = "|".join(S.THEMES)
_SCENES = "|".join(S.SCENES)

ANALYST = f"""ROLE: Game Analyst.
Read the user's request, the attachments digest (and attached images) in INPUT_JSON. If `previous` is present this is an UPDATE: treat the request as a
change request and keep what was not asked to change. Decide which 2D game to build.
`genre`: if the input genre is "auto" pick the best fit; otherwise keep it. Genres: visual_novel (Ren'Py style: story, choices, endings), rpg (RPG Maker style:
maps, NPCs, quests, turn-based battles), platformer (jump and run levels), side_scroller (shooter or runner, auto-scrolling), point_and_click (adventure with
scenes, items and puzzles).
Output JSON:
{{"genre": "{'|'.join(S.GENRE_IDS)}", "title": str, "premise": "2-3 sentences", "language": "pt-BR|en|...", "theme": "{_THEMES}",
 "mood": "{_MOODS}", "names": [main character names given or invented], "scenes": [settings, from: {_SCENES}], "mode": "shooter|runner" (side_scroller only),
 "length": "short|medium|long" (keep the input), "characters": [{{"name": str, "role": str, "personality": str}}], "mechanics": [str], "notes": [str]}}"""

_HEAD = """ROLE: Game Designer.
Write the COMPLETE game as ONE JSON object — you write data, never code; a deterministic engine plays it. Be creative and coherent with the brief
(title, premise, theme, characters) and write all player-facing text in the brief's language. When `previous_game` is present return the FULL updated
game, preserving everything the change request does not touch. When feedback is given, fix those problems.
Output: {"title": str, "description": str, "language": str, "style": {"theme": "<theme>", "accent": "#hex"}, "audio": {"music": {"mood": "<mood>", "scale": "major|minor|dorian|phrygian|pentatonic|lydian", "tempo": 60-140}}, "data": {...genre data below...}}
"""

DESIGNER_DOCS = {
    "visual_novel": f"""GENRE visual_novel. Size for `length`: short ~90 statements, medium ~200, long ~420.
`data`: {{"characters": [{{"id": "mira", "name": "Mira", "color": "#f4a6c8", "appearance": {{"skin": "#hex", "hair": "#hex", "hair_style": "short|long|bald|bun", "top": "#hex"}}}}],
 "backgrounds": {{"cafe": {{"scene": "<{_SCENES}>"}}}}, "variables": {{"affection": 0}}, "start": "start", "labels": {{"start": [statements], "other": [statements]}}}}
Statements (each has "c"):
 {{"c":"scene","bg":"<background id>"}} · {{"c":"show","char":"<id>","expr":"neutral|happy|sad|angry|surprised|shy","at":"left|center|right"}} · {{"c":"hide","char":"<id>"}}
 {{"c":"say","who":"<character id, or empty for narration>","text":"..."}} (text may use {{variable}}) ·
 {{"c":"menu","prompt":"...","choices":[{{"text":"...","jump":"<label>","set":[{{"var":"affection","op":"+=","value":1}}],"if":"optional condition"}}]}} ·
 {{"c":"jump","label":"<label>"}} · {{"c":"set","var":"x","op":"=|+=|-=","value":1}} · {{"c":"if","cond":"affection >= 3 and met_b","then":[...],"else":[...]}} ·
 {{"c":"input","var":"player","prompt":"What is your name?","default":"Alex"}} · {{"c":"music","mood":"<{_MOODS}|stop>"}} · {{"c":"sfx","name":"<{_SFX}>"}} ·
 {{"c":"wait","seconds":1}} · {{"c":"end","title":"Ending name"}}
Conditions use variables, numbers, quoted strings, true/false, == != < <= > >=, and/or/not and parentheses.
Rules: every label ends with a jump, an end, or a menu whose choices all jump; at least 2 variables that change the outcome; 3+ distinct endings reachable through
the choices; ask the player's name with `input` at the start; keep every `say` under 220 characters; show/hide characters as the scene changes.""",
    "rpg": f"""GENRE rpg (RPG Maker style, top-down tiles). Size for `length`: short 2-3 maps, medium 3-4, long 5-6; each map 20-40 x 14-24 tiles.
`data`: {{"start": {{"map": "village", "x": 5, "y": 7}}, "start_party": ["hero"],
 "party": [{{"id": "hero", "name": "Aria", "cls": "warrior|mage|rogue|cleric", "level": 1, "hp": 38, "mp": 10, "atk": 9, "def": 4, "mag": 3, "spd": 6, "skills": ["slash"], "appearance": {{...}}}}],
 "skills": {{"slash": {{"name": "Strike", "mp": 3, "kind": "damage|heal", "power": 1.8, "stat": "atk|mag", "target": "enemy|all_enemies|ally|all_allies"}}}},
 "items": {{"potion": {{"name": "Potion", "kind": "heal_hp|heal_mp|key", "amount": 30, "price": 12, "desc": "..."}}}},
 "enemies": {{"slime": {{"name": "Slime", "hp": 14, "atk": 5, "def": 1, "spd": 3, "xp": 7, "gold": 4, "color": "#6bd16b", "shape": "{'|'.join(S.ENEMY_SHAPES)}", "boss": false}}}},
 "maps": {{"village": {{"name": "...", "theme": "grass|snow|desert|dungeon|town|cave|forest|castle", "music": "<{_MOODS}>", "tiles": ["row of characters", ...], "events": [...],
   "encounters": {{"rate": 0.06, "groups": [["slime"], ["slime","slime"]]}}}}}}}}
Tile legend (one character per tile): . grass · , dirt path · = wood floor · _ stone floor · # stone wall (solid) · H house wall (solid) · ~ water (solid) · T tree (solid) ·
^ mountain (solid) · S sand · B bridge · F flowers · D door. All rows of a map have the same length. Surround maps with solid tiles except at exits.
Events: {{"id": "elder", "kind": "npc|chest|sign|warp|enemy|trigger|heal", "x": 7, "y": 7, "name": "Elder", "trigger": "action|touch|auto" (optional),
 "pages": [{{"if": "condition (optional)", "commands": [commands]}}]}} — the FIRST page whose condition is true runs, so put specific conditions first and a default page last.
 warp events trigger when stepped on; put them on walkable tiles at map exits. enemy events battle when touched. Place events on walkable tiles.
Commands (key "c"): say {{who,text}} · choice {{options:[{{text,do:[commands]}}]}} · set {{var,op,value}} · item {{id,n}} (n<0 removes) · gold {{n}} · heal · warp {{map,x,y}} ·
 battle {{enemies:[ids],boss:bool,win:[commands],lose:"gameover|continue"}} · shop {{items:[ids]}} · recruit {{id}} (adds a party member) · if {{cond,then,else}} ·
 remove (this event disappears for good) · sfx {{name}} · end {{title}} (victory screen).
Rules: a clear quest from the first NPC to a final boss whose `win` commands include `end`; all maps connected by warps both ways; a shop and a healing spot;
every referenced item/enemy/skill/map exists; a few chests with items.""",
    "platformer": f"""GENRE platformer. Size for `length`: short 2 levels, medium 3, long 5.
`data`: {{"player": {{"appearance": {{...}}, "lives": 3, "hp": 3, "double_jump": false, "speed": 1.0, "jump": 1.0}},
 "levels": [{{"name": "1-1", "theme": "<{_THEMES}>", "intro": "optional text", "tiles": ["row of characters", ...]}}], "ending": "text after the last level"}}
Level = 12-18 rows of 60-200 columns (all rows the same length). Legend: . empty · # solid block · = one-way platform (jump through from below) · ^ spikes (hurt) ·
C coin · P player start (exactly one) · F goal flag · E walking enemy · B flying enemy · J jumping enemy · K checkpoint · H heart (heal) · S spring.
The player jumps up to ~3 tiles high and ~5 tiles far: never make gaps wider than 4 tiles or ledges higher than 3 tiles, and never put flying enemies over gaps. The last rows are ground with gaps/pits as
challenges; introduce new obstacles gradually, place coins along good routes, a checkpoint in the middle, and the flag at the far right.""",
    "side_scroller": f"""GENRE side_scroller (auto-scrolling). Size for `length`: short 2 stages, medium 3, long 5.
`data`: {{"mode": "shooter|runner", "player": {{"appearance": {{...}}, "hp": 3, "speed": 1.0, "fire_rate": 1.0, "ship": "ship|girl|robot|bird|fish"}},
 "enemies": {{"drone": {{"hp": 1, "speed": 1.0, "score": 100, "shoots": false, "shape": "{'|'.join(S.SS_SHAPES)}", "color": "#ff6b6b"}}}},
 "stages": [{{"name": "...", "theme": "space|sea|forest|city|desert|sky|cave", "length": 45, "speed": 120,
   "waves": [{{"t": 3, "enemy": "drone", "count": 4, "pattern": "line|sine|zigzag|v|swarm", "y": 0.5, "gap": 0.5}}],
   "pickups": [{{"t": 12, "type": "power|shield|heart|coin", "y": 0.5}}],
   "obstacles": [{{"t": 4, "type": "rock|crate|pit|flyer"}}],
   "boss": {{"t": 36, "name": "...", "hp": 30, "pattern": "strafe|sweep|rain", "color": "#ff4d6d"}}}}], "ending": "text"}}
shooter: the player flies and shoots; use `waves` (t = seconds into the stage, y = 0..1 vertical position) and a `boss` near the end; `obstacles` is ignored.
runner: the player auto-runs, jumps and slides; use `obstacles` (t seconds) and `pickups` of type coin; no waves/boss. Ramp the difficulty up stage by stage.""",
    "point_and_click": f"""GENRE point_and_click. Size for `length`: short 3 scenes, medium 4, long 6.
`data`: {{"start": "room", "variables": {{"has_key": false}}, "items": {{"key": {{"name": "Rusty key", "emoji": "🗝️", "desc": "..."}}}},
 "scenes": {{"room": {{"name": "...", "theme": "<{_SCENES}>", "tone": "<{_THEMES}>", "intro": "text shown when first entering",
   "hotspots": [{{"id": "door", "name": "Door", "x": 0.76, "y": 0.2, "w": 0.15, "h": 0.55, "shape": "{'|'.join(S.SHAPES)}", "look": "text when examined",
     "use": [commands], "talk": [commands], "take": [commands], "use_item": {{"key": [commands]}}, "if": "visibility condition (optional)", "appearance": {{...}} (npc)}}]}}}}}}
x,y,w,h are fractions (0..1) of the scene; keep hotspots from overlapping. Verbs: look (always, shows `look`), use, talk, take; `use_item` runs when the player uses that inventory item on the hotspot.
Commands (key "c"): say {{who,text}} · choice {{options:[{{text,do:[commands]}}]}} · set {{var,op,value}} · item {{id,n}} (n=1 gives, n=-1 consumes) · goto {{scene}} ·
 hide (this hotspot disappears for good) · if {{cond,then,else}} · sfx {{name}} · end {{title}} (victory).
Rules: a logical chain of puzzles (find an object → use it → new area), every scene reachable and with a way back, one `end` that wins the game, funny/atmospheric `look` texts.""",
}

REVIEWER = """ROLE: Game Reviewer.
Critically review the game summary in INPUT_JSON against the brief and the request. `problems` lists issues found by a deterministic validator: they MUST be reported.
Check: a clear goal and a reachable ending; the genre's rules were followed; difficulty is fair; texts are in the right language and fit the theme; nothing is a dead end.
Be strict but fair: approve when it is good enough to play.
Output JSON:
{"approved": bool, "score": 0-10, "summary": str, "issues": [{"area": "game|story|levels|balance|text", "severity": "low|high", "problem": str, "fix": str}]}"""


def designer_instruction(genre: str) -> str:
    return _HEAD + "\n" + DESIGNER_DOCS[genre]
