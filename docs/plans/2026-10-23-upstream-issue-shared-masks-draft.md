**Title:** Sea masks of textures straddling a 1° line keep only one tile's half

Hi, a finding from running OXO-built tiles next to your regional packages (XEL 0.5.0-beta.1, `eu-west` 0.5.0).

**What happens.** Every OXO task builds one tile in an empty scratch, so `build_masks` never finds the neighbours' `.mesh` (`select_neighbor_meshes`, `record_water_tris`). `build_water_pre_mask` starts black and paints white only where a mesh exists, so in each tile's copy of a mask whose texture straddles a 1° line, the area beyond the line is treated as sea: a thin fake-shore fringe along the line, black beyond it. Both neighbours write a mask with the same name, and in a flat package only one copy survives (with `xearthlayer-publish add`, the first in lat/lon order, `processor/ortho4xp.rs` sorts tiles and dedups masks by filename).

**Example, Cannes.** `textures/23936_34032_ZL16.png` in `eu-west` (6.94–7.03°E, ~43.55°N) is referenced by `23936_34032_GO216_sea_overlay.ter`, which `+43+007.dsf` uses. Downsampled to your 1024 px mask resolution, it agrees with our `+43+006`-only build to about 1 grey level on average. East of 7°E it is black (max 10/255), where the `+43+007` build has content. So sea triangles of `+43+007` in that texture get no shore transition.

**Across the package (indicative).** 3,913 of the 31,002 sea masks straddle a 1° line. At 4,003 of those line crossings one side is entirely ≤30 while the other side has content; only 21 crossings have content on both sides. Some one-sided cases are legitimate (no coast on that side), so this strongly suggests a systematic effect rather than proving it. I haven't checked how visible it is in the sim.

**What we do on our side.** At packaging time we merge the copies of a shared mask, brightest value per pixel. We checked that against Ortho4XP builds with the neighbour mesh present (same image, settings and OSM as our production builds; the isolated rebuilds are pixel-identical to the production masks):

| Shared mask | merge | pixels differing from the with-neighbour mask | max abs error |
|---|---|---|---|
| `23936_34032` (7°E, Cannes) | brightest per pixel | 55,795 of 16.7M, all within 35 px of the line | 93 |
| | each pixel from its own tile | 59,974 | 135 |
| | one copy only (as packaged today) | 6,650,388 | 255 |
| `21936_34224` (51°N, Frankfurt) | brightest per pixel | 230, all within 5 px of the line | 24 |
| | one copy only | 12.3M | 255 |

It is not exact: where the neighbour's sea meets the line, an isolated copy is too bright there, and since `blur_mask` converts `masks_width` at `tile.lat + 0.5`, even the two with-neighbour builds of a texture across a latitude line differ slightly (32,040 px, ≤16 levels, at `21936_34224`).

(Side note on the Cannes numbers: our `+43+007` build had a broken coastline in its OSM data, cut at the French–Italian border, so its sea was meshed as land; that inflates the 7°E error. Not related to your packages.)

**Questions.**
1. Would you take a fix upstream: a merge in `xearthlayer-publish`, or a two-phase build (all meshes of a region first, then masks)? The second gives the exact masks, but it conflicts with the one-tile-per-task model, so a packaging-side merge may be the pragmatic option.
2. `eu-west` looks built with `mask_zl=14` (all `LOAD_CENTER_BORDER … 1024`) and `use_masks_for_inland=False` (inland water uses `water_transition.png`), while `docs/examples/example-region.toml` has `16` / `True`. Was it built with different settings? (Only asking because we follow the example.)
