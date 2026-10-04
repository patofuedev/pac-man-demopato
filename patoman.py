#!/usr/bin/env python3
"""PATOMAN - un Pac-Man con un pato, en pixel art retro. Requiere pygame."""
import array
import math
import random
import sys

import pygame

T, COLS, ROWS, OY = 24, 19, 21, 40
W, H = COLS * T, ROWS * T + OY + 30
MAP = [
    "###################",
    "#........#........#",
    "#o##.###.#.###.##o#",
    "#.................#",
    "#.##.#.#####.#.##.#",
    "#....#...#...#....#",
    "####.###.#.###.####",
    "####.#.......#.####",
    "####.#.##-##.#.####",
    ".......#GGG#.......",
    "####.#.#####.#.####",
    "####.#.......#.####",
    "####.#.#####.#.####",
    "#........#........#",
    "#.##.###.#.###.##.#",
    "#o.#.....P.....#.o#",
    "##.#.#.#####.#.#.##",
    "#....#...#...#....#",
    "#.######.#.######.#",
    "#.................#",
    "###################",
]
DIR = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # izq, der, arriba, abajo (i^1 = opuesto)
FOX_COLORS = ["#e8312f", "#ff8fd0", "#2fd8e8", "#ff9a20"]
KEYS = {
    pygame.K_LEFT: 0, pygame.K_a: 0, pygame.K_RIGHT: 1, pygame.K_d: 1,
    pygame.K_UP: 2, pygame.K_w: 2, pygame.K_DOWN: 3, pygame.K_s: 3,
}


def centered(v):
    return v % T < 1e-3 or v % T > T - 1e-3


