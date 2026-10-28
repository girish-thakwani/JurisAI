#!/usr/bin/env python3
"""

  python main.py record https://web.whatsapp.com              # codegen, then live editor
  python main.py edit main.py                                 # live editor on an existing script
  python main.py convert main.py                              # static main.flow.html + main.mmd

Works on raw `playwright codegen --target python` output (linear) and on hand-written
scripts with if / for / while / try-except / continue / break / helper functions.
Each function becomes its own diagram; calls to helpers show as subroutine boxes.
"""
import argparse
import ast
import hashlib
import http.server
import json
import pathlib
import secrets
import subprocess
import sys
import webbrowser

# ---- Playwright vocabulary -------------------------------------------------
VERBS = {
    "goto": "Go to", "go_back": "Go back", "reload": "Reload",
    "click": "Click", "dblclick": "Double-click", "hover": "Hover", "focus": "Focus", "drag_to": "Drag",
    "fill": "Fill", "type": "Type", "press": "Press", "press_sequentially": "Type", "clear": "Clear",
    "select_option": "Select", "check": "Check", "uncheck": "Uncheck", "set_input_files": "Upload",
    "wait_for_selector": "Wait for", "wait_for": "Wait for", "wait_for_timeout": "Wait",
    "wait_for_url": "Wait for URL", "wait_for_load_state": "Wait for load",
    "screenshot": "Screenshot", "expect_download": "Expect download",
}
KIND = {
    "goto": "nav", "go_back": "nav", "reload": "nav",
    "click": "act", "dblclick": "act", "hover": "act", "focus": "act", "drag_to": "act", "screenshot": "act",
    "fill": "input", "type": "input", "press": "input", "press_sequentially": "input", "clear": "input",
    "select_option": "input", "check": "input", "uncheck": "input", "set_input_files": "input",
}
WITH_VALUE = {"fill", "type", "press_sequentially", "select_option", "set_input_files"}
LOCATOR_ONLY = {"locator", "frame_locator", "first", "last", "nth", "filter", "and_", "or_"}
SKIP_CALLS = {"print", "len", "next", "int", "str", "enumerate", "range", "list", "sorted",
              "min", "max", "filter", "isinstance", "sleep"}
PW_BASES = {"page", "browser", "context", "playwright", "p", "frame"}


def src(n, limit=45):
    s = ast.unparse(n)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def lit(n, limit=35):
    s = n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else ast.unparse(n)
    s = str(s)
    return s if len(s) <= limit else s[: limit - 1] + "…"


def flatten(call):
    """a.b(x).c.d(y) -> (base_name, [(name, Call|None), ...]) in source order."""
    items, n, base = [], call, None
    while True:
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute):
                items.append((f.attr, n))
                n = f.value
            elif isinstance(f, ast.Name):
                items.append((f.id, n))
                break
            else:
                break
        elif isinstance(n, ast.Attribute):
            items.append((n.attr, None))
            n = n.value
        elif isinstance(n, ast.Subscript):
            n = n.value
        elif isinstance(n, ast.Name):
            base = n.id
            break
        else:
            break
    return base, items[::-1]


def locator_text(items):
    parts = []
    for name, c in items[:-1]:
        a = c.args if c else []
        kw = {k.arg: k.value for k in c.keywords} if c else {}
        if name == "locator" and a:
            parts.append(lit(a[0], 45))
        elif name.startswith("get_by_"):
            t = f"{name[7:]}:{lit(a[0]) if a else ''}"
            if "name" in kw:
                t += f' "{lit(kw["name"])}"'
            parts.append(t)
        elif name in ("first", "last"):
            parts.append(name)
        elif name == "nth" and a:
            parts.append(f"nth({lit(a[0])})")
    return " › ".join(parts)


def find_call(e):
    if isinstance(e, ast.Await):
        return find_call(e.value)
    if isinstance(e, ast.Call):
        return e
    if isinstance(e, (ast.Attribute, ast.Subscript)):
        return find_call(e.value)
    return None


# ---- Editable fields -------------------------------------------------------
ARG_LABELS = {"goto": ["url"], "fill": ["value"], "type": ["text"], "press": ["key"],
              "press_sequentially": ["text"], "select_option": ["option"], "wait_for_timeout": ["ms"],
              "wait_for_selector": ["selector"], "wait_for_url": ["url"], "set_input_files": ["file"]}


def mkfield(label, node, source):
    is_str = isinstance(node, ast.Constant) and isinstance(node.value, str)
    val = node.value if is_str else ((source and ast.get_source_segment(source, node)) or ast.unparse(node))
    return {"label": label, "value": val, "str": is_str,
            "span": [node.lineno, node.col_offset, node.end_lineno, node.end_col_offset]}


