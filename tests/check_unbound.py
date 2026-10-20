"""Heurística: variables asignadas SOLO dentro de un try cuyo except no sale (return/raise) y usadas después."""
import ast, sys
def names_assigned(nodes):
    out=set()
    for n in nodes:
        for m in ast.walk(n):
            if isinstance(m,(ast.Assign,ast.AnnAssign,ast.AugAssign)):
                tg=m.targets if isinstance(m,ast.Assign) else [m.target]
                for t in tg:
                    for x in ast.walk(t):
                        if isinstance(x,ast.Name): out.add(x.id)
            elif isinstance(m,(ast.For,ast.With)):
                pass
    return out
def exits(handler):
    return any(isinstance(m,(ast.Return,ast.Raise,ast.Continue,ast.Break)) for b in handler.body for m in ast.walk(b))
for path in sys.argv[1:]:
    tree=ast.parse(open(path,encoding='utf-8').read())
    for fn in [n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,))]:
        body=fn.body
        def scan(stmts, before):
            for i,s in enumerate(stmts):
                if isinstance(s,ast.Try) and s.handlers:
                    inside=names_assigned(s.body)
                    if not all(exits(h) for h in s.handlers):
                        handler_assigned=set().union(*[names_assigned(h.body) for h in s.handlers])
                        risky=inside-before-handler_assigned
                        later=stmts[i+1:]
                        used={x.id for st in later for x in ast.walk(st) if isinstance(x,ast.Name) and isinstance(x.ctx,ast.Load)}
                        for v in sorted(risky & used):
                            print(f"{path}:{s.lineno} {fn.name}: '{v}' asignada en try, usada después y el except no sale")
                before|=names_assigned([s])
        args={a.arg for a in fn.args.args}
        scan(body,set(args))
