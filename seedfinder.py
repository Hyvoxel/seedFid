#!/usr/bin/env python3
import argparse, json, os, random, shutil, subprocess, sys, tempfile, time

CACHE = "seed_results.json"

LUA = r'''
local S = minetest.settings
local R    = tonumber(S:get("seedscan_radius")) or 160
local STEP = tonumber(S:get("seedscan_step"))   or 4
local OUT  = minetest.get_worldpath() .. "/seedscan_out.json"
local YMIN, YMAX = -40, 140
local kcache = {}

local function kind_of(cid)
  local k = kcache[cid]; if k then return k end
  local name = minetest.get_name_from_content_id(cid)
  local def = minetest.registered_nodes[name] or {}
  local g = def.groups or {}
  if name == "air" then k = "air"
  elseif name == "ignore" then k = "ignore"
  elseif def.liquidtype and def.liquidtype ~= "none" then
    k = name:find("lava") and "lava" or "water"
  elseif g.tree or g.leaves or g.leafdecay then k = "tree"
  elseif def.walkable == false then k = "air"
  elseif name:find("snow") or name:find("ice") then k = "snow"
  elseif name:find("sand") then k = "sand"
  elseif name:find("grass") then k = "grass"
  elseif name:find("stone") or name:find("gravel") then k = "stone"
  else k = "other" end
  kcache[cid] = k
  return k
end

local function analyze()
  local vm = minetest.get_voxel_manip()
  local emin, emax = vm:read_from_map({x=-R,y=YMIN,z=-R}, {x=R,y=YMAX,z=R})
  local data = vm:get_data()
  local area = VoxelArea:new{MinEdge = emin, MaxEdge = emax}

  local n, hs = 0, {}
  local cnt = {water=0, tree=0, sand=0, snow=0, grass=0, stone=0}
  local airc, cells = 0, 0
  local slope_sum, slope_n = 0, 0
  local hm = {}
  local sp = {h={}, tree=0, n=0, water=0, wn=0}
  local spawn_h = nil
  local spots = {}
  local function near(name, x, y, z)
    local d2 = x*x + z*z
    local s = spots[name]
    if not s or d2 < s.d2 then spots[name] = {x=x, y=y, z=z, d2=d2} end
  end

  for x = -R, R, STEP do
    hm[x] = {}
    for z = -R, R, STEP do
      local y, h, ground, tree, water = YMAX, nil, nil, false, false
      local wtop = nil
      while y >= YMIN do
        local k = kind_of(data[area:index(x, y, z)])
        if k == "air" or k == "ignore" then
        elseif k == "tree" then tree = true
        elseif k == "water" then water = true; if not wtop then wtop = y end
        else ground = k; h = y; break end
        y = y - 1
      end
      if h then
        n = n + 1
        hs[#hs+1] = h
        hm[x][z] = h
        if water then
          cnt.water = cnt.water + 1
          near("water", x, wtop, z)
        else
          cnt[ground] = (cnt[ground] or 0) + 1
          near(ground, x, h + 1, z)
          if not spots.peak or h + 1 > spots.peak.y then spots.peak = {x=x, y=h+1, z=z} end
          if not spots.low or h + 1 < spots.low.y then spots.low = {x=x, y=h+1, z=z} end
        end
        if tree then cnt.tree = cnt.tree + 1; near("tree", x, h + 1, z) end
        for yy = h - 4, math.max(YMIN, h - 40), -1 do
          cells = cells + 1
          if kind_of(data[area:index(x, yy, z)]) == "air" then
            airc = airc + 1
            near("cave", x, yy, z)
          end
        end
        local prev = hm[x-STEP] and hm[x-STEP][z]
        if prev then slope_sum = slope_sum + math.abs(h - prev); slope_n = slope_n + 1 end
        local pz = hm[x][z-STEP]
        if pz then slope_sum = slope_sum + math.abs(h - pz); slope_n = slope_n + 1 end
        local d2 = x*x + z*z
        if d2 <= 32*32 then sp.h[#sp.h+1] = h; sp.n = sp.n + 1; if tree then sp.tree = sp.tree + 1 end end
        if d2 <= 64*64 then sp.wn = sp.wn + 1; if water then sp.water = sp.water + 1 end end
        if math.abs(x) <= STEP and math.abs(z) <= STEP and not spawn_h then
          spawn_h = h
          spots.spawn = {x=x, y=h+1, z=z}
        end
      end
    end
  end

  local function mean(t) local s=0 for _,v in ipairs(t) do s=s+v end return #t>0 and s/#t or 0 end
  local function std(t) local m=mean(t) local s=0 for _,v in ipairs(t) do s=s+(v-m)^2 end return #t>0 and math.sqrt(s/#t) or 0 end
  local mx, mn = -1e9, 1e9
  for _, v in ipairs(hs) do if v > mx then mx = v end if v < mn then mn = v end end
  local nn = math.max(n, 1)
  local res = {
    columns = n, avg_h = mean(hs), std_h = std(hs), max_h = mx, min_h = mn,
    slope = slope_n > 0 and slope_sum / slope_n or 0,
    water = cnt.water/nn, tree = cnt.tree/nn, sand = cnt.sand/nn, snow = cnt.snow/nn,
    grass = cnt.grass/nn, stone = cnt.stone/nn,
    cave = cells > 0 and airc / cells or 0,
    spawn_h = spawn_h or 0, spawn_std = std(sp.h),
    spawn_tree = sp.tree / math.max(sp.n, 1), spawn_water = sp.water / math.max(sp.wn, 1),
    spots = spots,
  }
  local f = io.open(OUT, "w"); f:write(minetest.write_json(res)); f:close()
  minetest.request_shutdown("seedscan done", false, 0)
end

minetest.after(1, function()
  minetest.emerge_area({x=-R,y=YMIN,z=-R}, {x=R,y=YMAX,z=R}, function(_, _, remaining)
    if remaining == 0 then minetest.after(0.2, analyze) end
  end)
end)
'''

