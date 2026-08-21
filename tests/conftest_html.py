"""Synthetic/test-only HTML snapshots. None was copied from a live manufacturer page."""

SIMPLE_PRODUCT_HTML = b"""<!doctype html>
<html><head><title>Fixture 45297BK</title></head>
<body><main><h1>Fixture Vanity Light</h1><p>Model 45297BK</p></main></body></html>
"""

PRODUCT_JSONLD_HTML = b"""<!doctype html><html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Fixture Light",
 "mpn":"45297BK","brand":{"@type":"Brand","name":"FixtureCo"}}
</script></head><body><main>Fixture product</main></body></html>
"""

MULTIPLE_JSONLD_HTML = b"""<html><head>
<script type="application/ld+json">{"@type":"WebSite","name":"Fixture Site"}</script>
<script type="application/ld+json">[{"@type":"Product","sku":"45297BK"}]</script>
</head><body>Multiple structured blocks</body></html>
"""

MALFORMED_JSONLD_HTML = b"""<html><head>
<script type="application/ld+json">{"@type":"Product", broken}</script>
<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>
</head><body>Usable document text</body></html>
"""

NOISY_HTML = b"""<html><head><style>.secret{display:none}</style></head><body>
<nav>Account Cart Menu</nav><main><h1>Visible heading</h1><p>Visible detail</p></main>
<script>globalThis.executed = true; fetch('https://subresource.invalid/')</script>
<noscript>noscript noise</noscript><template>template noise</template>
<iframe src="https://frame.invalid/">frame fallback noise</iframe></body></html>
"""

CANONICAL_HTML = b"""<html><head><title>Canonical Fixture</title>
<link rel="canonical" href="https://manufacturer.invalid/products/45297bk">
<meta name="description" content="Fixture description">
<meta property="og:title" content="Fixture OG title">
<meta property="og:description" content="Fixture OG description">
</head><body>Canonical body</body></html>
"""

NO_USEFUL_METADATA_HTML = b"<html><body><div></div></body></html>"
EMPTY_HTML = b""