# ---------- Sprites ----------
def make_sprite(rows, pal):
    surf = pygame.Surface((len(rows[0]), len(rows)), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in pal:
                surf.set_at((x, y), pygame.Color(pal[ch]))
    return pygame.transform.scale(surf, (T, T))


DUCK_PAL = {"y": "#ffd800", "o": "#ff7a00", "k": "#101010", "w": "#fff6c0"}


def duck_frame(open_beak, feet_a):
    rows = [
        "....yyyy....",
        "...yyyyyy...",
        "...yykyyy...",
        "...yyyyyooo." if open_beak else "...yyyyyoo..",
        "...yyyyyooo." if open_beak else "...yyyyyyo..",
        "....yyyy....",
        "..yyyyyy....",
        ".yyyyyyyyy..",
        "yyywwyyyyy..",
        ".yywwyyyyy..",
        "..yyyyyyy...",
        "...o..o....." if feet_a else "....o.o.....",
    ]
    return make_sprite(rows, DUCK_PAL)


FOX_BODY = [
    "..c......c..",
    ".ccc....ccc.",
    ".cccccccccc.",
    ".cwwccccwwc.",
    ".cwkccccwkc.",
    ".cccccccccc.",
    "..ccwwwwcc..",
    "..cwwkkwwc..",
    ".cccwwwwccc.",
    ".cccccccccc.",
    ".cccccccccc.",
]


def fox_frame(color, f, eyes="#ffffff"):
    rows = FOX_BODY + [".cc.cc.cc.c." if f else "c.cc.cc.cc.c"]
    return make_sprite(rows, {"c": color, "w": eyes, "k": "#101010"})


def build_sprites():
    s = {}
    s["duck"] = [duck_frame(True, True), duck_frame(False, False)]
    s["fox"] = [[fox_frame(c, 0), fox_frame(c, 1)] for c in FOX_COLORS]
    s["scared"] = [fox_frame("#2121de", 0), fox_frame("#2121de", 1)]
    s["flash"] = [fox_frame("#f4f4f4", 0, "#d02020"), fox_frame("#f4f4f4", 1, "#d02020")]
    s["eyes"] = make_sprite([
        "............", "............", "............",
        "..ww....ww..", ".wwkw..wwkw.", ".wwww..wwww.", "..ww....ww..",
        "............", "............", "............", "............", "............",
    ], {"w": "#ffffff", "k": "#2040ff"})
    return s


# ---------- Audio ----------
def tone(f1, dur, f2=None, wave="square", vol=0.15):
    rate = 22050
    n = int(rate * dur)
    f2 = f2 or f1
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        f = f1 + (f2 - f1) * i / n
        phase += f / rate
        if wave == "square":
            v = 1.0 if phase % 1 < 0.5 else -1.0
        else:
            v = 2 * (phase % 1) - 1
        env = 1 - i / n
        buf.append(int(v * env * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        self.screen = pygame.display.set_mode((W * 2, H * 2), pygame.RESIZABLE)
        pygame.display.set_caption("PATOMAN")
        self.canvas = pygame.Surface((W, H))
        self.clock = pygame.time.Clock()
        self.spr = build_sprites()
        self.fonts = {}
        self.muted = False
        self.snd = self.load_sounds()
        self.hi = self.load_hi()
        self.state = "title"
        self.frame = 0
        self.want = -1
        self.chomp = False
        self.scanlines = self.make_scanlines()

    # --- utilidades ---
    def load_sounds(self):
        try:
            return {
                "dot1": tone(440, .07), "dot2": tone(330, .07),
                "power": tone(300, .25, 160, "saw", .2), "eat": tone(200, .2, 900),
                "die": tone(700, .9, 80, "saw", .2),
                "start": [tone(f, .15) for f in (262, 330, 392, 523)],
                "win": [tone(f, .15) for f in (523, 659, 784, 1047)],
            }
        except pygame.error:
            return {}

    def play(self, name):
        if self.muted or name not in self.snd:
            return
        s = self.snd[name]
        if isinstance(s, list):  # pequeña melodía: se encadena por el mixer
            self.melody = [(pygame.time.get_ticks() + i * 140, x) for i, x in enumerate(s)]
        else:
            s.play()

    def tick_melody(self):
        m = getattr(self, "melody", [])
        now = pygame.time.get_ticks()
        while m and m[0][0] <= now:
            if not self.muted:
                m[0][1].play()
            m.pop(0)

    def load_hi(self):
        try:
            with open(".patoman-hi") as f:
                return int(f.read())
        except (OSError, ValueError):
            return 0

    def save_hi(self):
        try:
            with open(".patoman-hi", "w") as f:
                f.write(str(self.hi))
        except OSError:
            pass

    def make_scanlines(self):
        s = pygame.Surface((W * 2, H * 2), pygame.SRCALPHA)
        for y in range(0, H * 2, 3):
            pygame.draw.line(s, (0, 0, 0, 45), (0, y), (W * 2, y))
        return s

    def font(self, size):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.SysFont("monospace", size, bold=True)
        return self.fonts[size]

    def text(self, s, x, y, color="#ffffff", align="left", size=11):
        f = self.font(size)
        for col, off in (("#000000", 1), (color, 0)):
            img = f.render(s, False, col)
            r = img.get_rect()
            if align == "center":
                r.midtop = (x, y)
            elif align == "right":
                r.topright = (x, y)
            else:
                r.topleft = (x, y)
            self.canvas.blit(img, (r.x + off, r.y + off))

    # --- mapa ---
    def cell(self, c, r):
        if r < 0 or r >= ROWS:
            return "#"
        return self.grid[r][c % COLS]

    def walkable(self, c, r, door):
        ch = self.cell(c, r)
        return ch != "#" and (ch != "-" or door)

    def build_bfs(self):
        self.dist = [[10 ** 9] * COLS for _ in range(ROWS)]
        self.dist[9][9] = 0
        q = [(9, 9)]
        while q:
            c, r = q.pop(0)
            for dx, dy in DIR:
                nc, nr = (c + dx) % COLS, r + dy
                if 0 <= nr < ROWS and self.walkable(nc, nr, True) and self.dist[nr][nc] == 10 ** 9:
                    self.dist[nr][nc] = self.dist[r][c] + 1
                    q.append((nc, nr))

    def new_level(self):
        self.grid = [list(r) for r in MAP]
        self.dots = sum(r.count(".") + r.count("o") for r in self.grid)
        self.grid[15][9] = " "
        self.build_bfs()
        self.reset_actors()

    def reset_actors(self):
        self.duck = dict(x=9 * T, y=15 * T, dir=-1, speed=2.0, face=1, anim=0.0)
        self.want = -1
        starts = [(9, 7, "normal", 0), (8, 9, "house", 2), (9, 9, "house", 5), (10, 9, "house", 8)]
        self.foxes = [dict(i=i, x=c * T, y=r * T, dir=1 if st == "normal" else -1, state=st,
                           timer=t * 60, fright=False, bob=0.0, speed=1.7)
                      for i, (c, r, st, t) in enumerate(starts)]
        self.fright_t = 0
        self.scatter = True
        self.mode_t = 7 * 60
        self.combo = 0
        self.state, self.state_t = "ready", 120
        self.play("start")

    def new_game(self):
        self.score, self.lives, self.level = 0, 3, 1
        self.new_level()

    # --- movimiento ---
    def advance(self, e, choose, door):
        move = e["speed"]
        while move > 1e-6:
            if centered(e["x"]) and centered(e["y"]):
                e["x"] = round(e["x"] / T) * T
                e["y"] = round(e["y"] / T) * T
                choose(e)
                if e["dir"] < 0:
                    return
                dx, dy = DIR[e["dir"]]
                if not self.walkable(e["x"] // T + dx, e["y"] // T + dy, door()):
                    e["dir"] = -1
                    return
            dx, dy = DIR[e["dir"]]
            mx, my = e["x"] % T, e["y"] % T
            if dx > 0:
                rem = T - mx
            elif dx < 0:
                rem = mx or T
            elif dy > 0:
                rem = T - my
            else:
                rem = my or T
            s = min(move, rem)
            e["x"] += dx * s
            e["y"] += dy * s
            move -= s
            if e["x"] <= -T:
                e["x"] += W
            elif e["x"] >= W:
                e["x"] -= W
            e["x"], e["y"] = round(e["x"], 3), round(e["y"], 3)

    def update_duck(self):
        d = self.duck
        if self.want >= 0 and d["dir"] >= 0 and self.want == d["dir"] ^ 1:
            d["dir"] = self.want

        def choose(e):
            c, r = int(e["x"] // T), int(e["y"] // T)
            w = self.want
            if w >= 0 and self.walkable(c + DIR[w][0], r + DIR[w][1], False):
                e["dir"] = w
            elif e["dir"] >= 0 and not self.walkable(c + DIR[e["dir"]][0], r + DIR[e["dir"]][1], False):
                e["dir"] = -1

        self.advance(d, choose, lambda: False)
        if d["dir"] == 0:
            d["face"] = -1
        elif d["dir"] == 1:
            d["face"] = 1
        if d["dir"] >= 0:
            d["anim"] += d["speed"]
        c = int((d["x"] + T / 2) // T) % COLS
        r = int((d["y"] + T / 2) // T)
        ch = self.grid[r][c] if 0 <= r < ROWS else " "
        if ch == ".":
            self.grid[r][c] = " "
            self.score += 10
            self.dots -= 1
            self.chomp = not self.chomp
            self.play("dot1" if self.chomp else "dot2")
        elif ch == "o":
            self.grid[r][c] = " "
            self.score += 50
            self.dots -= 1
            self.play("power")
            self.fright_t = int(max(2.5, 7 - self.level * .6) * 60)
            self.combo = 0
            for f in self.foxes:
                if f["state"] != "eaten":
                    f["fright"] = True
                    if f["state"] == "normal" and f["dir"] >= 0:
                        f["dir"] ^= 1
        if self.score > self.hi:
            self.hi = self.score

    def fox_target(self, f):
        dc, dr = self.duck["x"] / T, self.duck["y"] / T
        corners = [(17, 0), (1, 0), (17, 20), (1, 20)]
        if self.scatter:
            return corners[f["i"]]
        dx, dy = DIR[self.duck["dir"]] if self.duck["dir"] >= 0 else (0, 0)
        i = f["i"]
        if i == 0:
            return dc, dr
        if i == 1:
            return dc + dx * 4, dr + dy * 4
        if i == 2:
            return dc + math.sin(self.frame / 50) * 6, dr + math.cos(self.frame / 50) * 6
        return (dc, dr) if math.hypot(f["x"] / T - dc, f["y"] / T - dr) > 6 else corners[3]

    def update_fox(self, f):
        base = min(2.0, 1.6 + self.level * .08)
        if f["state"] == "house":
            f["bob"] += .15
            f["y"] = 9 * T + math.sin(f["bob"]) * 3
            f["timer"] -= 1
            if f["timer"] <= 0:
                f["state"], f["y"] = "leaving", 9 * T
            return
        if f["state"] == "leaving":
            s, tx = 1.2, 9 * T
            if f["x"] != tx:
                f["x"] += math.copysign(min(s, abs(tx - f["x"])), tx - f["x"])
            elif f["y"] > 7 * T:
                f["y"] = max(7 * T, f["y"] - s)
            else:
                f["state"], f["dir"] = "normal", random.choice((0, 1))
            return
        f["speed"] = 4 if f["state"] == "eaten" else 1.1 if f["fright"] else base

        def choose(e):
            c, r = int(e["x"] // T), int(e["y"] // T)
            if e["state"] == "eaten" and c == 9 and r == 9:
                e["state"], e["fright"], e["dir"] = "leaving", False, -1
                return
            door = e["state"] == "eaten"
            ok = [i for i in range(4) if self.walkable(c + DIR[i][0], r + DIR[i][1], door)]
            opts = [i for i in ok if i != (e["dir"] ^ 1)] or ok
            if e["state"] == "eaten":
                e["dir"] = min(opts, key=lambda i: self.dist[r + DIR[i][1]][(c + DIR[i][0]) % COLS])
            elif e["fright"]:
                e["dir"] = random.choice(opts)
            else:
                tx, ty = self.fox_target(e)
                e["dir"] = min((i for i in (2, 0, 3, 1) if i in opts),
                               key=lambda i: (c + DIR[i][0] - tx) ** 2 + (r + DIR[i][1] - ty) ** 2)

        self.advance(f, choose, lambda: f["state"] == "eaten")

    def update(self):
        self.frame += 1
        if self.state == "ready":
            self.state_t -= 1
            if self.state_t <= 0:
                self.state = "play"
            return
        if self.state == "dying":
            self.state_t -= 1
            if self.state_t <= 0:
                self.lives -= 1
                if self.lives > 0:
                    self.reset_actors()
                else:
                    self.state = "over"
                    self.save_hi()
            return
        if self.state == "win":
            self.state_t -= 1
            if self.state_t <= 0:
                self.level += 1
                self.new_level()
            return
        if self.state != "play":
            return
        if self.fright_t > 0:
            self.fright_t -= 1
            if self.fright_t == 0:
                for f in self.foxes:
                    f["fright"] = False
        else:
            self.mode_t -= 1
            if self.mode_t <= 0:
                self.scatter = not self.scatter
                self.mode_t = (7 if self.scatter else 20) * 60
                for f in self.foxes:
                    if f["state"] == "normal" and f["dir"] >= 0:
                        f["dir"] ^= 1
        self.update_duck()
        for f in self.foxes:
            self.update_fox(f)
        for f in self.foxes:
            if f["state"] != "normal":
                continue
            if math.hypot(f["x"] - self.duck["x"], f["y"] - self.duck["y"]) < 14:
                if f["fright"]:
                    f["state"], f["fright"] = "eaten", False
                    self.combo += 1
                    self.score += 200 * (1 << (self.combo - 1))
                    self.play("eat")
                else:
                    self.state, self.state_t = "dying", 100
                    self.play("die")
                    return
        if self.dots <= 0:
            self.state, self.state_t = "win", 140
            self.play("win")

    # --- dibujo ---
    def blit_sprite(self, img, x, y, flip=False):
        self.canvas.blit(pygame.transform.flip(img, True, False) if flip else img, (x, y))

    def draw_maze(self):
        cv = self.canvas
        for r in range(ROWS):
            for c in range(COLS):
                ch, x, y = self.grid[r][c], c * T, r * T + OY
                if ch == "#":
                    cv.fill("#0a0a48", (x, y, T, T))
                    col = "#3b6bff"

                    def open_(dc, dr):
                        return 0 <= r + dr < ROWS and self.cell(c + dc, r + dr) != "#"
                    if open_(0, -1): cv.fill(col, (x, y, T, 3))
                    if open_(0, 1): cv.fill(col, (x, y + T - 3, T, 3))
                    if open_(-1, 0): cv.fill(col, (x, y, 3, T))
                    if open_(1, 0): cv.fill(col, (x + T - 3, y, 3, T))
                elif ch == "-":
                    cv.fill("#ff9ad0", (x, y + T // 2 - 2, T, 4))
                elif ch == ".":
                    cv.fill("#ffe9a8", (x + T // 2 - 2, y + T // 2 - 2, 4, 4))
                elif ch == "o" and (self.frame >> 4) % 2 == 0:  # maíz parpadeante
                    cv.fill("#ffb000", (x + 6, y + 6, 12, 12))
                    cv.fill("#fff07a", (x + 8, y + 8, 4, 4))
                    cv.fill("#fff07a", (x + 14, y + 12, 2, 2))
                    cv.fill("#3aa832", (x + 6, y + 16, 12, 2))

    def draw_duck(self):
        d = self.duck
        x, y = d["x"], d["y"] + OY
        if self.state == "dying":
            p = 1 - self.state_t / 100
            size = max(1, int(T * (1 - p)))
            img = pygame.transform.rotate(pygame.transform.scale(self.spr["duck"][0], (size, size)), p * 360 * 3)
            self.canvas.blit(img, img.get_rect(center=(x + T // 2, y + T // 2)))
            return
        self.blit_sprite(self.spr["duck"][int(d["anim"] // 5) % 2], x, y, d["face"] < 0)

    def draw_foxes(self):
        k = (self.frame >> 3) % 2
        for f in self.foxes:
            x, y = f["x"], f["y"] + OY
            if f["state"] == "eaten":
                img = self.spr["eyes"]
            elif f["fright"]:
                flash = self.fright_t < 120 and (self.frame >> 4) % 2
                img = self.spr["flash" if flash else "scared"][k]
            else:
                img = self.spr["fox"][f["i"]][k]
            self.blit_sprite(img, x, y)

    def draw_hud(self):
        self.text("1UP", 8, 6, "#ff9ad0")
        self.text(f"{self.score:06d}", 8, 20)
        self.text("RECORD", W // 2, 6, "#ff9ad0", "center")
        self.text(f"{self.hi:06d}", W // 2, 20, align="center")
        self.text(f"NIVEL {self.level}", W - 8, 6, "#ff9ad0", "right")
        for i in range(self.lives - (1 if self.state == "dying" else 0)):
            self.canvas.blit(self.spr["duck"][1], (6 + i * 26, H - 28))
        self.text("M: SONIDO " + ("OFF" if self.muted else "ON"), W - 8, H - 18, "#666677", "right", 9)

    def overlay(self, lines):
        s = pygame.Surface((W, 6 * T), pygame.SRCALPHA)
        s.fill((0, 0, 0, 190))
        self.canvas.blit(s, (0, OY + 7 * T))
        for i, (txt, col, size) in enumerate(lines):
            self.text(txt, W // 2, OY + 7 * T + 18 + i * 28, col, "center", size)

    def draw(self):
        cv = self.canvas
        cv.fill("#000000")
        if self.state == "title":
            self.text("PATOMAN", W // 2, 80, "#ffd800", "center", 40)
            big = pygame.transform.scale(self.spr["duck"][(self.frame >> 4) % 2], (96, 96))
            cv.blit(big, (W // 2 - 48, 150))
            for i, f in enumerate(self.spr["fox"]):
                cv.blit(pygame.transform.scale(f[(self.frame >> 3) % 2], (48, 48)), (60 + i * 88, 270))
            self.text("COME TODAS LAS MIGAS", W // 2, 350, "#ffe9a8", "center")
            self.text("Y EVITA A LOS ZORROS", W // 2, 372, "#ffe9a8", "center")
            self.text("EL MAIZ TE DA PODER", W // 2, 394, "#ffb000", "center")
            self.text("FLECHAS / WASD", W // 2, 440, "#7fa0ff", "center", 10)
            if (self.frame >> 5) % 2 == 0:
                self.text("PULSA ESPACIO", W // 2, 478, "#ffffff", "center", 18)
            self.text(f"RECORD {self.hi:06d}", W // 2, 530, "#ff9ad0", "center")
            return
        self.draw_maze()
        self.draw_foxes()
        self.draw_duck()
        self.draw_hud()
        if self.state == "ready":
            self.overlay([("JUGADOR 1", "#00e8e8", 14), ("¡LISTO!", "#ffd800", 22)])
        elif self.state == "win":
            self.overlay([("¡NIVEL SUPERADO!", "#ffd800", 18), ("CUAC CUAC CUAC", "#ffffff", 14)])
        elif self.state == "over":
            self.overlay([("FIN DEL JUEGO", "#ff3030", 22), ("ESPACIO PARA REPETIR", "#ffffff", 14)])
        elif self.state == "paused":
            self.overlay([("PAUSA", "#ffffff", 22), ("PULSA P", "#7fa0ff", 14)])

    def present(self):
        sw, sh = self.screen.get_size()
        s = min(sw / W, sh / H)
        size = (int(W * s), int(H * s))
        img = pygame.transform.scale(self.canvas, size)  # sin suavizado: píxeles nítidos
        self.screen.fill("#050510")
        pos = ((sw - size[0]) // 2, (sh - size[1]) // 2)
        self.screen.blit(img, pos)
        sl = pygame.transform.scale(self.scanlines, size)
        self.screen.blit(sl, pos)
        pygame.display.flip()

    # --- bucle ---
    def run(self):
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.save_hi()
                    return
                if e.type != pygame.KEYDOWN:
                    continue
                if e.key == pygame.K_ESCAPE:
                    self.save_hi()
                    return
                if e.key in KEYS:
                    self.want = KEYS[e.key]
                elif e.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if self.state in ("title", "over"):
                        self.new_game()
                elif e.key == pygame.K_p:
                    if self.state == "play":
                        self.state = "paused"
                    elif self.state == "paused":
                        self.state = "play"
                elif e.key == pygame.K_m:
                    self.muted = not self.muted
                elif e.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
            if self.state == "title":
                self.frame += 1
            else:
                self.update()
            self.tick_melody()
            self.draw()
            self.present()
            self.clock.tick(60)


if __name__ == "__main__":
    Game().run()
    pygame.quit()
    sys.exit()