def find_binary(user):
    if user: return user
    for b in ("luantiserver", "minetestserver", "luanti", "minetest"):
        p = shutil.which(b, path=os.environ.get("PATH", "") + ":/usr/games")
        if p: return p
    for b in ():
        p = shutil.which(b)
        if p: return p
    sys.exit("Luanti/Minetest not found. Install it (Termux: pkg install luanti) or use --minetest PATH")

def scan_seed(binary, seed, radius, game, mapgen, timeout, step):
    tmp = tempfile.mkdtemp(prefix="seedscan_")
    try:
        world = os.path.join(tmp, "world")
        mod = os.path.join(world, "worldmods", "seedscan")
        os.makedirs(mod)
        open(os.path.join(mod, "mod.conf"), "w").write("name = seedscan\n")
        open(os.path.join(mod, "init.lua"), "w").write(LUA)
        open(os.path.join(world, "world.mt"), "w").write(
            "gameid = %s\nworld_name = scan\nbackend = sqlite3\nplayer_backend = sqlite3\n"
            "auth_backend = sqlite3\nmod_storage_backend = sqlite3\nload_mod_seedscan = true\n" % game)
        out = os.path.join(world, "seedscan_out.json")
        conf = os.path.join(tmp, "scan.conf")
        open(conf, "w").write(
            "fixed_map_seed = %d\nmg_name = %s\nserver_announce = false\nport = %d\n"
            "seedscan_radius = %d\nseedscan_step = %d\nseedscan_out = %s\n"
            % (seed, mapgen, random.randint(31000, 39000), radius, step, out))
        cmd = [binary]
        if not os.path.basename(binary).endswith("server"): cmd.append("--server")
        cmd += ["--world", world, "--gameid", game, "--config", conf]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=timeout, text=True)
            log = r.stdout or ""
        except subprocess.TimeoutExpired as e:
            so = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            log = "TIMEOUT after %ds\n%s" % (timeout, so)
        if os.path.exists(out):
            return json.load(open(out))
        print("\n   command: " + " ".join(cmd))
        print("   " + "\n   ".join(log.strip().splitlines()[-15:]))
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# ---------- scoring ----------
def hi(x, bad, good):  return max(0.0, min(1.0, (x - bad) / (good - bad)))
def lo(x, good, bad):  return max(0.0, min(1.0, (bad - x) / (bad - good)))

WANTS = {
    "flat":         ("flat terrain overall",        lambda m: lo(m["slope"], 0.4, 3.0)),
    "mountains":    ("tall, rugged mountains",      lambda m: 0.5*hi(m["max_h"], 40, 120) + 0.5*hi(m["std_h"], 6, 25)),
    "water":        ("lots of water (lakes/ocean)", lambda m: hi(m["water"], 0.05, 0.40)),
    "islands":      ("islands: much water, land spawn", lambda m: 0.7*hi(m["water"], 0.25, 0.6) + 0.3*(1.0 if m["spawn_h"] >= 1 else 0.0)),
    "forest":       ("dense trees",                 lambda m: hi(m["tree"], 0.05, 0.40)),
    "grassland":    ("green grass land",            lambda m: hi(m["grass"], 0.3, 0.8)),
    "desert":       ("sand / desert",               lambda m: hi(m["sand"], 0.1, 0.6)),
    "snow":         ("snow / ice",                  lambda m: hi(m["snow"], 0.05, 0.5)),
    "caves":        ("many caves",                  lambda m: hi(m["cave"], 0.01, 0.15)),
    "spawn-flat":   ("flat spawn area",             lambda m: lo(m["spawn_std"], 0.5, 4.0)),
    "spawn-water":  ("water near spawn",            lambda m: hi(m["spawn_water"], 0.02, 0.2)),
    "spawn-forest": ("trees near spawn",            lambda m: hi(m["spawn_tree"], 0.05, 0.3)),
    "spawn-land":   ("spawn on dry land",           lambda m: 1.0 if m["spawn_h"] >= 1 else 0.0),
}
WANTS["survival"] = ("good survival start (flat+trees+water+grass at spawn)", lambda m: (
    WANTS["spawn-flat"][1](m) + WANTS["spawn-forest"][1](m) + WANTS["spawn-water"][1](m)
    + WANTS["grassland"][1](m) + WANTS["spawn-land"][1](m)) / 5)

