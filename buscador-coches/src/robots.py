"""Parser de robots.txt según RFC 9309 (comodines * y $, gana la regla más larga, empate -> Allow).

urllib.robotparser de la biblioteca estándar no soporta comodines y aplica la primera regla que
coincide, lo que da resultados erróneos en ambos sentidos (p. ej. permite /?pg=8 en coches.net
aunque 'Disallow: /*pg=8*', y bloquea filtros que sí están permitidos).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


def _compile(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
    return re.compile(rx + ("$" if anchored else ""))


class Robots:
    def __init__(self, text: str):
        self.groups: list[tuple[list[str], list[tuple[bool, str, re.Pattern]]]] = []
        agents: list[str] = []
        rules: list = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(val.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if val == "" and key == "disallow":
                    continue  # "Disallow:" vacío = todo permitido
                rules.append((key == "allow", val, _compile(val)))
            else:
                last_was_agent = False
        if agents or rules:
            self.groups.append((agents, rules))

    def _rules_for(self, user_agent: str):
        ua = user_agent.lower()
        specific = [r for a, r in self.groups if any(x != "*" and x and x in ua for x in a)]
        if specific:
            return [x for r in specific for x in r]
        return [x for a, r in self.groups if "*" in a for x in r]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        p = urlparse(url)
        path = (p.path or "/") + (f"?{p.query}" if p.query else "")
        if path == "/robots.txt":
            return True
        best_len, allowed = -1, True
        for is_allow, pat, rx in self._rules_for(user_agent):
            if rx.match(path):
                ln = len(pat)
                if ln > best_len or (ln == best_len and is_allow):
                    best_len, allowed = ln, is_allow
        return allowed
