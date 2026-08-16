# Curated source artifacts

Documents a person has confirmed are safe to publish. Everything ingestion writes
lands in `data/artifacts/runtime/` instead, which is gitignored.

## The rule

**No manufacturer PDF enters this directory automatically.** Promotion from runtime is
a deliberate copy, made only after someone has confirmed that the document may be
redistributed in a public repository.

Public availability is not redistribution rights. A datasheet that anyone can download
from a manufacturer's website is still that manufacturer's copyrighted work, and
putting it in a public Git history is a republication we are usually not entitled to
make.

For the eventual Schneider demonstration this matters concretely: we can ingest a real
LC1D18 artifact **locally**, run the whole pipeline against it, and cite it by URL,
hash, and page — without the PDF itself ever entering this repository. The hash and
page map are ours; the document is not.

## What may live here

- Documents we authored.
- Documents under a licence that permits redistribution, with the licence recorded in
  the artifact's `SourceMetadata.license_note`.
- Small synthetic fixtures created for this repository.

## What may not

- Manufacturer datasheets, catalogues, and product pages.
- Anything whose licence has not been checked.
- Anything copied here because it was convenient for a test.
