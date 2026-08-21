"""Single source of truth for every published number: the scorecard SVG, the
inference-compute curve, and both README AUTOGEN blocks — all rendered from
the committed metrics files. CI regenerates and `git diff --exit-code` fails
the build on any drift.

Two marker pairs, two independent blocks: AUTOGEN reads metrics.jsonl (the
v1.0 scorecard), AUTOGEN:TTC reads metrics-ttc.jsonl (the inference-compute
study). They never overlap, so a change to one cannot perturb the other.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from mutationlab.defects import BEHAVIORAL_PROBED_CLASSES
from mutationlab.runner import LINE_TOLERANCE

AUTOGEN_BEGIN = "<!-- AUTOGEN:BEGIN — rendered by report.py from metrics.jsonl; do not edit by hand -->"
AUTOGEN_END = "<!-- AUTOGEN:END -->"
TTC_BEGIN = "<!-- AUTOGEN:TTC:BEGIN — rendered by report.py from metrics-ttc.jsonl; do not edit by hand -->"
TTC_END = "<!-- AUTOGEN:TTC:END -->"
DISCLAIMER = "rule-based reviewer — harness conformance, not any model's catch rate"

_BLUE = "#2563eb"
_RED = "#dc2626"
_GREEN = "#059669"
_AMBER = "#b45309"
_VIOLET = "#7c3aed"
_INK = "#111111"
_MUTED = "#6b7280"

# Display names for the pre-registered arms. Unknown ids fall through to the
# raw arm id rather than being dropped: an unpublished arm is worse than an
# ugly label.
_ARM_LABELS = {
    "independent": "A1 independent",
    "correlated": "A2 correlated (shared stream)",
    "below-chance": "A3 below-chance",
}


@dataclass(frozen=True)
class Metrics:
    per_class: list[dict[str, object]]
    summary: dict[str, object]


def load_metrics(path: Path) -> Metrics:
    per_class: list[dict[str, object]] = []
    summary: dict[str, object] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["kind"] == "class":
                per_class.append(row)
            else:
                summary = row
    return Metrics(per_class=per_class, summary=summary)


def render_scorecard_svg(metrics: Metrics) -> str:
    """Horizontal bars: one row per defect class, hit fraction filled."""
    rows = sorted(metrics.per_class, key=lambda r: str(r["class_id"]))
    width = 760
    row_h, top, bottom, left, right = 30, 56, 96, 240, 30
    height = top + row_h * len(rows) + bottom
    bar_w = width - left - right

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="monospace" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="22" font-size="14" fill="#111111">'
        "scorecard — planted defects found per class (rule-based reviewer)</text>",
        f'<text x="{left}" y="40" fill="#6b7280">'
        f"HIT = planted class within ±{LINE_TOLERANCE} lines of the planted line</text>",
    ]
    for i, row in enumerate(rows):
        y = top + i * row_h
        mutants = int(row["mutants"])  # type: ignore[arg-type]
        hits = int(row["hits"])  # type: ignore[arg-type]
        frac = hits / mutants if mutants else 0.0
        full = hits == mutants
        color = _BLUE if full else _RED
        parts.append(
            f'<text x="{left - 10}" y="{y + 19}" text-anchor="end" fill="#111111">'
            f"{row['class_id']}</text>"
        )
        # A miss row must LOOK like a miss: red outline and red count, even
        # (especially) when the bar is empty — 'the red row' has to be true
        # as rendered, not only as intended.
        outline = "#e5e7eb" if full else _RED
        parts.append(
            f'<rect x="{left}" y="{y + 6}" width="{bar_w}" height="16" '
            f'fill="#f1f5f9" stroke="{outline}"/>'
        )
        if frac > 0:
            parts.append(
                f'<rect x="{left}" y="{y + 6}" width="{bar_w * frac:.1f}" height="16" '
                f'fill="{color}"/>'
            )
        count_color = "#111111" if full else _RED
        parts.append(
            f'<text x="{left + bar_w + 6}" y="{y + 19}" fill="{count_color}">'
            f"{hits}/{mutants}</text>"
        )
    clean_files = int(metrics.summary["clean_files"])  # type: ignore[arg-type]
    false_alarms = int(metrics.summary["false_alarms"])  # type: ignore[arg-type]
    base_y = top + row_h * len(rows) + 24
    parts.append(
        f'<text x="{left}" y="{base_y}" fill="{_GREEN}" font-weight="bold">'
        f"false-alarm arm: {false_alarms} finding(s) on {clean_files} byte-identical "
        "clean control files</text>"
    )
    parts.append(
        f'<text x="{left}" y="{base_y + 20}" fill="#991b1b">{DISCLAIMER}</text>'
    )
    parts.append(
        f'<text x="{left}" y="{base_y + 40}" fill="#6b7280">'
        "the red row is a DELIBERATE blind spot — a scorecard that cannot show "
        "a miss teaches nothing</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_claims(metrics: Metrics) -> str:
    total_mutants = int(metrics.summary["total_mutants"])  # type: ignore[arg-type]
    total_hits = int(metrics.summary["total_hits"])  # type: ignore[arg-type]
    clean_files = int(metrics.summary["clean_files"])  # type: ignore[arg-type]
    false_alarms = int(metrics.summary["false_alarms"])  # type: ignore[arg-type]
    spurious = int(metrics.summary.get("spurious_on_mutants", 0))  # type: ignore[union-attr]
    n_classes = len(metrics.per_class)
    missed = [r for r in metrics.per_class if int(r["hits"]) < int(r["mutants"])]  # type: ignore[arg-type]
    missed_names = ", ".join(str(r["class_id"]) for r in missed) or "none"

    lines = [
        "| claim | number (regenerated by CI) | how measured | honest caveat |",
        "|---|---|---|---|",
        (
            "| The harness plants real defects and scores them at the right line "
            f"| **{total_hits}/{total_mutants} planted defects flagged at the "
            f"planted line (±{LINE_TOLERANCE}), across {n_classes} classes** "
            "| every applicable "
            "(defect, file) pair injected once; the sealed answer key is generated "
            "with the batch; the bundled rule-based reviewer replays in CI | "
            "HARNESS CONFORMANCE, not a catch rate — the bundled reviewer is "
            "deterministic rules, and its blind spot is deliberate (see next row) |"
        ),
        (
            "| A miss looks like a miss "
            f"| **missed class(es): {missed_names}** | the bundled reviewer ships "
            "with NO rule for that class, so the scorecard contains a real MISS "
            "row | a harness whose demo scores 100% teaches nothing about what "
            "failure output looks like; the blind spot is documented in "
            "reviewer.py |"
        ),
        (
            "| Crying wolf scores zero "
            f"| **{false_alarms} finding(s) on {clean_files} byte-identical clean "
            f"control files; {spurious} spurious finding(s) on mutants** | every "
            "fixture is included unmodified in the batch; any finding on it counts "
            "against the reviewer, and findings on mutants that do not match the "
            "planted defect are counted as spurious | with a rule-based "
            "reviewer both are 0 by construction — the arms exist so that a LIVE "
            "reviewer cannot score by flagging everything |"
        ),
        (
            "| The planted defects are behavioral, not cosmetic "
            f"| **{len(BEHAVIORAL_PROBED_CLASSES)} classes proven by executable "
            f"probes** ({', '.join(BEHAVIORAL_PROBED_CLASSES)}) | "
            "tests exec the mutated module and drive the bug: pass on clean, "
            "misbehave on mutant | the other classes are structural patterns "
            "whose harm is documented per class in defects.py rather than "
            "executed |"
        ),
    ]
    return "\n".join(lines)


def inject_readme(
    readme_path: Path,
    block: str,
    begin_marker: str = AUTOGEN_BEGIN,
    end_marker: str = AUTOGEN_END,
) -> None:
    """Replace one marked block in place, leaving every other byte alone."""
    text = readme_path.read_text(encoding="utf-8")
    begin = text.index(begin_marker)
    end = text.index(end_marker) + len(end_marker)
    new = (
        text[:begin] + begin_marker + "\n\n" + block + "\n\n" + end_marker + text[end:]
    )
    with readme_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)


# --- the inference-compute study -------------------------------------------


@dataclass(frozen=True)
class TtcMetrics:
    params: dict[str, object]
    curve: list[dict[str, object]]
    wall: list[dict[str, object]]

    @property
    def arms(self) -> list[str]:
        return [str(a) for a in self.params["arms"]]  # type: ignore[union-attr]

    @property
    def k_values(self) -> list[int]:
        return [int(k) for k in self.params["k_values"]]  # type: ignore[union-attr]

    def point(self, arm: str, k: int) -> dict[str, object]:
        for row in self.curve:
            if row["arm"] == arm and row["k"] == k:
                return row
        raise KeyError(f"no published point for arm {arm!r} at k={k}")


def load_ttc_metrics(path: Path) -> TtcMetrics:
    params: dict[str, object] = {}
    curve: list[dict[str, object]] = []
    wall: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["kind"] == "curve":
                curve.append(row)
            elif row["kind"] == "wall":
                wall.append(row)
            else:
                params = row
    return TtcMetrics(params=params, curve=curve, wall=wall)


def _f(row: dict[str, object], key: str) -> str:
    return f"{float(row[key]):.4f}"  # type: ignore[arg-type]


def render_ttc_table(metrics: TtcMetrics) -> str:
    """The whole study as three tables: the curve, the cost, and the wall."""
    params = metrics.params
    trials = int(params["n_trials"])  # type: ignore[arg-type]
    detectable = int(params["detectable_mutants"])  # type: ignore[arg-type]
    classes = int(params["detectable_classes"])  # type: ignore[arg-type]
    clean = int(params["clean_items"])  # type: ignore[arg-type]
    mutants = int(params["mutant_items"])  # type: ignore[arg-type]
    wall_names = ", ".join(str(c) for c in params["wall_classes"])  # type: ignore[union-attr]
    arms = metrics.arms
    ks = metrics.k_values

    lines = [
        f"**Apparatus.** {trials} pre-registered trials over the same batch: "
        f"{mutants} mutants ({detectable} of them detectable, spread across "
        f"{classes} classes — one class plants twice) and {clean} byte-identical "
        f"clean controls. Members miss a real finding at rate "
        f"{_f(params, 'miss_rate')} (arm A3: {_f(params, 'miss_rate_below')}) and "
        f"invent a bogus one at rate {_f(params, 'fa_rate')} per file, clean or "
        f"mutant alike. Every point below is "
        f"{trials} x {detectable} = {trials * detectable} detectable mutant "
        f"reviews and {trials} x {clean} = {trials * clean} clean reviews. "
        f"Vote key: (line, class), majority of k, k odd.",
        "",
        "**The curve — detectable catch rate.** The prediction column is the "
        "exact binomial tail for this vote rule, valid only where member "
        "accuracy exceeds one half.",
        "",
    ]

    header = "| reviews per file (k) |" + "".join(
        f" {_ARM_LABELS.get(a, a)} |" for a in arms
    )
    lines.append(header + " binomial prediction (A1) |")
    lines.append("|---|" + "---|" * (len(arms) + 1))
    for k in ks:
        cells = "".join(f" {_f(metrics.point(a, k), 'detectable_catch')} |" for a in arms)
        prediction = _f(metrics.point(arms[0], k), "condorcet")
        lines.append(f"| **{k}** |{cells} {prediction} |")

    # Diminishing returns, DERIVED. This ratio is a measured number, so it is
    # rendered from the artifact rather than typed into the prose around it —
    # a hand-typed ratio drifts the moment the batch or the seeds change, and
    # nothing in CI would catch the contradiction.
    def catch(arm: str, k: int) -> float:
        return float(metrics.point(arm, k)["detectable_catch"])  # type: ignore[arg-type]

    first_step = catch(arms[0], ks[1]) - catch(arms[0], ks[0])
    last_step = catch(arms[0], ks[-1]) - catch(arms[0], ks[-2])
    lines.extend(
        [
            "",
            f"**Diminishing returns.** The first two extra reviews "
            f"(k={ks[0]} to k={ks[1]}) buy **{first_step:+.4f}** detectable "
            f"catch. The last two (k={ks[-2]} to k={ks[-1]}) buy "
            f"**{last_step:+.4f}** — **{last_step / first_step:.2f}x** the "
            f"gain, at exactly the same marginal cost of two more reviews.",
        ]
    )

    lines.extend(
        [
            "",
            "**The cost — noise the panel pays for.** A false alarm is any "
            "finding on a clean control; a spurious finding is one on a mutant "
            "that does not match the planted defect.",
            "",
            "| reviews per file (k) | A1 false alarms per clean review | A1 "
            "spurious per mutant review | A2 false alarms per clean review |",
            "|---|---|---|---|",
        ]
    )
    for k in ks:
        first = metrics.point(arms[0], k)
        placebo = metrics.point(arms[1], k)
        lines.append(
            f"| **{k}** | {_f(first, 'fa_per_clean_review')} | "
            f"{_f(first, 'spurious_per_mutant_review')} | "
            f"{_f(placebo, 'fa_per_clean_review')} |"
        )

    lines.extend(
        [
            "",
            f"**The wall — class(es) with no detection rule: {wall_names}.** No "
            "member can find them, so no majority can either. Zero by "
            "construction, published at every k in every arm.",
            "",
            "| rule-less class | arm |"
            + "".join(f" k={k} |" for k in ks)
            + " reviews per point |",
            "|---|---|" + "---|" * (len(ks) + 1),
        ]
    )
    # One table row per (class, arm), with k across the columns. Wall rows
    # exist at every k, so the first k's rows enumerate the (class, arm) pairs.
    for row in metrics.wall:
        if row["k"] != ks[0]:
            continue
        hits = "".join(
            f" {int(_wall_hits(metrics, str(row['arm']), k, str(row['class_id'])))} |"
            for k in ks
        )
        lines.append(
            f"| {row['class_id']} | {_ARM_LABELS.get(str(row['arm']), row['arm'])} |"
            f"{hits} {row['mutant_reviews']} |"
        )
    return "\n".join(lines)


def _wall_hits(metrics: TtcMetrics, arm: str, k: int, class_id: str) -> int:
    for row in metrics.wall:
        if row["arm"] == arm and row["k"] == k and row["class_id"] == class_id:
            return int(row["hits"])  # type: ignore[arg-type]
    raise KeyError(f"no wall row for {arm!r} k={k} {class_id!r}")


def render_ttc_curve_svg(metrics: TtcMetrics) -> str:
    """The k-curve: the win, the placebo, the amplified error, and the wall.

    Every coordinate is emitted at fixed precision — a float whose repr drifts
    by one digit between platforms would fail the drift gate for a reason that
    has nothing to do with the study.
    """
    arms = metrics.arms
    ks = metrics.k_values
    width, height = 760, 464
    left, right, top, floor = 70, 540, 66, 350
    span = (right - left) / (len(ks) - 1)
    scale = floor - top

    def x_of(index: int) -> str:
        return f"{left + index * span:.1f}"

    def y_of(value: float) -> str:
        return f"{floor - value * scale:.1f}"

    def series(arm: str) -> list[tuple[str, str]]:
        return [
            (x_of(i), y_of(float(metrics.point(arm, k)["detectable_catch"])))  # type: ignore[arg-type]
            for i, k in enumerate(ks)
        ]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="monospace" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="24" font-size="14" fill="{_INK}">'
        "inference-compute study — detectable catch rate vs reviews per file</text>",
        f'<text x="{left}" y="42" fill="{_MUTED}">'
        "same batch, same seeds, three arms — the only difference is where the "
        "errors come from</text>",
    ]
    for tick in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = y_of(tick)
        parts.append(
            f'<line x1="{left}" y1="{y}" x2="{right}" y2="{y}" stroke="#e5e7eb"/>'
        )
        parts.append(
            f'<text x="{left - 8}" y="{float(y) + 4:.1f}" text-anchor="end" '
            f'fill="{_MUTED}">{tick:.2f}</text>'
        )
    for i, k in enumerate(ks):
        parts.append(
            f'<text x="{x_of(i)}" y="{floor + 22}" text-anchor="middle" '
            f'fill="{_INK}">k={k}</text>'
        )
    parts.append(
        f'<text x="{(left + right) / 2:.1f}" y="{floor + 42}" text-anchor="middle" '
        f'fill="{_MUTED}">reviews per file</text>'
    )

    # A2 first, so the winning curve draws over the placebo where they meet.
    styles = {
        "correlated": (_AMBER, ' stroke-dasharray="7 5"'),
        "below-chance": (_VIOLET, ""),
        "independent": (_BLUE, ""),
    }
    for arm in ("correlated", "below-chance", "independent"):
        if arm not in arms:
            continue
        color, dash = styles[arm]
        points = series(arm)
        path = " ".join(f"{x},{y}" for x, y in points)
        parts.append(
            f'<polyline points="{path}" fill="none" stroke="{color}" '
            f'stroke-width="2"{dash}/>'
        )
        for x, y in points:
            parts.append(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{color}"/>')

    # Hollow markers: the theory the empirical dots are graded against.
    for i, k in enumerate(ks):
        predicted = float(metrics.point(arms[0], k)["condorcet"])  # type: ignore[arg-type]
        parts.append(
            f'<circle cx="{x_of(i)}" cy="{y_of(predicted)}" r="7" fill="none" '
            f'stroke="{_BLUE}" stroke-width="1.5"/>'
        )

    wall_y = y_of(0.0)
    parts.append(
        f'<line x1="{left}" y1="{wall_y}" x2="{right}" y2="{wall_y}" '
        f'stroke="{_RED}" stroke-width="3"/>'
    )
    parts.append(
        f'<text x="{left + 6}" y="{float(wall_y) - 8:.1f}" fill="{_RED}">'
        "THE WALL — rule-less class, 0 hits at every k, in every arm</text>"
    )

    # Labels are split into two explicit lines rather than wrapped by word
    # count: the canvas is fixed, and a label that silently overflows it would
    # ship a clipped legend into the README.
    legend = [
        (_BLUE, "solid", "A1 independent", "members"),
        (_BLUE, "hollow", "binomial", "prediction"),
        (_AMBER, "dashed", "A2 correlated", "(one shared stream)"),
        (_VIOLET, "solid", "A3 below-chance", "members"),
        (_RED, "solid", "the wall", "(no detection rule)"),
    ]
    parts.append(f'<text x="{right + 20}" y="{top - 6}" fill="{_INK}">legend</text>')
    for i, (color, kind, head, tail) in enumerate(legend):
        y = top + 18 + i * 34
        if kind == "hollow":
            parts.append(
                f'<circle cx="{right + 28}" cy="{y - 4}" r="6" fill="none" '
                f'stroke="{color}" stroke-width="1.5"/>'
            )
        else:
            dash = ' stroke-dasharray="7 5"' if kind == "dashed" else ""
            parts.append(
                f'<line x1="{right + 20}" y1="{y - 4}" x2="{right + 36}" '
                f'y2="{y - 4}" stroke="{color}" stroke-width="3"{dash}/>'
            )
        parts.append(
            f'<text x="{right + 44}" y="{y}" fill="{_INK}" font-size="11">'
            f"{head}</text>"
        )
        parts.append(
            f'<text x="{right + 44}" y="{y + 13}" fill="{_MUTED}" font-size="11">'
            f"{tail}</text>"
        )

    footer = (
        (_RED, "synthetic Bernoulli noise, independent BY CONSTRUCTION"),
        (_RED, "a mechanism reproduced, never any model measured"),
        (
            _MUTED,
            "the prediction is valid only above one-half member accuracy — "
            "A3 is the regime below it",
        ),
    )
    for i, (color, text) in enumerate(footer):
        parts.append(
            f'<text x="{left}" y="{height - 50 + i * 18}" fill="{color}">{text}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
