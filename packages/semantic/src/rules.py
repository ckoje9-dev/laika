"""Rule definitions for semantic object classification."""

# Default classification rules
DEFAULT_RULES = [
    {"kind": "border", "keys": ["BORD", "TITLE", "FORM"], "source": "layer"},
    {"kind": "dimension", "keys": ["DIM"], "source": "layer"},
    {"kind": "symbol", "keys": ["SYM"], "source": "layer"},
    {"kind": "text", "keys": ["TXT", "TEXT"], "source": "layer"},
    {"kind": "axis", "keys": ["AXIS", "GRID"], "source": "layer"},
    {"kind": "column", "keys": ["COL"], "source": "layer"},
    {"kind": "steel_column", "keys": ["STL"], "source": "layer"},
    {"kind": "concrete", "keys": ["CON"], "source": "layer"},
    {"kind": "wall", "keys": ["WAL"], "source": "layer"},
    {"kind": "door", "keys": ["DOOR"], "source": "layer"},
    {"kind": "window", "keys": ["WIN"], "source": "layer"},
    {"kind": "stair", "keys": ["STR"], "source": "layer"},
    {"kind": "elevator", "keys": ["ELV"], "source": "layer"},
    {"kind": "furniture", "keys": ["FURN"], "source": "layer"},
    {"kind": "finish", "keys": ["FIN"], "source": "layer"},
    {"kind": "block", "keys": ["BLOCK"], "source": "type"},
]

# Maps UI selection keys to (kind, source) tuples
SELECTION_RULE_MAP = {
    "basic-border-block": ("border", "block"),
    "basic-dim-layer": ("dimension", "layer"),
    "basic-symbol-layer": ("symbol", "layer"),
    "basic-text-layer": ("text", "layer"),
    "struct-axis-layer": ("axis", "layer"),
    "struct-ccol-layer": ("column", "layer"),
    "struct-scol-layer": ("steel_column", "layer"),
    "struct-cwall-layer": ("concrete", "layer"),
    "non-wall-layer": ("wall", "layer"),
    "non-door-layer": ("door", "layer"),
    "non-window-layer": ("window", "layer"),
    "non-stair-layer": ("stair", "layer"),
    "non-elevator-layer": ("elevator", "layer"),
    "non-furniture-layer": ("furniture", "layer"),
    "non-finish-layer": ("finish", "layer"),
}
