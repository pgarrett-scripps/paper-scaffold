#import "../lib/template.typ": *
#chapter-title-page(id: "second", title: "Validation Results", authors: [Example Author],
  contributions: [The author designed this example and prepared its illustrations.
    The chapter demonstrates the export contract.], inclusion: none)
// >>> BODY START
== Overview
This chapter cites its own reference @second-shared.
The example retains native mathematics such as $x^2 / n$ in Word.
#figure(table(columns: (1fr, 3fr), table.header([Quantity], [Description]),
  [Signal], [A wider explanation column demonstrates preserved proportions.]),
  caption: [Measurement summary. The opening table list shows only the first sentence.]) <tbl-second>
#figure(image("diagram.svg", width: 80%),
  caption: [Workflow illustration. The blue input connects to the green output.
    This explanation is retained in the opening figure list.]) <fig-second>
// <<< BODY END
#chapter-references("chapters/second.bib", prefix: "second-")