def fields_for(call, source):
    out = []
    for name, c in flatten(call)[1]:
        if c is None:
            continue
        for i, a in enumerate(c.args):
            if isinstance(a, ast.Starred):
                continue
            if name == "locator" and i == 0:
                lab = "selector"
            elif name.startswith("get_by_") and i == 0:
                lab = name[7:].replace("_", " ")
            else:
                labs = ARG_LABELS.get(name, [])
                lab = labs[i] if i < len(labs) else f"{name} arg {i + 1}"
            out.append(mkfield(lab, a, source))
        for k in c.keywords:
            if k.arg:
                out.append(mkfield(k.arg if name.startswith("get_by_") else f"{name} {k.arg}", k.value, source))
    return out


def constants(tree, source):
    out = []
    for s in tree.body:
        if (isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name)
                and s.targets[0].id.isupper() and isinstance(s.value, ast.Constant)
                and isinstance(s.value.value, (str, int, float)) and not isinstance(s.value.value, bool)):
            out.append(mkfield(s.targets[0].id, s.value, source))
    return out


# ---- Graph model -----------------------------------------------------------
class Graph:
    def __init__(self, title, funcs, pw_funcs, src=""):
        self.title, self.funcs, self.pw, self.src = title, funcs, pw_funcs, src
        self.meta = {}  # node id -> {line, fields, stmt span, context}
        self.cur, self.sib = {}, ([], 0)
        self.nodes, self.edges, self.groups = [], [], {}
        self.gstack, self.loops, self.alias = [None], [], {}
        self.n = self.g = self.tries = 0

    # nodes / edges
    def add(self, label, kind, pend, fields=None, line=None):
        self.n += 1
        nid = f"n{self.n}"
        self.nodes.append((nid, label, kind, self.gstack[-1]))
        if fields is not None:
            self.meta[nid] = dict(self.cur, fields=fields, line=line)
        for a, lab, dash in pend:
            self.edge(a, nid, lab, dash)
        return nid

    def edge(self, a, b, lab="", dash=False):
        e = (a, b, lab, dash)
        if e not in self.edges:
            self.edges.append(e)

    # call -> (label, kind) | None
    def describe(self, call):
        base, items = flatten(call)
        name = items[-1][0] if items else None
        if isinstance(call.func, ast.Name):
            fn = call.func.id
            if fn in SKIP_CALLS:
                return None
            if fn in self.funcs:
                return src(call, 50), ("sub" if fn in self.pw else "act")
            return src(call, 55), "io"
        if name in SKIP_CALLS or name in LOCATOR_ONLY or (name or "").startswith("get_by_"):
            return None
        a = call.args
        if name in VERBS:
            verb = VERBS[name]
            target = locator_text(items)
            if not target and base and base not in PW_BASES:
                target = self.alias.get(base, base)
            is_kb = any(n in ("keyboard", "mouse") for n, c in items[:-1] if c is None)
            arg = lit(a[0], 40) if a else ""
            if name == "wait_for_timeout":
                label = f"Wait {arg} ms"
            elif name in ("goto", "wait_for_selector", "wait_for_url") and arg:
                label = f"{verb} {arg}"
            elif name == "press" and (is_kb or not target):
                label = f"Press {arg}"
            elif name in ("type", "press_sequentially") and (is_kb or not target):
                label = f"Type {arg}"
            else:
                label = f"{verb} {target}".strip()
                if name in WITH_VALUE and arg:
                    label += f" ← {arg}"
                elif name == "wait_for":
                    kw = {k.arg: k.value for k in call.keywords}
                    if "state" in kw:
                        label += f" ({lit(kw['state'])})"
            kind = "wait" if name.startswith("wait") else KIND.get(name, "act")
            return label, kind
        is_pw = base in PW_BASES or any(n.startswith("get_by_") or n == "locator" for n, _ in items)
        return src(call, 55), ("act" if is_pw else "io")

    # statements
    def block(self, stmts, pend):
        for i, s in enumerate(stmts):
            if not pend:
                break
            self.sib = (stmts, i)
            pend = self.stmt(s, pend)
        return pend

    def stmt(self, s, pend):
        last = self.sib[0][-1]
        self.cur = {"stmt": [s.lineno, s.col_offset, s.end_lineno, s.end_col_offset],
                    "rest_end": [last.end_lineno, last.end_col_offset],
                    "in_loop": bool(self.loops), "func": self.title != "module",
                    "assign": isinstance(s, (ast.Assign, ast.AugAssign, ast.AnnAssign)),
                    "is_if": isinstance(s, ast.If), "has_else": isinstance(s, ast.If) and bool(s.orelse),
                    "base": None}
        if isinstance(s, (ast.Expr, ast.Assign, ast.AugAssign, ast.AnnAssign)):
            v = s.value
            c = find_call(v) if v is not None else None
            d = self.describe(c) if c else None
            if d:
                nid = self.add(d[0], d[1], pend, fields_for(c, self.src), s.lineno)
                b = flatten(c)[0]
                self.meta[nid]["base"] = b if b in ("page", "frame") else None
                return [(nid, "", False)]
            if c is not None and isinstance(s, ast.Assign) and isinstance(s.targets[0], ast.Name):
                _, its = flatten(c)
                self.alias[s.targets[0].id] = locator_text(its + [("_", None)])
            return pend
        if isinstance(s, ast.If):
            dec = self.add(src(s.test, 50) + "?", "dec", pend,
                           [mkfield("condition", s.test, self.src)], s.lineno)
            yes = self.block(s.body, [(dec, "yes", False)])
            no = self.block(s.orelse, [(dec, "no", False)]) if s.orelse else [(dec, "no", False)]
            return yes + no
        if isinstance(s, (ast.For, ast.AsyncFor, ast.While)):
            label = (f"for {src(s.target, 20)} in {src(s.iter, 35)}"
                     if not isinstance(s, ast.While) else f"while {src(s.test, 40)}")
            head = self.add(label, "loop", pend,
                            [mkfield("condition" if isinstance(s, ast.While) else "iterable",
                                     s.test if isinstance(s, ast.While) else s.iter, self.src)], s.lineno)
            self.loops.append({"head": head, "breaks": []})
            body = self.block(s.body, [(head, "next", False)])
            loop = self.loops.pop()
            for a, lab, dash in body:
                self.edge(a, head, lab, dash)
            return [(head, "done", False)] + loop["breaks"]
        if isinstance(s, ast.Try):
            self.g += 1
            gid = f"g{self.g}"
            self.groups[gid] = {"label": "try", "parent": self.gstack[-1]}
            before = len(self.nodes)
            self.gstack.append(gid)
            self.tries += 1
            body = self.block(s.body, pend)
            self.tries -= 1
            self.gstack.pop()
            if len(self.nodes) == before:
                del self.groups[gid]
                return pend
            outs = self.block(s.orelse, body) if s.orelse else list(body)
            for h in s.handlers:
                lab = "on error" + (f": {src(h.type, 25)}" if h.type else "")
                outs += self.block(h.body, [(gid, lab, True)])
            if s.finalbody:
                outs = self.block(s.finalbody, outs)
            return outs
        if isinstance(s, (ast.With, ast.AsyncWith)):
            return self.block(s.body, pend)
        if isinstance(s, ast.Continue):
            if self.loops:
                for a, lab, dash in pend:
                    self.edge(a, self.loops[-1]["head"], lab or "continue", dash)
            return []
        if isinstance(s, ast.Break):
            if self.loops:
                self.loops[-1]["breaks"].extend(pend)
            return []
        if isinstance(s, ast.Raise):
            n = self.add("raise " + (src(s.exc, 40) if s.exc else ""), "err", pend)
            if self.tries == 0:
                self.edge(n, "END")
            return []
        if isinstance(s, ast.Return):
            c = find_call(s.value) if s.value is not None else None
            d = self.describe(c) if c else None
            if d:
                pend = [(self.add(d[0], d[1], pend, fields_for(c, self.src), s.lineno), "", False)]
            for a, lab, dash in pend:
                self.edge(a, "END", lab, dash)
            return []
        return pend

    # output
    def mermaid(self):
        shapes = {
            "term": '(["{}"])', "dec": '{{"{}"}}', "loop": '{{{{"{}"}}}}',
            "sub": '[["{}"]]', "io": '[/"{}"/]',
        }
        esc = lambda t: (t.replace("#", "#35;").replace('"', "#quot;")
                          .replace("<", "#lt;").replace(">", "#gt;"))
        out = ["flowchart TD"]
        out += [
            "classDef term fill:#1f2937,stroke:#1f2937,color:#fff",
            "classDef nav fill:#dbeafe,stroke:#3b82f6,color:#111",
            "classDef act fill:#dcfce7,stroke:#22c55e,color:#111",
            "classDef input fill:#ede9fe,stroke:#8b5cf6,color:#111",
            "classDef wait fill:#f3f4f6,stroke:#9ca3af,color:#111",
            "classDef io fill:#fef3c7,stroke:#f59e0b,color:#111",
            "classDef sub fill:#ccfbf1,stroke:#14b8a6,color:#111",
            "classDef err fill:#fee2e2,stroke:#ef4444,color:#111",
            "classDef dec fill:#fff,stroke:#111,color:#111",
            "classDef loop fill:#fff7ed,stroke:#f97316,color:#111",
        ]

        def emit(gid, ind):
            for nid, label, kind, g in self.nodes:
                if g == gid:
                    shape = shapes.get(kind, '["{}"]').format(esc(label))
                    out.append(f"{ind}{nid}{shape}:::{kind}")
            for cg, info in self.groups.items():
                if info["parent"] == gid:
                    out.append(f'{ind}subgraph {cg}["{info["label"]}"]')
                    emit(cg, ind + "  ")
                    out.append(f"{ind}end")

        emit(None, "")
        for a, b, lab, dash in self.edges:
            arrow = "-.->" if dash else "-->"
            out.append(f'{a} {arrow}|"{esc(lab)}"| {b}' if lab else f"{a} {arrow} {b}")
        return "\n".join(out)


