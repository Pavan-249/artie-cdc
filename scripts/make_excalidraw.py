"""Generate .excalidraw files for the blog diagrams.

Run: python scripts/make_excalidraw.py
Writes docs/diagrams/*.excalidraw. Open each at https://excalidraw.com, then export PNG/SVG.
"""
import json
import pathlib
import random
import time

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)
NOW = int(time.time() * 1000)

DARK = "#1e1e1e"


def rnd():
    return random.randint(1, 2_000_000_000)


class Scene:
    def __init__(self):
        self.elements = []

    def _eid(self):
        return f"el{rnd()}"

    def box(self, x, y, w, h, text, bg="#ffffff", stroke=DARK, font=16, align="center"):
        rid, tid = self._eid(), self._eid()
        self.elements.append({
            "id": rid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 3}, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False,
            "boundElements": [{"type": "text", "id": tid}], "updated": NOW, "link": None, "locked": False,
        })
        self.elements.append({
            "id": tid, "type": "text", "x": x + 6, "y": y + h / 2 - font, "width": w - 12, "height": 2 * font,
            "angle": 0, "strokeColor": stroke, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False, "boundElements": [],
            "updated": NOW, "link": None, "locked": False, "text": text, "fontSize": font,
            "fontFamily": 2, "textAlign": align, "verticalAlign": "middle", "baseline": font - 2,
            "containerId": rid, "originalText": text, "lineHeight": 1.25,
        })
        return rid

    def label(self, x, y, text, size=16, color=DARK, align="left", w=260):
        tid = self._eid()
        self.elements.append({
            "id": tid, "type": "text", "x": x, "y": y, "width": w, "height": size * 1.4,
            "angle": 0, "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False, "boundElements": [],
            "updated": NOW, "link": None, "locked": False, "text": text, "fontSize": size,
            "fontFamily": 2, "textAlign": align, "verticalAlign": "top", "baseline": size - 2,
            "containerId": None, "originalText": text, "lineHeight": 1.25,
        })
        return tid

    def arrow(self, x1, y1, x2, y2, start=None, end=None, dashed=False, stroke=DARK, label=None, label_dy=-22):
        aid = self._eid()
        el = {
            "id": aid, "type": "arrow", "x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1,
            "angle": 0, "strokeColor": stroke, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "dashed" if dashed else "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 2}, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False, "boundElements": [],
            "updated": NOW, "link": None, "locked": False, "points": [[0, 0], [x2 - x1, y2 - y1]],
            "lastCommittedPoint": None,
            "startBinding": {"elementId": start, "focus": 0, "gap": 6} if start else None,
            "endBinding": {"elementId": end, "focus": 0, "gap": 6} if end else None,
            "startArrowhead": None, "endArrowhead": "arrow",
        }
        self.elements.append(el)
        for rid in (start, end):
            if rid:
                self._bind(rid, aid)
        if label:
            self.label((x1 + x2) / 2 - 90, (y1 + y2) / 2 + label_dy, label, size=13, color=stroke, align="center", w=180)
        return aid

    def poly_arrow(self, pts, dashed=False, stroke=DARK):
        aid = self._eid()
        x0, y0 = pts[0]
        rel = [[px - x0, py - y0] for px, py in pts]
        self.elements.append({
            "id": aid, "type": "arrow", "x": x0, "y": y0,
            "width": max(p[0] for p in rel) - min(p[0] for p in rel),
            "height": max(p[1] for p in rel) - min(p[1] for p in rel),
            "angle": 0, "strokeColor": stroke, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "dashed" if dashed else "solid", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 2}, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False, "boundElements": [],
            "updated": NOW, "link": None, "locked": False, "points": rel, "lastCommittedPoint": None,
            "startBinding": None, "endBinding": None, "startArrowhead": None, "endArrowhead": "arrow",
        })
        return aid

    def region(self, x, y, w, h, label, stroke=DARK):
        rid = self._eid()
        self.elements.append({
            "id": rid, "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "angle": 0, "strokeColor": stroke, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "dashed", "roughness": 1, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": {"type": 3}, "seed": rnd(),
            "version": 1, "versionNonce": rnd(), "isDeleted": False, "boundElements": [],
            "updated": NOW, "link": None, "locked": False,
        })
        self.label(x + 12, y + 8, label, size=13, color=stroke, align="left", w=240)
        return rid

    def _bind(self, rid, aid):
        for el in self.elements:
            if el["id"] == rid:
                el["boundElements"].append({"type": "arrow", "id": aid})

    def save(self, name, bg="#ffffff"):
        doc = {
            "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
            "elements": self.elements, "appState": {"gridSize": None, "viewBackgroundColor": bg},
            "files": {},
        }
        (OUT / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        print("wrote", name, f"({len(self.elements)} elements)")


# palette
PG = ("#a5d8ff", "#1971c2")
WAL = ("#d0bfff", "#6741d9")
WORKER = ("#b2f2bb", "#2f9e44")
CH = ("#ffec99", "#f08c00")
DASH = ("#99e9f2", "#0c8599")
RED = ("#ffc9c9", "#e03131")


def architecture():
    s = Scene()
    s.label(40, 40, "Local Postgres to ClickHouse CDC", size=24, w=700)
    y, w, h = 150, 170, 90
    xs = [40, 260, 480, 700, 920, 1140]
    boxes = [
        ("Postgres\ntrades table", PG),
        ("Logical WAL\nstream", WAL),
        ("wal2json\nreplication slot", WAL),
        ("Python\nCDC worker", WORKER),
        ("ClickHouse\nReplacingMergeTree", CH),
        ("Streamlit\ndashboard", DASH),
    ]
    ids = []
    for x, (label, (bg, st)) in zip(xs, boxes):
        ids.append(s.box(x, y, w, h, label, bg=bg, stroke=st))
    for a, b, x in zip(ids, ids[1:], xs):
        s.arrow(x + w, y + h / 2, x + w + 50, y + h / 2, start=a, end=b)
    # dashed write-back loop from dashboard to postgres
    s.poly_arrow([(1225, y + h), (1225, y + h + 110), (125, y + h + 110), (125, y + h)],
                 dashed=True, stroke=DASH[1])
    s.label(430, y + h + 118, "The dashboard changes only the source. ClickHouse updates after CDC.",
            size=14, color=DASH[1], align="center", w=560)
    s.save("architecture.excalidraw")


def version_lifecycle():
    s = Scene()
    s.label(40, 30, "ClickHouse keeps every version, FINAL resolves the latest", size=22, w=820)
    vx, vw, vh = 60, 250, 74
    rows = [
        ("INSERT   trade_id 1003\nrisk 50   __cdc_updated_at 10:00:00\n__cdc_is_deleted 0", CH),
        ("UPDATE   trade_id 1003\nrisk 67   __cdc_updated_at 10:05:00\n__cdc_is_deleted 0", CH),
        ("UPDATE   trade_id 1003\nrisk 82   __cdc_updated_at 10:09:00  (latest)\n__cdc_is_deleted 0", CH),
    ]
    ids = []
    for i, (label, (bg, st)) in enumerate(rows):
        ids.append(s.box(vx, 110 + i * (vh + 16), vw, vh, label, bg=bg, stroke=st, font=13))
    result = s.box(560, 150, 280, 120,
                   "SELECT * FROM trades FINAL\nWHERE __cdc_is_deleted = 0\n\ntrade_id 1003, risk 82\n(latest version wins)",
                   bg=WORKER[0], stroke=WORKER[1], font=13)
    s.arrow(vx + vw, 110 + (vh + 16) + vh / 2, 560, 210, start=ids[1], end=result,
            label="FINAL keeps\nmax(__cdc_updated_at)")
    # tombstone example
    ty = 400
    tomb = s.box(vx, ty, vw, vh, "DELETE   trade_id 1009\n__cdc_is_deleted 1\n(tombstone)", bg=RED[0], stroke=RED[1], font=13)
    excl = s.box(560, ty, 280, vh, "WHERE __cdc_is_deleted = 0\nrow is excluded from the view", bg="#ffffff", stroke=RED[1], font=13)
    s.arrow(vx + vw, ty + vh / 2, 560, ty + vh / 2, start=tomb, end=excl, dashed=True, stroke=RED[1], label="filtered out")
    s.save("version-lifecycle.excalidraw")


def two_phase_worker():
    s = Scene()
    s.label(40, 30, "The CDC worker runs in two phases", size=22, w=620)
    # phase 1 lane
    s.label(40, 90, "Phase 1: snapshot backfill", size=15, color=WORKER[1])
    w1 = s.box(40, 120, 200, 80, "Python CDC worker\nread trades", bg=WORKER[0], stroke=WORKER[1], font=14)
    ch1 = s.box(540, 120, 220, 80, "ClickHouse\nappend rows tagged SNAPSHOT", bg=CH[0], stroke=CH[1], font=13)
    s.arrow(240, 160, 540, 160, start=w1, end=ch1, label="bulk insert")
    # phase 2 lane
    s.label(40, 270, "Phase 2: live stream", size=15, color=WAL[1])
    pg = s.box(40, 300, 200, 90, "Postgres\nWAL via slot (wal2json)", bg=PG[0], stroke=PG[1], font=13)
    w2 = s.box(300, 300, 200, 90, "Python CDC worker\ndecode each change", bg=WORKER[0], stroke=WORKER[1], font=13)
    ch2 = s.box(560, 300, 220, 90, "ClickHouse\nappend INSERT / UPDATE / DELETE\nversion rows", bg=CH[0], stroke=CH[1], font=12)
    s.arrow(240, 345, 300, 345, start=pg, end=w2)
    s.arrow(500, 345, 560, 345, start=w2, end=ch2)
    s.save("two-phase-worker.excalidraw")


def artie_architecture():
    s = Scene()
    s.label(40, 32, "How Artie replicates Postgres to ClickHouse", size=22, w=900)
    # managed boundary drawn first so it sits behind the boxes
    s.region(280, 150, 735, 150, "Artie (fully managed)", stroke="#0c8599")
    y, h = 185, 80
    pg = s.box(40, y, 160, h, "Postgres\nwrite ahead log", bg=PG[0], stroke=PG[1], font=13)
    rd = s.box(300, y, 170, h, "Artie Reader\nreads the log", bg=WORKER[0], stroke=WORKER[1], font=13)
    kf = s.box(540, y, 195, h, "Kafka\none topic per table", bg=WAL[0], stroke=WAL[1], font=13)
    tf = s.box(800, y, 200, h, "Artie Transfer\nschema check, merge", bg=WORKER[0], stroke=WORKER[1], font=13)
    ch = s.box(1075, y, 190, h, "ClickHouse\nReplacingMergeTree", bg=CH[0], stroke=CH[1], font=13)
    s.arrow(200, y + h / 2, 300, y + h / 2, start=pg, end=rd)
    s.arrow(470, y + h / 2, 540, y + h / 2, start=rd, end=kf)
    s.arrow(735, y + h / 2, 800, y + h / 2, start=kf, end=tf)
    s.arrow(1000, y + h / 2, 1075, y + h / 2, start=tf, end=ch)
    s.label(40, 330,
            "Reader tails the log, Kafka buffers each table, Transfer merges into the destination. "
            "Exactly once, sub-minute latency, automatic schema changes, and Artie never stores your data.",
            size=14, color=DARK, align="left", w=1180)
    s.save("artie-architecture.excalidraw")


if __name__ == "__main__":
    architecture()
    version_lifecycle()
    two_phase_worker()
    artie_architecture()
