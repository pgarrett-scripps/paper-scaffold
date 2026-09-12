#import "layout.typ": layout
#import "@preview/alexandria:0.2.0": alexandria
#show: alexandria(prefix: "intro-", read: p => read(p))
#show: alexandria(prefix: "methods-", read: p => read(p))
#show: layout
= Example dissertation
This front matter is outside the counted chapter prose.
#pagebreak()
#include "chapters/introduction.typ"
#pagebreak()
#include "chapters/methods.typ"