GENERATED_HELPERS = {"element_appears"}


def build(tree, src=""):
    fdefs = (ast.FunctionDef, ast.AsyncFunctionDef)
    funcs = {n.name: n for n in tree.body if isinstance(n, fdefs)}

    def has_pw(fn, known):
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                _, items = flatten(n)
                names = {i[0] for i in items}
                if names & set(VERBS) or any(x.startswith("get_by_") or x == "locator" for x in names):
                    return True
                if isinstance(n.func, ast.Name) and n.func.id in known:
                    return True
        return False

    pw = set()
    while True:  # fixpoint: helpers that call helpers that touch the page
        new = {k for k, f in funcs.items() if k not in pw and has_pw(f, pw)}
        if not new:
            break
        pw |= new

    def make(title, stmts):
        g = Graph(title, funcs, pw, src)
        start = g.add("Start", "term", [])
        end = g.block(stmts, [(start, "", False)])
        g.nodes.append(("END", "End", "term", None))
        for a, lab, dash in end:
            g.edge(a, "END", lab, dash)
        return g

    graphs = []
    module = [s for s in tree.body
              if not isinstance(s, fdefs + (ast.ClassDef, ast.Import, ast.ImportFrom))]
    m = make("module", module)
    if len(m.nodes) > 2:
        graphs.append(m)
    called = {n.func.id for s in module for n in ast.walk(s)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    order = [k for k in funcs if k in called] + [k for k in funcs if k not in called]
    for name in order:
        if name in pw and name not in GENERATED_HELPERS:
            graphs.append(make(f"{name}()", funcs[name].body))
    return graphs


HTML = """<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>
body{{font:15px system-ui,sans-serif;margin:0;background:#f8fafc;color:#111}}
main{{max-width:1200px;margin:auto;padding:24px}}
section{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin:0 0 24px;overflow-x:auto}}
h2{{margin:0 0 8px;font-size:16px}} button{{float:right;cursor:pointer}}
.legend span{{display:inline-block;padding:2px 8px;margin:0 6px 12px 0;border-radius:4px;font-size:12px;border:1px solid}}
</style>
<main><h1>{title}</h1>
<div class="legend">
<span style="background:#dbeafe;border-color:#3b82f6">navigate</span>
<span style="background:#dcfce7;border-color:#22c55e">click</span>
<span style="background:#ede9fe;border-color:#8b5cf6">input</span>
<span style="background:#f3f4f6;border-color:#9ca3af">wait</span>
<span style="background:#fef3c7;border-color:#f59e0b">external I/O</span>
<span style="background:#ccfbf1;border-color:#14b8a6">subroutine</span>
<span style="background:#fee2e2;border-color:#ef4444">error</span></div>
{sections}</main>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{startOnLoad:true,securityLevel:"loose",flowchart:{{curve:"basis",htmlLabels:true}}}});
document.querySelectorAll("button[data-src]").forEach(b=>b.onclick=()=>navigator.clipboard.writeText(
  document.getElementById(b.dataset.src).textContent));
</script>"""


def convert(path, out=None):
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")
    graphs = build(ast.parse(text), text)
    out = pathlib.Path(out) if out else path.with_suffix(".flow.html")
    secs, mmd = [], []
    for i, g in enumerate(graphs):
        code = g.mermaid()
        mmd.append(f"%% {g.title}\n{code}")
        secs.append(f'<section><button data-src="m{i}">Copy Mermaid</button><h2>{g.title}</h2>'
                    f'<pre class="mermaid" id="m{i}">{code}</pre></section>')
    out.write_text(HTML.format(title=path.name, sections="\n".join(secs)), encoding="utf-8")
    path.with_suffix(".mmd").write_text("\n\n".join(mmd), encoding="utf-8")
    print(f"wrote {out} and {path.with_suffix('.mmd')} ({len(graphs)} diagram(s))")
    return out


# ---- Live editor: HTML edits are patched back into the script --------------
def payload(path):
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines()
    pub = lambda f: {k: f[k] for k in ("label", "value", "str")}
    gs = []
    for g in build(tree, src):
        nodes = {}
        for nid, label, kind, _ in g.nodes:
            m = g.meta.get(nid)
            ln = m["line"] if m else None
            nodes[nid] = {"label": label, "kind": kind, "line": ln,
                          "code": lines[ln - 1].strip() if ln else "",
                          "ctx": {k: m[k] for k in ("in_loop", "func", "assign", "is_if", "has_else", "base")} if m else None,
                          "fields": [pub(f) for f in m["fields"]] if m else []}
        gs.append({"title": g.title, "mermaid": g.mermaid(), "nodes": nodes})
    return {"rev": hashlib.sha1(src.encode()).hexdigest(), "file": path.name, "graphs": gs,
            "consts": [pub(f) for f in constants(tree, src)]}


def apply_edits(src, edits):
    tree = ast.parse(src)
    graphs, consts = build(tree, src), constants(tree, src)
    sb = src.encode("utf-8")
    starts, pos = [0], 0
    for line in sb.split(b"\n"):
        pos += len(line) + 1
        starts.append(pos)
    off = lambda l, c: starts[l - 1] + c
    reps = []
    for e in edits:
        f = (graphs[e["g"]].meta[e["nid"]]["fields"][e["fi"]] if e["t"] == "n" else consts[e["ci"]])
        v = e["value"]
        if f["str"]:
            text = json.dumps(v, ensure_ascii=False)
        else:
            text = v.strip()
            if not text:
                raise ValueError(f'"{f["label"]}" cannot be empty')
        sp = f["span"]
        reps.append((off(sp[0], sp[1]), off(sp[2], sp[3]), text.encode("utf-8")))
    reps.sort(reverse=True)
    for (s1, e1, _), (s2, e2, _) in zip(reps, reps[1:]):
        if s1 < e2:
            raise ValueError("overlapping edits")
    for s_, e_, t in reps:
        sb = sb[:s_] + t + sb[e_:]
    out = sb.decode("utf-8")
    ast.parse(out)  # never write a script that no longer parses
    return out


HELPER = [
    "def element_appears(locator, timeout=3000):",
    "    # True if the locator becomes visible within `timeout` ms (generated helper)",
    "    try:",
    '        locator.first.wait_for(state="visible", timeout=timeout)',
    "        return True",
    "    except Exception:",
    "        return False",
]


def _tail(line, col):
    return line.encode("utf-8")[col:].decode("utf-8", "ignore")


def structure_edit(src, op):
    """wrap_if: wrap a step (or it + the rest of its block) in if/else.  add_else: give an if an else."""
    tree = ast.parse(src)
    m = build(tree, src)[op["g"]].meta.get(op["nid"])
    if not m:
        raise ValueError("this step can't be edited")
    other = op.get("other", "none")
    if other == "end":
        else_stmt = "return" if m["func"] else "raise SystemExit"
    elif other == "exit":
        else_stmt = "raise SystemExit"
    elif other in ("continue", "break"):
        if not m["in_loop"]:
            raise ValueError("this step is not inside a loop")
        else_stmt = other
    elif other == "none":
        else_stmt = None
    else:
        raise ValueError("unknown else action")
    nl = "\r\n" if "\r\n" in src else "\n"
    lines = src.split(nl)
    s_l, col, e_l, _ = m["stmt"]
    first = lines[s_l - 1]
    prefix = first[: len(first) - len(first.lstrip())]
    unit = "\t" if "\t" in prefix else "    "
    if op["op"] == "wrap_if":
        cond = op["cond"].strip()
        ast.parse(cond, mode="eval")
        if len(prefix) != col or first.lstrip().startswith("elif"):
            raise ValueError("this step can't be wrapped here (shares a line, or is an elif)")
        if op.get("scope") == "rest":
            e_l, e_c = m["rest_end"]
        else:
            e_c = m["stmt"][3]
        rest = _tail(lines[e_l - 1], e_c).strip()
        if rest and not rest.startswith("#"):
            raise ValueError("another statement shares the last line of this step")
        for n in ast.walk(tree):
            if (isinstance(n, (ast.Constant, ast.JoinedStr)) and not (isinstance(n, ast.Constant) and not isinstance(n.value, (str, bytes)))
                    and n.lineno >= s_l and n.end_lineno <= e_l and n.end_lineno > n.lineno):
                raise ValueError("a multi-line string is inside the step; edit the script by hand")
        body = [(unit + l if l.strip() else l) for l in lines[s_l - 1:e_l]]
        new = [f"{prefix}if {cond}:"] + body
        if else_stmt:
            new += [f"{prefix}else:", f"{prefix}{unit}{else_stmt}"]
        lines[s_l - 1:e_l] = new
        if "element_appears(" in cond and "def element_appears" not in src:
            imp = 0
            for st in tree.body:
                if isinstance(st, (ast.Import, ast.ImportFrom)):
                    imp = st.end_lineno
                elif not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)):
                    break
            if imp >= s_l:
                raise ValueError("step is above the imports")
            lines[imp:imp] = ["", ""] + HELPER + ["", ""]
    elif op["op"] == "add_else":
        if not m["is_if"] or m["has_else"]:
            raise ValueError("only an if without an else can get one")
        if else_stmt is None:
            raise ValueError("choose what the else branch does")
        lines[e_l:e_l] = [f"{prefix}else:", f"{prefix}{unit}{else_stmt}"]
    else:
        raise ValueError("unknown operation")
    out = nl.join(lines)
    ast.parse(out)
    return out


