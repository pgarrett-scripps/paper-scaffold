#import "@preview/alexandria:0.2.0": bibliographyx
= Chapter 2: Methods
// >>> BODY START
== Procedure
Each document declares which chapter sources it includes.
The build checks those sources and records the files used to produce its PDF.
The bibliography belongs to this chapter @methods-example.
// <<< BODY END
#bibliographyx("chapters/methods.bib", prefix: "methods-", title: "References")