def score(m, wants):
    parts = []
    for w in wants:
        neg = w.startswith("no-") or w.startswith("not-")
        key = w.split("-", 1)[1] if neg else w
        if key not in WANTS: sys.exit("Unknown want '%s'. Options: %s" % (w, ", ".join(WANTS)))
        s = WANTS[key][1](m)
        parts.append(1 - s if neg else s)
    return 100 * sum(parts) / len(parts)

def main():
    ap = argparse.ArgumentParser(description="Minetest seed finder")
    ap.add_argument("--want", help="comma list, e.g. flat,forest,no-water,spawn-flat")
    ap.add_argument("--seeds", nargs="*", type=int, help="specific seeds to scan")
    ap.add_argument("--count", type=int, default=10, help="random seeds to scan")
    ap.add_argument("--radius", type=int, default=160, help="scan radius in nodes (bigger = slower)")
    ap.add_argument("--step", type=int, default=4, help="sampling step in nodes")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--game", default="minetest", help="game id (minetest = Minetest Game)")
    ap.add_argument("--mapgen", default="v7")
    ap.add_argument("--minetest", help="path to luanti/minetest binary")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--rank-only", action="store_true", help="only rank cached seeds")
    ap.add_argument("--all-spots", action="store_true", help="print every location found")
    a = ap.parse_args()

    if not a.want:
        print("What do you want? Options:")
        for k, (d, _) in WANTS.items(): print("  %-13s %s" % (k, d))
        print("  (prefix with no- to avoid, e.g. no-water)")
        a.want = input("Your choice (comma separated): ").strip()
    wants = [w.strip().lower() for w in a.want.split(",") if w.strip()]

    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    tag = "%s|%s|r%d" % (a.mapgen, a.game, a.radius)

    if not a.rank_only:
        binary = find_binary(a.minetest)
        seeds = a.seeds or [random.randint(1, 2**40) for _ in range(a.count)]
        for i, sd in enumerate(seeds, 1):
            key = "%s|%d" % (tag, sd)
            if key in cache and "spots" in cache[key]: continue
            t = time.time()
            print("[%d/%d] checking seed %d ..." % (i, len(seeds), sd), end=" ", flush=True)
            m = scan_seed(binary, sd, a.radius, a.game, a.mapgen, a.timeout, a.step)
            if m:
                cache[key] = m
                json.dump(cache, open(CACHE, "w"))
                print("ok (%.0fs, quick score %.0f)" % (time.time() - t, score(m, wants)))
            else:
                print("failed")
        pool = {k: v for k, v in cache.items() if k.split("|")[-1] in {str(s) for s in seeds}
                and k.startswith(tag)}
    else:
        pool = {k: v for k, v in cache.items() if k.startswith(tag)}

    ranked = sorted(pool.items(), key=lambda kv: -score(kv[1], wants))[:a.top]
    print("\nseeds for: %s" % ", ".join(wants))
    for r, (k, m) in enumerate(ranked, 1):
        print("\n#%d  seed %s   match %.0f%%" % (r, k.split("|")[-1], score(m, wants)))
        print("   height avg %.0f (max %d, min %d), roughness %.1f, spawn y=%d"
              % (m["avg_h"], m["max_h"], m["min_h"], m["slope"], m["spawn_h"]))
        print("   water %.0f%%  trees %.0f%%  grass %.0f%%  sand %.0f%%  snow %.0f%%  caves %.0f%%"
              % tuple(100 * m[x] for x in ("water", "tree", "grass", "sand", "snow", "cave")))
        spots = m.get("spots")
        if not spots:
            print("   (no coordinates cached - rescan this seed)")
            continue
        show = ["spawn"]
        for w in wants:
            key = w.split("-", 1)[1] if w.startswith(("no-", "not-")) else w
            if w.startswith(("no-", "not-")): continue
            key = key.replace("spawn-", "")
            show.append({"mountains": "peak", "forest": "tree", "grassland": "grass",
                         "desert": "sand", "islands": "water", "flat": "spawn"}.get(key, key))
        if a.all_spots: show = ["spawn", "peak", "low", "water", "tree", "grass", "sand", "snow", "stone", "cave"]
        seen = set()
        print("   Places (teleport with /teleport x,y,z):")
        for name in show:
            if name in seen or name not in spots: continue
            seen.add(name)
            s = spots[name]
            print("     %-6s %d,%d,%d" % (name, s["x"], s["y"], s["z"]))
    if not ranked: print("No results (nothing scanned/cached).")
    print("\nUse it: set the seed when creating the world (or fixed_map_seed in minetest.conf), mapgen %s." % a.mapgen)
    print("To teleport in game: /grantme all  then  /teleport x,y,z  (coordinates are nearest to spawn).")

if __name__ == "__main__":
    main()