APP_HTML = """<!doctype html><meta charset="utf-8"><title>__TITLE__ - flow editor</title>
<style>
body{font:14px system-ui,sans-serif;margin:0;background:#f8fafc;color:#111}
header{display:flex;gap:12px;align-items:center;padding:10px 16px;background:#111827;color:#fff}
header b{flex:1} #status{font-size:12px;opacity:.85} #status.err{color:#fca5a5;opacity:1}
#wrap{display:flex;align-items:flex-start}
#diagrams{flex:1;min-width:0;padding:16px}
section{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px;margin:0 0 16px;overflow:auto}
h2{margin:0 0 6px;font-size:15px} h3{margin:14px 0 6px;font-size:13px;text-transform:uppercase;color:#6b7280}
aside{width:340px;flex:none;position:sticky;top:0;height:100vh;overflow:auto;box-sizing:border-box;
 padding:14px;background:#fff;border-left:1px solid #e5e7eb}
label{display:block;font-size:12px;color:#374151;margin:8px 0 0} label em{color:#9ca3af}
input[type=text]{width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid #d1d5db;border-radius:6px;
 font:13px ui-monospace,monospace} input.chg{border-color:#2563eb;background:#eff6ff}
code{display:block;margin-top:6px;padding:6px;background:#f3f4f6;border-radius:6px;font-size:12px;word-break:break-all}
select{width:100%;box-sizing:border-box;padding:6px;border:1px solid #d1d5db;border-radius:6px;margin-top:2px;background:#fff}
.prev{white-space:pre}
button{padding:6px 12px;border-radius:6px;border:1px solid #d1d5db;background:#fff;cursor:pointer}
#save{width:100%;margin-top:16px;background:#2563eb;color:#fff;border-color:#2563eb} #save:disabled{opacity:.4;cursor:default}
.muted{color:#6b7280} .lbl{font-weight:600}
g.node{cursor:pointer} g.node.sel>*:first-child{stroke:#2563eb!important;stroke-width:3.5px!important}
</style>
<header><b>__TITLE__</b><span id="status"></span><button id="undo">Undo</button><button id="reload">Reload</button></header>
<div id="wrap"><div id="diagrams"></div><aside id="panel"></aside></div>
<script src="__MERMAID__"></script>
<script>
const TOKEN="__TOKEN__", $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
let state={graphs:[],consts:[]}, sel=null, pending={}, cnt=0;
mermaid.initialize({startOnLoad:false,theme:"default",flowchart:{curve:"basis",htmlLabels:true}});
function status(t,err){const e=$("status");e.textContent=t;e.className=err?"err":"";}
async function api(url,opt){const r=await fetch(url,Object.assign({headers:{"X-Token":TOKEN,"Content-Type":"application/json"}},opt));
  const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j;}
async function draw(){
  const host=$("diagrams");host.innerHTML="";
  for(const [gi,g] of state.graphs.entries()){
    const sec=document.createElement("section");sec.innerHTML="<h2>"+esc(g.title)+"</h2><div class='d'></div>";host.appendChild(sec);
    const {svg}=await mermaid.render("m"+gi+"_"+(++cnt),g.mermaid);
    const d=sec.querySelector(".d");d.innerHTML=svg;
    d.querySelectorAll("g.node").forEach(el=>{
      const m=el.id.match(/flowchart-(n\\d+)-\\d+$/);if(!m)return;
      const nid=m[1];el.dataset.g=gi;el.dataset.nid=nid;
      if(sel&&sel.g==gi&&sel.nid==nid)el.classList.add("sel");
      el.onclick=()=>{sel={g:gi,nid};document.querySelectorAll("g.node.sel").forEach(x=>x.classList.remove("sel"));
        el.classList.add("sel");renderPanel();};
    });
  }
}
function field(key,f){const v=key in pending?pending[key]:f.value;
  return "<label>"+esc(f.label)+(f.str?"":" <em>(expression)</em>")+"<input type='text' data-k='"+key+"' data-o=\\""+esc(f.value)+"\\" value=\\""+esc(v)+"\\" class='"+(key in pending?"chg":"")+"'></label>";}
function renderPanel(){
  let h="";
  if(state.consts.length)h+="<h3>Constants</h3>"+state.consts.map((c,i)=>field("c:"+i,c)).join("");
  if(sel){const n=state.graphs[sel.g].nodes[sel.nid];
    h+="<h3>Step</h3><div class='lbl'>"+esc(n.label)+"</div>"+(n.line?"<code>line "+n.line+": "+esc(n.code)+"</code>":"");
    h+=n.fields.length?n.fields.map((f,i)=>field("n:"+sel.g+":"+sel.nid+":"+i,f)).join(""):"<p class='muted'>No editable inputs.</p>";
  }else h+="<h3>Step</h3><p class='muted'>Click a step to edit its inputs.</p>";
  h+="<button id='save'>Save to script</button>";
  if(sel)h+=structHtml(state.graphs[sel.g].nodes[sel.nid]);
  $("panel").innerHTML=h;
  $("undo").disabled=!state.can_undo;
  document.querySelectorAll("#panel [data-k]").forEach(i=>i.oninput=()=>{
    if(i.value===i.dataset.o){delete pending[i.dataset.k];i.classList.remove("chg");}else{pending[i.dataset.k]=i.value;i.classList.add("chg");}
    btn();});
  $("save").onclick=save;btn();bindStruct();
}
function btn(){const b=$("save");const n=Object.keys(pending).length;b.disabled=!n;b.textContent=n?"Save "+n+" change"+(n>1?"s":"")+" to script":"Save to script";}
async function save(){
  const edits=Object.entries(pending).map(([k,v])=>{const a=k.split(":");
    return a[0]=="c"?{t:"c",ci:+a[1],value:v}:{t:"n",g:+a[1],nid:a[2],fi:+a[3],value:v};});
  try{const j=await api("/api/edit",{method:"POST",body:JSON.stringify({rev:state.rev,edits})});
    pending={};state=j;await draw();renderPanel();status("Saved to "+j.file+" (backup: "+j.file+".bak)");}
  catch(e){status("Not saved: "+e.message,true);}
}
const NL=String.fromCharCode(10);
let ui={ctype:"visible",val:"",timeout:3000,neg:false,scope:"step",other:"end"};
const pyStr=s=>JSON.stringify(s);
const sopt=(o,cur)=>o.map(x=>"<option value='"+x[0]+"'"+(x[0]==cur?" selected":"")+">"+esc(x[1])+"</option>").join("");
function condExpr(n){
  const pv=(n.ctx&&n.ctx.base)||"page",t=+ui.timeout||0;let c;
  if(ui.ctype=="visible")c="element_appears("+pv+".locator("+pyStr(ui.val)+"), "+t+")";
  else if(ui.ctype=="text")c="element_appears("+pv+".get_by_text("+pyStr(ui.val)+"), "+t+")";
  else if(ui.ctype=="url")c=pyStr(ui.val)+" in "+pv+".url";
  else c=ui.val.trim();
  return ui.neg?"not ("+c+")":c;
}
function elseOpts(n,allowNone){const o=[["end","End workflow"]];
  if(n.ctx.func)o.push(["exit","Stop the whole script"]);
  if(n.ctx.in_loop){o.push(["continue","Skip to next loop item"]);o.push(["break","Exit the loop"]);}
  if(allowNone)o.push(["none","Do nothing"]);return o;}
function elseCode(n,e){return {end:n.ctx.func?"return":"raise SystemExit",exit:"raise SystemExit","continue":"continue","break":"break"}[e];}
function prevText(n){
  const c=ui.val.trim()?condExpr(n):"...";
  let t="if "+c+":"+NL+"    "+(ui.scope=="rest"?"(this step and the rest of the block)":n.label)+NL;
  if(ui.other!="none")t+="else:"+NL+"    "+elseCode(n,ui.other);
  return t;}
function structHtml(n){
  if(!n.ctx)return "";
  if(!elseOpts(n,true).some(x=>x[0]==ui.other))ui.other="end";
  let h="<h3>Add condition</h3>";
  h+="<label>Run only if<select id='c-type'>"+sopt([["visible","element is visible"],["text","text is on the page"],["url","URL contains"],["expr","custom expression"]],ui.ctype)+"</select></label>";
  h+="<label>"+({visible:"Selector (CSS, or text=...)",text:"Text",url:"URL part",expr:"Python expression"})[ui.ctype]+"<input type='text' id='c-val'></label>";
  if(ui.ctype=="visible"||ui.ctype=="text")h+="<label>Wait up to (ms)<input type='text' id='c-timeout'></label>";
  h+="<label><input type='checkbox' id='c-neg'> negate (run only if NOT)</label>";
  h+="<label>Apply to<select id='c-scope'>"+sopt([["step","this step only"],["rest","this step and everything after it in the block"]],ui.scope)+"</select></label>";
  h+="<label>Otherwise<select id='c-other'>"+sopt(elseOpts(n,true),ui.other)+"</select></label>";
  if(n.ctx.assign)h+="<p class='muted'>This step assigns a variable. If later steps use it, apply to the rest of the block.</p>";
  h+="<code class='prev' id='c-prev'></code><button id='c-apply' style='width:100%;margin-top:8px'>Wrap in if / else</button>";
  if(n.ctx.is_if&&!n.ctx.has_else)
    h+="<h3>Add else to this if</h3><label>Otherwise<select id='e-other'>"+sopt(elseOpts(n,false),"end")+"</select></label><button id='e-apply' style='width:100%;margin-top:8px'>Add else branch</button>";
  return h;
}
async function structure(body){
  if(Object.keys(pending).length){status("Save or discard pending edits first",true);return;}
  try{const j=await api("/api/structure",{method:"POST",body:JSON.stringify(Object.assign({rev:state.rev},body))});
    state=j;sel=null;await draw();renderPanel();status("Updated "+j.file);}
  catch(e){status("Not applied: "+e.message,true);}
}
function bindStruct(){
  if(!sel)return;const n=state.graphs[sel.g].nodes[sel.nid];if(!n.ctx)return;
  const g=id=>$(id),prev=()=>{g("c-prev").textContent=prevText(n);};
  g("c-val").value=ui.val;if(g("c-timeout"))g("c-timeout").value=ui.timeout;g("c-neg").checked=ui.neg;
  g("c-type").onchange=e=>{ui.ctype=e.target.value;renderPanel();};
  g("c-val").oninput=e=>{ui.val=e.target.value;prev();};
  if(g("c-timeout"))g("c-timeout").oninput=e=>{ui.timeout=e.target.value;prev();};
  g("c-neg").onchange=e=>{ui.neg=e.target.checked;prev();};
  g("c-scope").onchange=e=>{ui.scope=e.target.value;prev();};
  g("c-other").onchange=e=>{ui.other=e.target.value;prev();};
  g("c-apply").onclick=()=>{if(!ui.val.trim()){status("Enter the condition value",true);return;}
    structure({op:"wrap_if",g:sel.g,nid:sel.nid,cond:condExpr(n),scope:ui.scope,other:ui.other});};
  if(g("e-apply"))g("e-apply").onclick=()=>structure({op:"add_else",g:sel.g,nid:sel.nid,other:g("e-other").value});
  prev();
}
async function undo(){
  try{state=await api("/api/undo",{method:"POST",body:"{}"});sel=null;pending={};await draw();renderPanel();status("Undone");}
  catch(e){status("Not undone: "+e.message,true);}
}
async function load(){try{state=await api("/api/state");pending={};await draw();renderPanel();status("Loaded "+state.file);}
  catch(e){status(e.message,true);}}
$("reload").onclick=load;$("undo").onclick=undo;load();
</script>"""


