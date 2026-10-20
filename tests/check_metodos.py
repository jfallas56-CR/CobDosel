import ast, sys
QT = {'setWindowTitle','setLayout','resize','show','close','accept','reject','exec','exec_','setMinimumSize','setMinimumWidth','setMinimumHeight',
 'update','repaint','width','height','rect','size','setMouseTracking','setCursor','unsetCursor','mapToScene','mapFromScene','scene','setScene',
 'viewport','setRenderHint','setDragMode','scale','resetTransform','fitInView','centerOn','horizontalScrollBar','verticalScrollBar','transform',
 'setTransformationAnchor','setResizeAnchor','setAlignment','setStyleSheet','setToolTip','setEnabled','isVisible','setWindowFlags','windowFlags',
 'parent','setParent','deleteLater','tr','sender','findChild','setFocus','hasFocus','installEventFilter','setSizePolicy','setFixedSize','setFixedWidth',
 'setFixedHeight','layout','setAttribute','setModal','raise_','activateWindow','setVisible','hide','setBackgroundBrush','setFrameShape',
 'setHorizontalScrollBarPolicy','setVerticalScrollBarPolicy','setViewportUpdateMode','mapToGlobal','font','setFont','palette','setPalette',
 'minimumSizeHint','sizeHint','geometry','setGeometry','move','pos','windowTitle','setWindowModality','grab','setAcceptDrops','isEnabled','setText','text'}
tot=0
for ruta in sys.argv[1:]:
    t=ast.parse(open(ruta,encoding='utf-8').read())
    clases={c.name:c for c in ast.walk(t) if isinstance(c,ast.ClassDef)}
    def defs(c):
        d={f.name for f in c.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for b in c.bases:
            if isinstance(b,ast.Name) and b.id in clases: d|=defs(clases[b.id])
        return d
    for c in clases.values():
        D=defs(c); A=set()
        for n in ast.walk(c):
            tg=n.targets if isinstance(n,ast.Assign) else ([n.target] if isinstance(n,(ast.AnnAssign,ast.AugAssign)) else [])
            for x in tg:
                if isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name) and x.value.id=='self': A.add(x.attr)
        for n in ast.walk(c):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='self':
                m=n.func.attr
                if m not in D|A|QT:
                    print(f"  {ruta}:{n.lineno} {c.name}.{m}()"); tot+=1
print("TOTAL", tot)
