ITEM ICONS
==========

One PNG per item, named after the item's id:

  tools/<id>.png      ids from data/relics.json       (e.g. tools/coffee_machine.png)
  supplies/<id>.png   ids from data/consumables.json  (e.g. supplies/pizza_night.png)
  training/<id>.png   ids from data/training.json     (e.g. training/train_seismic.png)

Icons are loaded when the game starts; press F5 in game to reload them. Any size
works (they're scaled to fit), but square images with a transparent background
look best. They show in the tool bar while you play, on supply buttons, in the
shop and on the centre's unlock track, always with a tooltip saying what the
item does.

An item without a PNG gets a generated badge (its initials in the rarity or
category colour), so new items you add to the data files always have an icon.
The shipped icons are those badges, written by tools/make_placeholder_items.py
(run it with --force to redraw them all).