def serve(script, port=8765, open_browser=True, vendor=None):
    path = pathlib.Path(script).resolve()
    token = secrets.token_urlsafe(16)
    vendor_path = pathlib.Path(vendor).resolve() if vendor else None
    mermaid_src = "/vendor/mermaid.js" if vendor_path else "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"

    hist = []  # (source before, sha1 of source after) for undo

    def sha(t):
        return hashlib.sha1(t.encode()).hexdigest()

    def state():
        p_ = payload(path)
        p_["can_undo"] = bool(hist) and hist[-1][1] == p_["rev"]
        return p_

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def guard(self, need_token=True):
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                self.send(403, json.dumps({"error": "bad host"}))
                return False
            if need_token and self.headers.get("X-Token") != token:
                self.send(403, json.dumps({"error": "bad token"}))
                return False
            return True

        def do_GET(self):
            if self.path == "/":
                if self.guard(False):
                    html = (APP_HTML.replace("__TITLE__", path.name).replace("__TOKEN__", token)
                            .replace("__MERMAID__", mermaid_src))
                    self.send(200, html, "text/html")
            elif self.path == "/vendor/mermaid.js" and vendor_path and self.guard(False):
                self.send(200, vendor_path.read_bytes(), "text/javascript")
            elif self.path == "/api/state" and self.guard():
                try:
                    self.send(200, json.dumps(state()))
                except Exception as e:
                    self.send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))
            else:
                self.send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            if self.path not in ("/api/edit", "/api/structure", "/api/undo") or not self.guard():
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                src = path.read_text(encoding="utf-8")
                if self.path == "/api/undo":
                    if not hist or hist[-1][1] != sha(src):
                        return self.send(409, json.dumps({"error": "nothing to undo (or script changed on disk)"}))
                    path.write_text(hist.pop()[0], encoding="utf-8")
                    return self.send(200, json.dumps(state()))
                if body.get("rev") != sha(src):
                    return self.send(409, json.dumps({"error": "script changed on disk - press Reload"}))
                if self.path == "/api/edit":
                    new = apply_edits(src, body["edits"])
                else:
                    new = structure_edit(src, body)
                bak = path.with_name(path.name + ".bak")
                if not bak.exists():
                    bak.write_text(src, encoding="utf-8")
                path.write_text(new, encoding="utf-8")
                hist.append((src, sha(new)))
                self.send(200, json.dumps(state()))
            except Exception as e:
                self.send(400, json.dumps({"error": f"{type(e).__name__}: {e}"}))

    for p in range(port, port + 10):
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", p), H)
            break
        except OSError:
            continue
    else:
        sys.exit("no free port")
    url = f"http://127.0.0.1:{p}/"
    print(f"editing {path}\n-> {url}   (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="run playwright codegen, then open the live editor")
    r.add_argument("url", nargs="?", default="")
    r.add_argument("-o", "--out", default="recorded.py")
    e = sub.add_parser("edit", help="live editor: change inputs in the flowchart, saved back into the script")
    e.add_argument("script")
    e.add_argument("--port", type=int, default=8765)
    e.add_argument("--no-browser", action="store_true")
    e.add_argument("--vendor", help="path to a local mermaid.js (UMD) for offline use")
    c = sub.add_parser("convert", help="static HTML + .mmd export")
    c.add_argument("script")
    c.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.cmd == "record":
        cmd = [sys.executable, "-m", "playwright", "codegen", "--target", "python", "-o", a.out]
        if a.url:
            cmd.append(a.url)
        subprocess.run(cmd, check=True)
        serve(a.out)
    elif a.cmd == "edit":
        serve(a.script, a.port, not a.no_browser, a.vendor)
    else:
        convert(a.script, a.out)


if __name__ == "__main__":
    main()
