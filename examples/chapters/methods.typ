#import "layout.typ": layout
#import "@preview/alexandria:0.2.0": alexandria
#show: alexandria(prefix: "methods-", read: p => read(p))
#show: layout
#include "chapters/methods.typ"
