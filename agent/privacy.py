"""
agent/privacy.py — swap cashier names for IDs before anything leaves the PC.

When an online model is connected, tool results go through hide() first, so
the model only ever sees "Cashier 1042", never a name. Its answer goes
through reveal() before it is shown, so the manager reads real names. A
question typed with a name ("how is Anna doing?") is hidden the same way.

Names come from the Cashier Database (operator ID → name). Anyone not in it
gets a stable placeholder ("Cashier X1", "Cashier X2", ...) for the session.
"""
import re

from config import DATABASE_FILE
from utils_core import load_db_map


class Pseudonymiser:
    def __init__(self, cashier_map=None):
        if cashier_map is None:
            cashier_map = load_db_map(DATABASE_FILE)
        self._to_alias = {}     # full name → alias (matched in any case)
        self._first = {}        # unique first name → alias (matched as written)
        self._to_name = {}
        for op_id, name in cashier_map.items():
            name = str(name).strip()
            if name and name not in self._to_alias:
                self._add(name, f"Cashier {op_id}")
        # First names too ("how is Anna doing?"), when only one cashier has it.
        # Matched only with a capital letter, so a cashier called "Will"
        # doesn't swallow the word "will".
        firsts = {}
        for name in list(self._to_alias):
            first = name.split()[0]
            if len(first) >= 3 and first != name:
                firsts.setdefault(first, []).append(name)
        for first, names in firsts.items():
            if len(names) == 1:
                self._first[first] = self._to_alias[names[0]]
        self._extra = 0

    def _add(self, name, alias):
        self._to_alias[name] = alias
        self._to_name[alias] = name

    def add_names(self, names):
        """Give placeholders to names that aren't in the Cashier Database."""
        for n in names:
            n = str(n).strip()
            if n and n not in self._to_alias:
                self._extra += 1
                self._add(n, f"Cashier X{self._extra}")

    @staticmethod
    def _swap(text, table, any_case):
        if not table:
            return text
        keys = sorted(table, key=len, reverse=True)       # longest first
        pattern = re.compile("|".join(r"(?<!\w)" + re.escape(k) + r"(?!\w)" for k in keys),
                             re.IGNORECASE if any_case else 0)
        if any_case:
            lower = {k.lower(): v for k, v in table.items()}
            return pattern.sub(lambda m: lower[m.group(0).lower()], text)
        return pattern.sub(lambda m: table[m.group(0)], text)

    def _walk(self, obj, fn):
        if isinstance(obj, str):
            return fn(obj)
        if isinstance(obj, dict):
            return {k: self._walk(v, fn) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._walk(v, fn) for v in obj]
        return obj

    def hide(self, obj):
        """Replace every known name with its alias (strings, dicts, lists)."""
        return self._walk(obj, lambda t: self._swap(self._swap(t, self._to_alias, True),
                                                    self._first, False))

    def reveal(self, obj):
        """Put real names back in place of aliases."""
        return self._walk(obj, lambda t: self._swap(t, self._to_name, False))
