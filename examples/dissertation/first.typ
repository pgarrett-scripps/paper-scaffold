#import "lib/template.typ": *
#import "@preview/alexandria:0.2.0": alexandria
#show: alexandria(prefix: "first-", read: p => read(p))
#show: chapter-document
#include "chapters/first.typ"
