ANALYST AVATARS
===============

Each analyst is built from one PNG per layer, stacked in the order listed in
avatar_config.json (first = bottom):

  skin/         face, ears, neck and shoulders   (greyscale, tinted with a skin tone)
  clothes/      top                              (greyscale, tinted with the team colour)
  eyes/         eyes and eyebrows
  nose/
  mouth/
  hair/         (greyscale, tinted with a hair colour; ~6% of analysts are bald)
  accessories/  glasses, headsets, hats...       (~55% of analysts have none)
  overlays/     tired.png is drawn over analysts whose fatigue is high

Everything in these folders is loaded automatically when the game starts.


Adding art
----------
* Drop more PNGs into any layer folder. They're picked at random for new
  analysts. In game, press F5 to reload, or open "Avatars" on the title screen
  to browse random combinations (Space = shuffle, T = tired overlay, click a
  face to see it in every team colour, hover for the pieces it uses).
* Every piece must use the same canvas (128x128 by default; set "canvas" in
  avatar_config.json if you prefer another size). Draw each piece in position
  on that canvas, with transparency everywhere else, so the layers line up.
  Using one of the placeholder files as a template is the easiest start.
* Layers with a tint are drawn in greyscale: white becomes the full tint colour
  and greys become darker shades of it (the PNG is multiplied by the colour).
  To keep a piece's own colours, put "_fixed" in its file name
  (e.g. beanie_fixed.png). Layers without a tint (eyes, nose, mouth,
  accessories) are drawn exactly as they are.
* Pieces that need a part behind the head (long hair, ponytails) come in pairs:
  long.png (in front of the face) and long_back.png (behind everything).
* For pixel art, set "pixel_art": true so sprites are scaled without smoothing.
* "portrait_crop" is the square [x, y, width, height] of the canvas used for
  the round portraits (chips, desks, team cards). The ops room shows the whole
  canvas.
* You can add new layers (e.g. "freckles" or "facial_hair") by adding a folder
  and an entry in "layers". "chance_none" is how often an analyst gets nothing
  from that layer; "required": true means everyone gets one.
* Palettes ("skin_tones", "hair_colours") are lists of [r, g, b]. Add colours,
  or make your own palette and point a layer's "tint" at it.

Male and female pieces
----------------------
Every analyst is male or female (their first name is picked to match, from
data/names.json). Start a file name with f_ for a piece only female analysts
get, or m_ for one only male analysts get (e.g. hair/f_bun.png, hair/m_buzz.png,
hair/f_long.png with hair/f_long_back.png). Files without either prefix are
for everyone. This works in any layer, not just hair.

"chance_none" can also be set per gender. For hair it's the bald chance, so
    {"name": "hair", "tint": "hair_colours", "chance_none": {"f": 0.0, "m": 0.12}}
makes 12% of men bald and no women. ("any" sets it for analysts with no gender,
such as contractors and older saved analysts.)

Condition layers (e.g. tired eye rings)
---------------------------------------
A layer with "condition": "tired" is only drawn while the analyst is tired
(fatigue at or above "tired_fatigue"), but in its own place in the stack, so
it can sit under the eyes instead of on top of everything. Everyone gets one
of its pieces (picked per analyst if there are several). Example, between
skin and eyes:

    {"name": "skin",       "tint": "skin_tones", "required": true},
    {"name": "tired_eyes", "tint": "skin_tones", "condition": "tired"},
    {"name": "clothes",    "tint": "team"},
    {"name": "eyes"},

With "tint": "skin_tones" the rings take the analyst's skin colour, so paint
them in greys (darker grey = darker rings). Leave the tint out to keep the
PNG's own colours. Remove "tired" from "overlays" if you no longer want the
old overlay on top.

Whole faces instead of layers
-----------------------------
If you'd rather draw complete avatars, put them in skin/ with "_fixed" in the
name (so they aren't tinted) and empty the other folders, or remove those
layers from avatar_config.json. Keep a clothes/ layer on top if you still want
the team colours to show. Layers are composed once and cached, so there's no
speed benefit to baking them yourself.

The shipped pieces are placeholders drawn by tools/make_placeholder_avatars.py
(run it with --force to redraw them). Replace or delete them whenever you like.
Analysts already saved in a run keep their pieces, and if a file disappears a
replacement is picked automatically. With no art at all, the game shows coloured
initials instead.
