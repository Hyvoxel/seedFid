# Minetest / Luanti Seed Finder

A terminal tool that tries many world seeds, measures the **real** generated terrain around spawn, and ranks the seeds by what you want (flat land, forest, mountains, islands, snow...). It also prints **x, y, z coordinates** so you can teleport straight to the interesting spots.

- Pure Python 3 (standard library only)
- Uses the real Luanti/Minetest mapgen, so results match what you get in game
- Works on Android via Termux + Debian (proot), and on normal Linux/macOS/Windows

## How it works

1. For each seed, the script creates a temporary world with a fixed seed.
2. It starts a headless Luanti server with a small built-in Lua mod (`seedscan`).
3. The mod generates the area around spawn, samples terrain columns, records stats and feature locations, writes JSON, and shuts the server down.
4. Python scores every seed against your wants and prints the best ones.

Results are cached in `seed_results.json` so you can re-rank for a different goal without scanning again.

## Requirements

- Python 3
- Luanti (Minetest) server, with **Minetest Game** (game id `minetest`)

### Linux / Debian

```
sudo apt install python3 luanti-server
```
(on older systems the package is `minetest-server`). If the binaries are not found, add `/usr/games` to your PATH:

```
export PATH=$PATH:/usr/games
```

### Android (Termux)

The Termux repo may not ship Luanti, so run Debian inside Termux:

```
pkg install proot-distro python
proot-distro install debian
termux-setup-storage
proot-distro login debian --bind ~/storage/downloads:/mnt/dl
```

Then inside Debian:

```
apt update
apt install python3 luanti-server
export PATH=$PATH:/usr/games
cp /mnt/dl/seedfinder.py ~
cd ~
```

To keep the PATH change permanently:

```
echo 'export PATH=$PATH:/usr/games' >> ~/.bashrc
```

## Usage

```
python3 seedfinder.py --want "flat,forest,spawn-water" --count 20
python3 seedfinder.py --seeds 123 456 789 --radius 160 --want mountains,snow
python3 seedfinder.py --rank-only --want desert
python3 seedfinder.py
```

Running with no `--want` shows a menu and asks what you want.

### Options

| Option | Meaning | Default |
|---|---|---|
| `--want` | Comma-separated goals (see below) | asks you |
| `--count` | Number of random seeds to scan | 10 |
| `--seeds` | Specific seeds to scan | random |
| `--radius` | Scan radius around spawn in nodes (bigger = slower) | 160 |
| `--step` | Sampling step in nodes | 4 |
| `--top` | How many results to show | 5 |
| `--game` | Game id | `minetest` |
| `--mapgen` | Map generator | `v7` |
| `--minetest` | Path to the Luanti/Minetest binary | auto-detect |
| `--timeout` | Seconds allowed per seed | 900 |
| `--rank-only` | Only rank cached results, no scanning | off |
| `--all-spots` | Print every location found | off |

On a phone, start with `--radius 96`. It takes roughly 15-20 seconds per seed.

## Wants

| Want | Meaning |
|---|---|
| `flat` | Flat terrain overall |
| `mountains` | Tall, rugged mountains |
| `water` | Lots of lakes/ocean |
| `islands` | Much water but spawn on land |
| `forest` | Dense trees |
| `grassland` | Lots of grass |
| `desert` | Sand/desert |
| `snow` | Snow and ice |
| `caves` | Many caves |
| `spawn-flat` | Flat area around spawn |
| `spawn-water` | Water near spawn |
| `spawn-forest` | Trees near spawn |
| `spawn-land` | Spawn on dry land |
| `survival` | Good survival start (flat spawn, trees, water, grass) |

Put `no-` in front to avoid something, for example `no-water` or `no-snow`. Several wants are averaged into one match score (0-100%).

## Example output

```
#1  seed 957725051549   match 38%
   height avg 28 (max 88, min -19), roughness 2.5, spawn y=52
   water 18%  trees 58%  grass 4%  sand 3%  snow 0%  caves 3%
   Places (teleport with /teleport x,y,z):
     spawn  0,53,0
     water  -44,1,32
```

## Using a result

1. Create a new world with that seed and the same mapgen (`v7` by default), or set `fixed_map_seed` in `minetest.conf`.
2. In game, run `/grantme all` once, then `/teleport x,y,z` to jump to a listed place.

Coordinates are the ones nearest to spawn, except `peak` and `low`, which are the highest and lowest points in the scanned area.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Luanti/Minetest not found` | Install the server and add `/usr/games` to PATH, or pass `--minetest /path/to/luantiserver` |
| `luantiserver: command not found` | `export PATH=$PATH:/usr/games` |
| Every seed says `failed` | Read the error lines printed under it. Check the game exists with `luantiserver --gameid minetest --world ~/testworld` |
| Game `minetest` not found | Install Minetest Game from content.luanti.org into your games folder |
| Very slow | Lower `--radius` (try 64-96) |
| `(no coordinates cached)` | Rescan the seed; it was cached by an older version |

## Notes and limits

- Only the area within `--radius` of spawn is analysed. Terrain beyond that can be very different.
- Biomes are detected from surface block names (grass, sand, snow...), not from biome data.
- The tool targets Minetest Game. Other games may work with `--game`, but node names differ and the stats may be less accurate.
- The scan uses the world's default spawn area around (0, 0).
