-- Promote export_docx.py's `#block[]<refs>` anchor into the Div citeproc needs.
--
-- Citeproc sets the reference list inside a Div whose id is "refs"; without
-- one it appends the list at the very END of the document -- which put the
-- references after the entire Supporting Information. Pandoc's Typst reader
-- has no syntax that yields a Div: the anchor arrives as a Para holding one
-- empty Span carrying the id. This rewrites that Para into the Div. Order
-- matters: pandoc applies filters in command-line order, so export_docx.py
-- passes --lua-filter BEFORE --citeproc.
function Para(el)
  if #el.content == 1 and el.content[1].t == "Span"
      and el.content[1].attr.identifier == "refs" then
    return pandoc.Div({}, pandoc.Attr("refs"))
  end
end
